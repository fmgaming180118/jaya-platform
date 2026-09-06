"""Secure HTTP service boundary and truthful readiness for JAYA_CORE."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import inspect
import os
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from jaya_core.core_config import CoreConfig, core_config
from jaya_core.observability.runtime_metrics import RuntimeMetrics
from jaya_core.reasoning.pure_logic import LogicFailureCode, PureLogicError

_PUBLIC_PATHS = frozenset({"/healthz", "/readyz"})
_CORS_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"})
_CORS_HEADERS = frozenset({"authorization", "content-type"})
_SERVICE_NAME = "jaya-core"
_SERVICE_VERSION = "1"


class CapabilityUnavailableError(RuntimeError):
    """Raised when a runtime does not implement a requested public contract."""


@dataclass(frozen=True, slots=True)
class DependencyStatus:
    """Sanitized state returned by one readiness dependency."""

    name: str
    ready: bool
    code: str
    critical: bool = True

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "ready": self.ready,
            "code": self.code,
            "critical": self.critical,
        }


@runtime_checkable
class ReadinessDependency(Protocol):
    """Contract for dependency probes used by the service factory."""

    name: str
    critical: bool

    def check(self) -> DependencyStatus | Awaitable[DependencyStatus]:
        ...


class ModelArtifactDependency:
    name = "model_artifact"

    def __init__(self, path: Path, *, critical: bool = True) -> None:
        self._path = path
        self.critical = critical

    def check(self) -> DependencyStatus:
        try:
            if not self._path.exists():
                return DependencyStatus(self.name, False, "missing", self.critical)
            if not self._path.is_file():
                return DependencyStatus(self.name, False, "not_file", self.critical)
            if self._path.stat().st_size <= 0:
                return DependencyStatus(self.name, False, "empty", self.critical)
            if not os.access(self._path, os.R_OK):
                return DependencyStatus(self.name, False, "not_readable", self.critical)
        except OSError:
            return DependencyStatus(
                self.name, False, "inspection_failed", self.critical
            )
        return DependencyStatus(self.name, True, "available", self.critical)


class DataDirectoryDependency:
    name = "data_directory"
    critical = True

    def __init__(self, path: Path) -> None:
        self._path = path

    def check(self) -> DependencyStatus:
        try:
            if not self._path.exists():
                return DependencyStatus(self.name, False, "missing")
            if not self._path.is_dir():
                return DependencyStatus(self.name, False, "not_directory")
            if not os.access(self._path, os.R_OK | os.W_OK):
                return DependencyStatus(self.name, False, "not_read_write")
        except OSError:
            return DependencyStatus(self.name, False, "inspection_failed")
        return DependencyStatus(self.name, True, "available")


class ApiCredentialDependency:
    name = "api_authentication"
    critical = True

    def __init__(self, config: CoreConfig) -> None:
        self._configured = bool(config.api_key)

    def check(self) -> DependencyStatus:
        return DependencyStatus(
            self.name,
            self._configured,
            "configured" if self._configured else "not_configured",
        )


class RuntimeDependency:
    name = "brain_runtime"
    critical = True

    def __init__(self, runtime: object | None) -> None:
        self._runtime = runtime

    async def check(self) -> DependencyStatus:
        if self._runtime is None:
            return DependencyStatus(self.name, False, "not_configured")
        try:
            readiness = getattr(self._runtime, "is_ready", None)
            if not callable(readiness):
                return DependencyStatus(
                    self.name,
                    False,
                    "readiness_contract_missing",
                )
            result = readiness()
            if inspect.isawaitable(result):
                result = await result
            ready = bool(result)
        except Exception:
            return DependencyStatus(self.name, False, "probe_failed")
        code = "ready" if ready else "not_ready"
        model_readiness = getattr(self._runtime, "model_readiness", None)
        model_code = getattr(model_readiness, "code", None)
        safe_code = getattr(model_code, "value", None)
        if not ready and isinstance(safe_code, str) and safe_code:
            code = safe_code
        return DependencyStatus(self.name, ready, code)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=16_384)


class LogicRuleRequest(BaseModel):
    """Strict external representation of one propositional implication."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    rule_id: str = Field(alias="id", min_length=1, max_length=128)
    premises: list[str] = Field(alias="if", min_length=1, max_length=32)
    conclusion: str = Field(alias="then", min_length=1, max_length=132)


class LogicEvaluateRequest(BaseModel):
    """Bounded input contract for deterministic Pure Logic evaluation."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    request_id: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9_.:-]+$",
    )
    facts: list[str] = Field(default_factory=list, max_length=2_000)
    rules: list[LogicRuleRequest] = Field(default_factory=list, max_length=2_000)
    query: str = Field(min_length=1, max_length=132)


def _error(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
        headers=headers,
    )


def _bearer_token(request: Request) -> str:
    scheme, separator, token = request.headers.get("authorization", "").partition(" ")
    if not separator or scheme.casefold() != "bearer":
        return ""
    return token.strip()


def _token_matches(config: CoreConfig, candidate: str) -> bool:
    expected = config.api_key.get_secret_value()
    if not expected or not candidate:
        return False
    expected_digest = hashlib.sha256(expected.encode("utf-8")).digest()
    candidate_digest = hashlib.sha256(candidate.encode("utf-8")).digest()
    return hmac.compare_digest(expected_digest, candidate_digest)


def _cors_preflight_error(request: Request) -> JSONResponse | None:
    requested_method = request.headers.get("access-control-request-method", "").upper()
    requested_headers = {
        item.strip().lower()
        for item in request.headers.get("access-control-request-headers", "").split(",")
        if item.strip()
    }
    if requested_method not in _CORS_METHODS or not requested_headers <= _CORS_HEADERS:
        return _error(403, "cors_request_denied", "CORS preflight was denied.")
    return None


async def _run_probe(dependency: ReadinessDependency) -> DependencyStatus:
    try:
        result = dependency.check()
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, DependencyStatus):
            return result
        return DependencyStatus(
            getattr(dependency, "name", "unknown"),
            False,
            "invalid_probe_result",
            getattr(dependency, "critical", True),
        )
    except Exception:
        return DependencyStatus(
            getattr(dependency, "name", "unknown"),
            False,
            "probe_failed",
            getattr(dependency, "critical", True),
        )


async def _runtime_chat(
    runtime: object,
    message: str,
    *,
    timeout_seconds: float,
) -> str:
    chat = getattr(runtime, "chat", None)
    if not callable(chat):
        raise CapabilityUnavailableError
    operation = (
        chat(message)
        if inspect.iscoroutinefunction(chat)
        else run_in_threadpool(chat, message)
    )
    result = await asyncio.wait_for(operation, timeout=timeout_seconds)
    if not isinstance(result, str) or not result.strip():
        raise RuntimeError("invalid runtime response")
    return result


async def _runtime_logic(
    runtime: object,
    request: LogicEvaluateRequest,
    *,
    timeout_seconds: float,
) -> dict[str, object]:
    evaluate = getattr(runtime, "reason_logic", None)
    if not callable(evaluate):
        raise CapabilityUnavailableError
    arguments: dict[str, Any] = {
        "request_id": request.request_id,
        "facts": request.facts,
        "rules": [rule.model_dump(by_alias=True) for rule in request.rules],
        "query": request.query,
    }
    operation = (
        evaluate(**arguments)
        if inspect.iscoroutinefunction(evaluate)
        else run_in_threadpool(evaluate, **arguments)
    )
    result = await asyncio.wait_for(operation, timeout=timeout_seconds)
    serialize = getattr(result, "to_dict", None)
    if not callable(serialize):
        raise RuntimeError("invalid logic runtime response")
    payload = serialize()
    if not isinstance(payload, dict):
        raise RuntimeError("invalid logic runtime payload")
    return payload


def create_app(
    config: CoreConfig | None = None,
    *,
    runtime: object | None = None,
    dependencies: Sequence[ReadinessDependency] | None = None,
) -> FastAPI:
    """Create an isolated API instance with explicit runtime dependencies."""

    active_config = core_config if config is None else config
    active_config.validate()
    baseline: tuple[ReadinessDependency, ...] = (
        ModelArtifactDependency(
            active_config.model_path,
            critical=active_config.model_required,
        ),
        DataDirectoryDependency(active_config.data_dir),
        ApiCredentialDependency(active_config),
        RuntimeDependency(runtime),
    )
    readiness_dependencies = baseline + tuple(dependencies or ())

    app = FastAPI(
        title="JAYA Core API",
        version=_SERVICE_VERSION,
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.config = active_config
    app.state.runtime = runtime
    app.state.readiness_dependencies = readiness_dependencies
    app.state.metrics = RuntimeMetrics()
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(active_config.trusted_hosts),
    )

    @app.middleware("http")
    async def security_boundary(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        started = time.perf_counter()

        def observed(response: Response) -> Response:
            app.state.metrics.observe_http(
                request.url.path,
                response.status_code,
                (time.perf_counter() - started) * 1_000,
            )
            return response

        origin = request.headers.get("origin")
        origin_allowed = bool(origin and origin in active_config.cors_origins)
        if origin and not origin_allowed:
            response = _error(
                403,
                "origin_denied",
                "Cross-origin request is not allowed.",
            )
            return observed(response)

        preflight = (
            request.method == "OPTIONS"
            and bool(origin)
            and bool(request.headers.get("access-control-request-method"))
        )
        if preflight:
            denied = _cors_preflight_error(request)
            if denied is not None:
                return observed(denied)
            response: Response = Response(status_code=204)
        elif request.url.path not in _PUBLIC_PATHS:
            if not active_config.api_key:
                return observed(
                    _error(
                        503,
                        "authentication_not_configured",
                        "Protected API routes are unavailable.",
                    )
                )
            if not _token_matches(active_config, _bearer_token(request)):
                return observed(
                    _error(
                        401,
                        "authentication_required",
                        "A valid bearer credential is required.",
                        headers={"WWW-Authenticate": "Bearer"},
                    )
                )
            response = await call_next(request)
        else:
            response = await call_next(request)

        if origin_allowed:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Methods"] = ", ".join(
                sorted(_CORS_METHODS)
            )
            response.headers[
                "Access-Control-Allow-Headers"
            ] = "Authorization, Content-Type"
            response.headers["Vary"] = "Origin"
        return observed(response)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> dict[str, str]:
        return {
            "status": "alive",
            "service": _SERVICE_NAME,
            "version": _SERVICE_VERSION,
        }

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> JSONResponse:
        statuses: list[DependencyStatus] = []
        for dependency in app.state.readiness_dependencies:
            try:
                status = await asyncio.wait_for(
                    _run_probe(dependency),
                    timeout=min(active_config.request_timeout_seconds, 5.0),
                )
            except TimeoutError:
                status = DependencyStatus(
                    getattr(dependency, "name", "unknown"),
                    False,
                    "probe_timeout",
                    getattr(dependency, "critical", True),
                )
            statuses.append(status)
        ready = all(status.ready for status in statuses if status.critical)
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "not_ready",
                "dependencies": [status.as_dict() for status in statuses],
            },
        )

    @app.post("/v1/chat")
    async def chat(request: ChatRequest) -> JSONResponse:
        if runtime is None or not callable(getattr(runtime, "chat", None)):
            return _error(
                501,
                "capability_not_implemented",
                "No verified Core inference runtime is attached.",
            )
        runtime_status = await RuntimeDependency(runtime).check()
        if not runtime_status.ready:
            return _error(
                503,
                "runtime_not_ready",
                "The verified Core inference runtime is unavailable.",
            )
        try:
            response = await _runtime_chat(
                runtime,
                request.message,
                timeout_seconds=active_config.request_timeout_seconds,
            )
        except CapabilityUnavailableError:
            return _error(501, "capability_not_implemented", "Chat is unavailable.")
        except TimeoutError:
            return _error(504, "runtime_timeout", "The Core runtime timed out.")
        except Exception:
            return _error(
                503,
                "runtime_unavailable",
                "The Core runtime could not produce a verified response.",
            )
        return JSONResponse({"response": response})

    @app.post("/v1/logic/evaluate")
    async def logic_evaluate(request: LogicEvaluateRequest) -> JSONResponse:
        if runtime is None or not callable(getattr(runtime, "reason_logic", None)):
            return _error(
                501,
                "capability_not_implemented",
                "No Pure Logic runtime is attached.",
            )
        runtime_status = await RuntimeDependency(runtime).check()
        if not runtime_status.ready:
            return _error(
                503,
                "runtime_not_ready",
                "The Pure Logic runtime is unavailable.",
            )
        try:
            payload = await _runtime_logic(
                runtime,
                request,
                timeout_seconds=active_config.request_timeout_seconds,
            )
        except PureLogicError as exc:
            status_by_code = {
                LogicFailureCode.INVALID_INPUT: 422,
                LogicFailureCode.THEORY_LIMIT_EXCEEDED: 413,
                LogicFailureCode.SOLVER_TIMEOUT: 504,
                LogicFailureCode.DUPLICATE_REQUEST: 409,
                LogicFailureCode.STORAGE_ERROR: 503,
                LogicFailureCode.CORRUPT_PROOF: 500,
                LogicFailureCode.RUNTIME_NOT_READY: 503,
                LogicFailureCode.MEMORY_LIMIT_EXCEEDED: 503,
                LogicFailureCode.RESOURCE_PROBE_UNAVAILABLE: 503,
            }
            return _error(
                status_by_code[exc.code],
                exc.code.value.casefold(),
                str(exc),
            )
        except CapabilityUnavailableError:
            return _error(
                501,
                "capability_not_implemented",
                "Pure Logic is unavailable.",
            )
        except TimeoutError:
            return _error(504, "runtime_timeout", "Pure Logic evaluation timed out.")
        except Exception:
            return _error(
                503,
                "runtime_unavailable",
                "Pure Logic could not produce a verified result.",
            )
        app.state.metrics.observe_logic(str(payload.get("status", "UNKNOWN")))
        return JSONResponse(payload)

    @app.get("/v1/metrics")
    async def metrics() -> JSONResponse:
        runtime_snapshot: dict[str, object] = {"ready": False}
        snapshot_provider = getattr(runtime, "operational_snapshot", None)
        if callable(snapshot_provider):
            try:
                value = await run_in_threadpool(snapshot_provider)
                if isinstance(value, dict):
                    runtime_snapshot = value
            except Exception:
                runtime_snapshot = {"ready": False, "error": "snapshot_failed"}
        return JSONResponse(
            {
                "service": app.state.metrics.snapshot().to_dict(),
                "runtime": runtime_snapshot,
            }
        )

    async def thesis_not_implemented() -> JSONResponse:
        return _error(
            501,
            "capability_not_implemented",
            "Thesis research belongs to JAYA_RESEARCH and is not served by Core.",
        )

    thesis_methods = ["GET", "POST", "PUT", "PATCH", "DELETE"]
    app.add_api_route("/v1/thesis", thesis_not_implemented, methods=thesis_methods)
    app.add_api_route(
        "/v1/thesis/{remaining_path:path}",
        thesis_not_implemented,
        methods=thesis_methods,
    )
    return app


__all__ = [
    "ApiCredentialDependency",
    "CapabilityUnavailableError",
    "DataDirectoryDependency",
    "DependencyStatus",
    "ModelArtifactDependency",
    "ReadinessDependency",
    "RuntimeDependency",
    "LogicEvaluateRequest",
    "LogicRuleRequest",
    "create_app",
]
