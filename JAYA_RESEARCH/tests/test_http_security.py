"""Unit tests for the standalone SEC-003 HTTP security module."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from network.http_security import (  # noqa: E402
    ApiKeyAuthenticator,
    ApiKeyCredential,
    ApiPrincipal,
    CorsPolicy,
    HttpSecurityMiddleware,
    HttpSecurityPolicy,
    SecurityConfigurationError,
    TokenBucketRateLimiter,
    redact_sensitive,
    require_workspace_identity,
)
from network.http_security import identity as http_security_identity  # noqa: E402

API_KEY = "research-client-key-" + ("a" * 32)
SECOND_API_KEY = "research-client-key-" + ("b" * 32)


def _credential(
    *,
    key_id: str = "research-client",
    secret: str = API_KEY,
    scopes: frozenset[str] = frozenset({"research:read"}),
    workspace_ids: frozenset[str] = frozenset({"alpha"}),
) -> ApiKeyCredential:
    return ApiKeyCredential.from_secret(
        key_id=key_id,
        secret=secret,
        subject=f"{key_id}-subject",
        scopes=scopes,
        workspace_ids=workspace_ids,
    )


def _client(
    *,
    credentials: tuple[ApiKeyCredential, ...] | None = None,
    max_body_bytes: int = 128,
    limiter: TokenBucketRateLimiter | None = None,
    policy: HttpSecurityPolicy | None = None,
    logger: logging.Logger | None = None,
) -> TestClient:
    app = FastAPI()

    @app.get("/workspaces/{workspace_id}")
    async def read_workspace(workspace_id: str, request: Request):
        identity = require_workspace_identity(
            request,
            workspace_id,
            required_scopes={"research:read"},
        )
        return {
            "subject": identity.subject,
            "workspace_id": identity.workspace_id,
        }

    @app.post("/workspaces/{workspace_id}")
    async def write_workspace(workspace_id: str, request: Request):
        identity = require_workspace_identity(
            request,
            workspace_id,
            required_scopes={"research:write"},
        )
        return {"workspace_id": identity.workspace_id}

    @app.post("/echo")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    app.add_middleware(
        HttpSecurityMiddleware,
        authenticator=ApiKeyAuthenticator(
            credentials if credentials is not None else (_credential(),)
        ),
        policy=policy or HttpSecurityPolicy(max_body_bytes=max_body_bytes),
        rate_limiter=limiter,
        logger=logger,
    )
    return TestClient(app)


def _authorization(secret: str = API_KEY) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret}"}


def test_missing_and_invalid_api_keys_return_401() -> None:
    client = _client()

    missing = client.get("/workspaces/alpha")
    invalid = client.get(
        "/workspaces/alpha",
        headers=_authorization("invalid-" + ("x" * 32)),
    )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.headers["www-authenticate"] == "Bearer"
    assert invalid.json()["error"]["code"] == "INVALID_API_KEY"


def test_workspace_and_scope_grants_return_403_without_cross_tenant_access() -> None:
    client = _client()

    allowed = client.get("/workspaces/ALPHA", headers=_authorization())
    other_workspace = client.get("/workspaces/beta", headers=_authorization())
    missing_scope = client.post("/workspaces/alpha", headers=_authorization())

    assert allowed.status_code == 200
    assert allowed.json()["workspace_id"] == "alpha"
    assert other_workspace.status_code == 403
    assert other_workspace.json()["error"]["code"] == "WORKSPACE_FORBIDDEN"
    assert missing_scope.status_code == 403
    assert missing_scope.json()["error"]["code"] == "SCOPE_FORBIDDEN"


def test_token_bucket_returns_429_with_retry_after() -> None:
    limiter = TokenBucketRateLimiter(
        refill_rate_per_second=0.01,
        burst_capacity=1,
    )
    client = _client(limiter=limiter)

    first = client.get("/workspaces/alpha", headers=_authorization())
    limited = client.get("/workspaces/alpha", headers=_authorization())

    assert first.status_code == 200
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
    assert int(limited.headers["retry-after"]) >= 1


def test_content_length_and_actual_body_are_limited_with_413() -> None:
    client = _client(max_body_bytes=8)

    declared_too_large = client.post(
        "/echo",
        content=b"x" * 9,
        headers=_authorization(),
    )
    streamed_too_large = client.post(
        "/echo",
        content=b"x" * 9,
        headers={
            **_authorization(),
            "Content-Length": "1",
        },
    )

    assert declared_too_large.status_code == 413
    assert streamed_too_large.status_code == 413
    assert streamed_too_large.json()["error"]["code"] == "REQUEST_BODY_TOO_LARGE"


def test_authenticator_compares_every_digest_even_after_a_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    authenticator = ApiKeyAuthenticator(
        (
            _credential(),
            _credential(
                key_id="second-client",
                secret=SECOND_API_KEY,
                workspace_ids=frozenset({"beta"}),
            ),
        )
    )
    original_compare = http_security_identity.secrets.compare_digest
    calls: list[tuple[bytes, bytes]] = []

    def recording_compare(left: bytes, right: bytes) -> bool:
        calls.append((left, right))
        return original_compare(left, right)

    monkeypatch.setattr(
        http_security_identity.secrets,
        "compare_digest",
        recording_compare,
    )

    principal = authenticator.authenticate(API_KEY)

    assert principal.credential_id == "research-client"
    assert len(calls) == 2


def test_empty_production_authenticator_fails_closed() -> None:
    client = _client(credentials=())

    response = client.get("/workspaces/alpha")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"


def test_unauthenticated_bypass_requires_explicit_test_mode() -> None:
    test_principal = ApiPrincipal(
        subject="test-subject",
        credential_id="test-credential",
        scopes=frozenset({"research:read"}),
        workspace_ids=frozenset({"alpha"}),
        is_test_identity=True,
    )

    with pytest.raises(SecurityConfigurationError):
        HttpSecurityPolicy(unauthenticated_test_principal=test_principal)

    policy = HttpSecurityPolicy(
        test_mode=True,
        unauthenticated_test_principal=test_principal,
    )
    response = _client(credentials=(), policy=policy).get("/workspaces/alpha")

    assert response.status_code == 200
    assert response.json()["subject"] == "test-subject"


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.test",
        "https://user@example.test",
        "https://example.test/private",
        "https://example.test?debug=1",
        "file:///tmp/ui",
    ],
)
def test_cors_policy_rejects_wildcards_and_non_origin_urls(origin: str) -> None:
    with pytest.raises(SecurityConfigurationError):
        CorsPolicy(allow_origins=(origin,))


def test_cors_policy_normalizes_allowlist_for_starlette() -> None:
    policy = CorsPolicy.from_csv("HTTPS://UI.EXAMPLE.TEST:443, http://localhost:5173/")

    assert policy.as_middleware_kwargs() == {
        "allow_origins": [
            "https://ui.example.test:443",
            "http://localhost:5173",
        ],
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "DELETE", "OPTIONS"],
        "allow_headers": [
            "Authorization",
            "Content-Type",
            "X-API-Key",
            "X-Request-ID",
        ],
    }


def test_security_errors_and_logs_never_echo_credentials(
    caplog: pytest.LogCaptureFixture,
) -> None:
    logger = logging.getLogger("test.http-security")
    secret = "do-not-log-this-secret-" + ("z" * 32)
    client = _client(logger=logger)

    with caplog.at_level(logging.WARNING, logger=logger.name):
        response = client.get(
            "/workspaces/alpha",
            headers={"X-API-Key": secret},
        )

    assert response.status_code == 401
    assert secret not in response.text
    assert secret not in caplog.text
    assert redact_sensitive(
        {
            "authorization": f"Bearer {secret}",
            "message": f"api_key={secret}",
        }
    ) == {
        "authorization": "[REDACTED]",
        "message": "api_key=[REDACTED]",
    }
