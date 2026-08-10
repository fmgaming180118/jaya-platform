"""Verified, detachable capability puzzles owned by JAYA Core.

External puzzles are loaded only from explicitly configured roots. Their Python
artifact must match the SHA-256 declared by the manifest before any code is
imported. Missing puzzles fail closed and never produce simulated output.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from types import ModuleType
from typing import Any, Callable, Mapping, Protocol, Sequence, runtime_checkable

_SAFE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SAFE_VERSION = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)?$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_RISK_CLASSES = frozenset(
    {
        "READ_ONLY",
        "REVERSIBLE",
        "DESTRUCTIVE",
        "PHYSICAL_ACTION",
        "SECURITY_SENSITIVE",
        "COGNITIVE_UPDATE",
    }
)


class PuzzleFailureCode(str, Enum):
    INVALID_MANIFEST = "INVALID_MANIFEST"
    CAPABILITY_UNAVAILABLE = "CAPABILITY_UNAVAILABLE"
    CAPABILITY_CONFLICT = "CAPABILITY_CONFLICT"
    ARTIFACT_OUTSIDE_ROOT = "ARTIFACT_OUTSIDE_ROOT"
    ARTIFACT_INTEGRITY_FAILED = "ARTIFACT_INTEGRITY_FAILED"
    ADAPTER_INVALID = "ADAPTER_INVALID"
    ADAPTER_UNHEALTHY = "ADAPTER_UNHEALTHY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    PAYLOAD_INVALID = "PAYLOAD_INVALID"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    INVOCATION_TIMEOUT = "INVOCATION_TIMEOUT"
    INVOCATION_FAILED = "INVOCATION_FAILED"
    RESULT_INVALID = "RESULT_INVALID"


class PuzzleError(RuntimeError):
    def __init__(self, code: PuzzleFailureCode, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, slots=True)
class PuzzleManifest:
    puzzle_id: str
    capability_id: str
    version: str
    api_version: str = "1.0"
    permissions_required: tuple[str, ...] = ()
    timeout_seconds: float = 5.0
    max_payload_bytes: int = 262_144
    artifact: str | None = None
    artifact_sha256: str | None = None
    entrypoint: str = "create_puzzle"
    risk_class: str = "SECURITY_SENSITIVE"

    def __post_init__(self) -> None:
        if not _SAFE_ID.fullmatch(self.puzzle_id):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "puzzle_id is invalid",
            )
        if not _SAFE_ID.fullmatch(self.capability_id):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "capability_id is invalid",
            )
        if not _SAFE_VERSION.fullmatch(self.version):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "version is invalid",
            )
        if self.api_version != "1.0":
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "unsupported puzzle api_version",
            )
        if not 0.01 <= self.timeout_seconds <= 300:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "timeout_seconds must be between 0.01 and 300",
            )
        if not 1 <= self.max_payload_bytes <= 8_388_608:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "max_payload_bytes is outside the safe range",
            )
        if len(set(self.permissions_required)) != len(self.permissions_required):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "permissions_required contains duplicates",
            )
        if any(not _SAFE_ID.fullmatch(item) for item in self.permissions_required):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "permission id is invalid",
            )
        external_fields = (self.artifact, self.artifact_sha256)
        if any(external_fields) and not all(external_fields):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "artifact and artifact_sha256 must be declared together",
            )
        if self.artifact_sha256 and not _SHA256.fullmatch(self.artifact_sha256):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "artifact_sha256 is invalid",
            )
        if not self.entrypoint.isidentifier():
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "entrypoint must be a Python identifier",
            )
        if self.risk_class not in _RISK_CLASSES:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "risk_class is not recognized by the policy contract",
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "PuzzleManifest":
        allowed = {
            "schema_version",
            "puzzle_id",
            "capability_id",
            "version",
            "api_version",
            "permissions_required",
            "timeout_seconds",
            "max_payload_bytes",
            "artifact",
            "artifact_sha256",
            "entrypoint",
            "risk_class",
        }
        if set(value) - allowed:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "puzzle manifest contains unknown fields",
            )
        if value.get("schema_version") != 1:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "unsupported puzzle manifest schema_version",
            )
        permissions = value.get("permissions_required", ())
        if not isinstance(permissions, Sequence) or isinstance(
            permissions, (str, bytes)
        ):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "permissions_required must be an array",
            )
        try:
            return cls(
                puzzle_id=value["puzzle_id"],
                capability_id=value["capability_id"],
                version=value["version"],
                api_version=value.get("api_version", "1.0"),
                permissions_required=tuple(permissions),
                timeout_seconds=float(value.get("timeout_seconds", 5.0)),
                max_payload_bytes=int(value.get("max_payload_bytes", 262_144)),
                artifact=value.get("artifact"),
                artifact_sha256=value.get("artifact_sha256"),
                entrypoint=value.get("entrypoint", "create_puzzle"),
                risk_class=value.get("risk_class", "SECURITY_SENSITIVE"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "puzzle manifest fields are invalid",
            ) from exc


@runtime_checkable
class CapabilityPuzzle(Protocol):
    def health_check(self) -> bool:
        ...

    def invoke(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        ...


@dataclass(frozen=True, slots=True)
class PuzzleReceipt:
    puzzle_id: str
    capability_id: str
    version: str
    status: str
    elapsed_ms: float
    invoked_at: str
    input_sha256: str
    result_sha256: str
    artifact_sha256: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "puzzle_id": self.puzzle_id,
            "capability_id": self.capability_id,
            "version": self.version,
            "status": self.status,
            "elapsed_ms": self.elapsed_ms,
            "invoked_at": self.invoked_at,
            "input_sha256": self.input_sha256,
            "result_sha256": self.result_sha256,
            "artifact_sha256": self.artifact_sha256,
        }


@dataclass(frozen=True, slots=True)
class PuzzleInvocation:
    result: Mapping[str, Any]
    receipt: PuzzleReceipt

    def to_dict(self) -> dict[str, object]:
        return {"result": dict(self.result), "receipt": self.receipt.to_dict()}


class CapabilityPuzzleRegistry:
    """Thread-safe puzzle lifecycle, discovery, and bounded invocation."""

    def __init__(
        self,
        puzzle_roots: Sequence[Path | str] = (),
        *,
        worker_count: int = 4,
        authorization_required: bool = False,
        authorization_validator: (
            Callable[[str, Mapping[str, Any], object], bool] | None
        ) = None,
    ) -> None:
        if not 1 <= worker_count <= 32:
            raise ValueError("worker_count must be between 1 and 32")
        self._roots = tuple(Path(item).resolve() for item in puzzle_roots)
        if authorization_required and authorization_validator is None:
            raise ValueError(
                "authorization_validator is required in protected registry mode"
            )
        self._authorization_required = authorization_required
        self._authorization_validator = authorization_validator
        self._manifests: dict[str, PuzzleManifest] = {}
        self._puzzles: dict[str, CapabilityPuzzle] = {}
        self._modules: dict[str, ModuleType] = {}
        self._external_sources: dict[str, Path] = {}
        self._failures: dict[str, str] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(
            max_workers=worker_count,
            thread_name_prefix="jaya-puzzle",
        )

    def attach(
        self,
        manifest: PuzzleManifest,
        puzzle: CapabilityPuzzle,
    ) -> None:
        if not isinstance(puzzle, CapabilityPuzzle):
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_INVALID,
                "puzzle does not implement health_check and invoke",
            )
        try:
            healthy = puzzle.health_check()
        except Exception as exc:
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_UNHEALTHY,
                "puzzle health check failed",
            ) from exc
        if healthy is not True:
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_UNHEALTHY,
                "puzzle reported unhealthy",
            )
        with self._lock:
            existing = self._manifests.get(manifest.capability_id)
            if existing is not None and existing != manifest:
                raise PuzzleError(
                    PuzzleFailureCode.CAPABILITY_CONFLICT,
                    "capability id is already owned by another puzzle",
                )
            self._manifests[manifest.capability_id] = manifest
            self._puzzles[manifest.capability_id] = puzzle
            self._failures.pop(manifest.capability_id, None)

    def detach(self, capability_id: str) -> bool:
        with self._lock:
            removed = self._puzzles.pop(capability_id, None)
            self._manifests.pop(capability_id, None)
            self._modules.pop(capability_id, None)
            self._external_sources.pop(capability_id, None)
            return removed is not None

    def refresh(self) -> dict[str, str]:
        results: dict[str, str] = {}
        discovered: set[str] = set()
        for root in self._roots:
            if not root.exists() or not root.is_dir():
                results[str(root)] = "ROOT_UNAVAILABLE"
                continue
            for manifest_path in sorted(root.glob("*/puzzle.json")):
                key = str(manifest_path)
                try:
                    manifest, puzzle, module = self._load_external(
                        root,
                        manifest_path,
                    )
                    self.attach(manifest, puzzle)
                    with self._lock:
                        self._modules[manifest.capability_id] = module
                        self._external_sources[manifest.capability_id] = manifest_path
                    discovered.add(manifest.capability_id)
                    results[key] = "CONNECTED"
                except PuzzleError as exc:
                    results[key] = exc.code.value
                    with self._lock:
                        self._failures[key] = exc.code.value
        with self._lock:
            stale = set(self._external_sources) - discovered
        for capability_id in stale:
            self.detach(capability_id)
        return results

    def invoke(
        self,
        capability_id: str,
        payload: Mapping[str, Any],
        *,
        granted_permissions: Sequence[str] = (),
        authorization: object | None = None,
    ) -> PuzzleInvocation:
        if not isinstance(payload, Mapping):
            raise PuzzleError(
                PuzzleFailureCode.RESULT_INVALID,
                "puzzle payload must be an object",
            )
        with self._lock:
            puzzle = self._puzzles.get(capability_id)
            manifest = self._manifests.get(capability_id)
        if puzzle is None or manifest is None:
            self.refresh()
            with self._lock:
                puzzle = self._puzzles.get(capability_id)
                manifest = self._manifests.get(capability_id)
        if puzzle is None or manifest is None:
            raise PuzzleError(
                PuzzleFailureCode.CAPABILITY_UNAVAILABLE,
                f"capability puzzle is unavailable: {capability_id}",
            )

        granted = set(granted_permissions)
        required = set(manifest.permissions_required)
        if not required <= granted:
            raise PuzzleError(
                PuzzleFailureCode.PERMISSION_DENIED,
                "required puzzle permissions were not granted",
            )
        if self._authorization_required:
            validator = self._authorization_validator
            try:
                authorized = (
                    validator(capability_id, payload, authorization)
                    if validator is not None and authorization is not None
                    else False
                )
            except (RuntimeError, TypeError, ValueError):
                authorized = False
            if authorized is not True:
                raise PuzzleError(
                    PuzzleFailureCode.PERMISSION_DENIED,
                    "verified Ethical Heart authorization is required",
                )
        try:
            healthy = puzzle.health_check()
        except Exception as exc:
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_UNHEALTHY,
                "puzzle health check failed before invocation",
            ) from exc
        if healthy is not True:
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_UNHEALTHY,
                "puzzle became unhealthy before invocation",
            )
        try:
            encoded = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PuzzleError(
                PuzzleFailureCode.PAYLOAD_INVALID,
                "puzzle payload is not JSON serializable",
            ) from exc
        if len(encoded) > manifest.max_payload_bytes:
            raise PuzzleError(
                PuzzleFailureCode.PAYLOAD_TOO_LARGE,
                "puzzle payload exceeds manifest limit",
            )

        started = time.perf_counter()
        future = self._executor.submit(puzzle.invoke, payload)
        try:
            result = future.result(timeout=manifest.timeout_seconds)
        except FutureTimeout as exc:
            future.cancel()
            raise PuzzleError(
                PuzzleFailureCode.INVOCATION_TIMEOUT,
                "puzzle invocation timed out",
            ) from exc
        except PuzzleError:
            raise
        except Exception as exc:
            raise PuzzleError(
                PuzzleFailureCode.INVOCATION_FAILED,
                "puzzle invocation failed",
            ) from exc
        if not isinstance(result, Mapping):
            raise PuzzleError(
                PuzzleFailureCode.RESULT_INVALID,
                "puzzle result must be an object",
            )
        try:
            result_bytes = json.dumps(
                result,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise PuzzleError(
                PuzzleFailureCode.RESULT_INVALID,
                "puzzle result is not JSON serializable",
            ) from exc
        if len(result_bytes) > manifest.max_payload_bytes:
            raise PuzzleError(
                PuzzleFailureCode.RESULT_INVALID,
                "puzzle result exceeds manifest limit",
            )
        elapsed_ms = round((time.perf_counter() - started) * 1_000, 6)
        return PuzzleInvocation(
            result=dict(result),
            receipt=PuzzleReceipt(
                puzzle_id=manifest.puzzle_id,
                capability_id=manifest.capability_id,
                version=manifest.version,
                status="SUCCESS",
                elapsed_ms=elapsed_ms,
                invoked_at=datetime.now(timezone.utc).isoformat(),
                input_sha256=hashlib.sha256(encoded).hexdigest(),
                result_sha256=hashlib.sha256(result_bytes).hexdigest(),
                artifact_sha256=manifest.artifact_sha256,
            ),
        )

    def capabilities(self) -> tuple[PuzzleManifest, ...]:
        with self._lock:
            return tuple(self._manifests.values())

    def manifest(self, capability_id: str) -> PuzzleManifest:
        """Return trusted in-memory metadata for policy evaluation."""

        with self._lock:
            manifest = self._manifests.get(capability_id)
        if manifest is None:
            self.refresh()
            with self._lock:
                manifest = self._manifests.get(capability_id)
        if manifest is None:
            raise PuzzleError(
                PuzzleFailureCode.CAPABILITY_UNAVAILABLE,
                f"capability puzzle is unavailable: {capability_id}",
            )
        return manifest

    def health_check(self) -> bool:
        with self._lock:
            puzzles = tuple(self._puzzles.values())
        try:
            return all(puzzle.health_check() is True for puzzle in puzzles)
        except Exception:
            return False

    def close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    def _load_external(
        self,
        root: Path,
        manifest_path: Path,
    ) -> tuple[PuzzleManifest, CapabilityPuzzle, ModuleType]:
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "cannot read puzzle manifest",
            ) from exc
        if not isinstance(raw, Mapping):
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "puzzle manifest must be an object",
            )
        manifest = PuzzleManifest.from_mapping(raw)
        if not manifest.artifact or not manifest.artifact_sha256:
            raise PuzzleError(
                PuzzleFailureCode.INVALID_MANIFEST,
                "external puzzle requires an artifact",
            )
        artifact = (manifest_path.parent / manifest.artifact).resolve()
        try:
            artifact.relative_to(root)
        except ValueError as exc:
            raise PuzzleError(
                PuzzleFailureCode.ARTIFACT_OUTSIDE_ROOT,
                "puzzle artifact escaped its configured root",
            ) from exc
        try:
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        except OSError as exc:
            raise PuzzleError(
                PuzzleFailureCode.ARTIFACT_INTEGRITY_FAILED,
                "cannot read puzzle artifact",
            ) from exc
        if digest != manifest.artifact_sha256:
            raise PuzzleError(
                PuzzleFailureCode.ARTIFACT_INTEGRITY_FAILED,
                "puzzle artifact digest mismatch",
            )

        module_name = f"jaya_puzzle_{manifest.puzzle_id.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(module_name, artifact)
        if spec is None or spec.loader is None:
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_INVALID,
                "cannot construct puzzle module loader",
            )
        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
            factory = getattr(module, manifest.entrypoint)
            puzzle = factory()
        except Exception as exc:
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_INVALID,
                "puzzle entrypoint failed",
            ) from exc
        if not isinstance(puzzle, CapabilityPuzzle):
            raise PuzzleError(
                PuzzleFailureCode.ADAPTER_INVALID,
                "external puzzle does not satisfy the capability protocol",
            )
        return manifest, puzzle, module


__all__ = [
    "CapabilityPuzzle",
    "CapabilityPuzzleRegistry",
    "PuzzleError",
    "PuzzleFailureCode",
    "PuzzleInvocation",
    "PuzzleManifest",
    "PuzzleReceipt",
]
