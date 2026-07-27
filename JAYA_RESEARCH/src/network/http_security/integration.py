"""Environment-backed integration helpers for the Research FastAPI service."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any

from fastapi import Request

from .cors import CorsPolicy
from .errors import configuration_error
from .identity import (
    ApiKeyAuthenticator,
    ApiPrincipal,
    require_scope,
    request_principal,
    workspace_identity,
)
from .middleware import HttpSecurityPolicy
from .rate_limit import TokenBucketRateLimiter

_PUBLIC_PATHS = frozenset({"/"})
_ADMIN_PATH_PREFIXES = (
    "/config/",
    "/evolution/",
)
_ADMIN_EXACT_PATHS = frozenset(
    {
        "/workspaces",
        "/workspaces/create",
    }
)


@dataclass(frozen=True)
class RuntimeHttpSecurity:
    """Validated security objects constructed once during API import."""

    authenticator: ApiKeyAuthenticator
    policy: HttpSecurityPolicy
    rate_limiter: TokenBucketRateLimiter
    cors: CorsPolicy


def _positive_int(name: str, default: int) -> int:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = int(raw_value)
    except ValueError as exc:
        raise configuration_error(f"{name} must be an integer") from exc
    if value < 1:
        raise configuration_error(f"{name} must be positive")
    return value


def _positive_float(name: str, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise configuration_error(f"{name} must be a number") from exc
    if not math.isfinite(value) or value <= 0:
        raise configuration_error(f"{name} must be a positive finite number")
    return value


def _test_principal_from_environment() -> ApiPrincipal | None:
    test_mode_requested = os.getenv(
        "JAYA_HTTP_SECURITY_TEST_MODE",
        "",
    ).strip() == "1"
    environment = os.getenv("JAYA_ENV", "development").strip().casefold()
    if not test_mode_requested:
        return None
    if environment != "test":
        raise configuration_error(
            "JAYA_HTTP_SECURITY_TEST_MODE is only valid when JAYA_ENV=test"
        )
    return ApiPrincipal(
        subject="research-api-test",
        credential_id="research-api-test",
        scopes=frozenset({"*"}),
        workspace_ids=frozenset({"*"}),
        is_test_identity=True,
    )


def runtime_http_security_from_environment() -> RuntimeHttpSecurity:
    """Build a fail-closed runtime security configuration.

    The service remains importable without credentials, but every non-public
    request receives ``AUTH_NOT_CONFIGURED`` until ``JAYA_RESEARCH_API_KEYS`` is
    configured. An unauthenticated identity exists only in an explicitly marked
    test process.
    """

    test_principal = _test_principal_from_environment()
    body_limit = _positive_int(
        "JAYA_HTTP_MAX_BODY_BYTES",
        32 * 1024 * 1024,
    )
    policy = HttpSecurityPolicy(
        max_body_bytes=body_limit,
        public_paths=_PUBLIC_PATHS,
        test_mode=test_principal is not None,
        unauthenticated_test_principal=test_principal,
    )
    limiter = TokenBucketRateLimiter(
        refill_rate_per_second=_positive_float(
            "JAYA_HTTP_RATE_PER_SECOND",
            10.0,
        ),
        burst_capacity=float(
            _positive_int(
                "JAYA_HTTP_RATE_BURST",
                200,
            )
        ),
        max_identities=_positive_int(
            "JAYA_HTTP_RATE_MAX_IDENTITIES",
            10_000,
        ),
        idle_ttl_seconds=_positive_float(
            "JAYA_HTTP_RATE_IDLE_TTL_SECONDS",
            900.0,
        ),
    )
    cors = CorsPolicy.from_csv(
        os.getenv(
            "JAYA_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        )
    )
    return RuntimeHttpSecurity(
        authenticator=ApiKeyAuthenticator.from_environment(),
        policy=policy,
        rate_limiter=limiter,
        cors=cors,
    )


def _required_scope(method: str, path: str) -> str:
    normalized_method = method.upper()
    if (
        path in _ADMIN_EXACT_PATHS
        or path.startswith(_ADMIN_PATH_PREFIXES)
        or normalized_method == "DELETE"
    ):
        return "research:admin"
    if normalized_method in {"GET", "HEAD", "OPTIONS"}:
        return "research:read"
    return "research:write"


async def _json_workspace_id(request: Request) -> str | None:
    content_type = request.headers.get("content-type", "").partition(";")[0].strip()
    if content_type != "application/json":
        return None
    try:
        payload: Any = await request.json()
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    workspace_id = payload.get("workspace_id")
    return workspace_id if isinstance(workspace_id, str) else None


async def authorize_research_request(request: Request) -> None:
    """Authorize one API request and bind every declared workspace.

    Authentication and coarse rate/body enforcement happen in the ASGI
    middleware. This FastAPI dependency performs route-aware scope and
    workspace authorization before endpoint code runs.
    """

    path = request.url.path
    if path in _PUBLIC_PATHS:
        return

    principal = request_principal(request)
    require_scope(principal, _required_scope(request.method, path))

    workspace_ids = {
        candidate
        for candidate in (
            request.path_params.get("workspace_id"),
            request.query_params.get("workspace_id"),
            await _json_workspace_id(request),
        )
        if isinstance(candidate, str) and candidate
    }
    for workspace_id_value in workspace_ids:
        workspace_identity(principal, workspace_id_value)

