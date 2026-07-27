"""ASGI middleware composing HTTP request security controls."""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .errors import HttpSecurityError, configuration_error, redact_sensitive
from .identity import ApiKeyAuthenticator, ApiPrincipal, validate_identifier
from .rate_limit import TokenBucketRateLimiter

_AUTHORIZATION_HEADER = b"authorization"
_API_KEY_HEADER = b"x-api-key"
_CONTENT_LENGTH_HEADER = b"content-length"


@dataclass(frozen=True)
class HttpSecurityPolicy:
    """Validated middleware behavior.

    Production defaults are fail-closed. An unauthenticated identity is accepted
    only when both explicit test mode and a test-marked principal are configured.
    """

    max_body_bytes: int = 10 * 1024 * 1024
    public_paths: frozenset[str] = frozenset()
    allow_unauthenticated_options: bool = True
    principal_state_key: str = "jaya_principal"
    test_mode: bool = False
    unauthenticated_test_principal: ApiPrincipal | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.max_body_bytes, bool)
            or not isinstance(self.max_body_bytes, int)
            or self.max_body_bytes < 1
        ):
            raise configuration_error("HTTP body limit must be a positive integer")
        validate_identifier(
            self.principal_state_key,
            field_name="principal_state_key",
        )
        public_paths = frozenset(self.public_paths)
        for path in public_paths:
            if (
                not isinstance(path, str)
                or not path.startswith("/")
                or "?" in path
                or "#" in path
                or any(ord(character) < 32 for character in path)
            ):
                raise configuration_error(
                    "Public paths must be exact absolute URL paths"
                )
        object.__setattr__(self, "public_paths", public_paths)
        if self.unauthenticated_test_principal is not None and not self.test_mode:
            raise configuration_error(
                "Unauthenticated requests can only be enabled in explicit test mode"
            )
        if (
            self.unauthenticated_test_principal is not None
            and not self.unauthenticated_test_principal.is_test_identity
        ):
            raise configuration_error(
                "Test bypass requires an identity marked as a test identity"
            )


class HttpSecurityMiddleware:
    """Enforce body limits, API-key auth, and token-bucket limits."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        authenticator: ApiKeyAuthenticator,
        policy: HttpSecurityPolicy | None = None,
        rate_limiter: TokenBucketRateLimiter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self.app = app
        self.authenticator = authenticator
        self.policy = policy or HttpSecurityPolicy()
        self.rate_limiter = rate_limiter
        self.logger = logger or logging.getLogger("jaya_research.http_security")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            declared_length = self._validate_content_length(scope)
            if (
                declared_length is not None
                and declared_length > self.policy.max_body_bytes
            ):
                raise self._body_too_large()

            path = str(scope.get("path", ""))
            is_public = path in self.policy.public_paths
            is_public_options = (
                self.policy.allow_unauthenticated_options
                and str(scope.get("method", "")).upper() == "OPTIONS"
            )
            if not is_public and not is_public_options:
                principal = self._authenticate_scope(scope)
                state = scope.get("state")
                if state is None:
                    state = {}
                    scope["state"] = state
                if not isinstance(state, dict):
                    raise HttpSecurityError(
                        500,
                        "INVALID_ASGI_STATE",
                        "HTTP security state is unavailable",
                    )
                state[self.policy.principal_state_key] = principal
                self._enforce_rate_limit(
                    f"credential:{principal.credential_id}",
                )

            buffered_receive = await self._bounded_receive(receive, declared_length)
            await self.app(scope, buffered_receive, tracked_send)
        except HttpSecurityError as exc:
            if response_started:
                raise
            self._log_rejection(scope, exc)
            response = JSONResponse(
                {
                    "error": {
                        "code": exc.code,
                        "message": redact_sensitive(exc.safe_message),
                    }
                },
                status_code=exc.status_code,
                headers=dict(exc.headers),
            )
            await response(scope, receive, send)

    def _authenticate_scope(self, scope: Scope) -> ApiPrincipal:
        test_principal = self.policy.unauthenticated_test_principal
        if not self.authenticator.configured and test_principal is None:
            raise HttpSecurityError(
                503,
                "AUTH_NOT_CONFIGURED",
                "API authentication is unavailable",
            )

        presented_secret = self._extract_api_key(scope)
        if presented_secret is None and test_principal is not None:
            return test_principal
        self._enforce_rate_limit(self._anonymous_rate_key(scope))
        if presented_secret is None:
            raise HttpSecurityError(
                401,
                "AUTHENTICATION_REQUIRED",
                "Authentication is required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return self.authenticator.authenticate(presented_secret)

    @staticmethod
    def _extract_api_key(scope: Scope) -> str | None:
        authorization_values: list[str] = []
        api_key_values: list[str] = []
        for raw_name, raw_value in scope.get("headers", []):
            name = raw_name.lower()
            if name not in {_AUTHORIZATION_HEADER, _API_KEY_HEADER}:
                continue
            value = raw_value.decode("latin-1")
            if name == _AUTHORIZATION_HEADER:
                authorization_values.append(value)
            else:
                api_key_values.append(value)

        if (
            len(authorization_values) > 1
            or len(api_key_values) > 1
            or (authorization_values and api_key_values)
        ):
            raise HttpSecurityError(
                401,
                "AMBIGUOUS_AUTH_HEADER",
                "Authentication credentials are invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if api_key_values:
            return api_key_values[0]
        if not authorization_values:
            return None

        scheme, separator, credential = authorization_values[0].partition(" ")
        if (
            not separator
            or scheme.casefold() != "bearer"
            or not credential
            or " " in credential
        ):
            raise HttpSecurityError(
                401,
                "INVALID_AUTH_HEADER",
                "Authentication credentials are invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return credential

    def _enforce_rate_limit(self, identity_key: str) -> None:
        if self.rate_limiter is None:
            return
        decision = self.rate_limiter.consume(identity_key)
        if decision.allowed:
            return
        retry_after = max(1, math.ceil(decision.retry_after_seconds))
        raise HttpSecurityError(
            429,
            "RATE_LIMIT_EXCEEDED",
            "Request rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    @staticmethod
    def _anonymous_rate_key(scope: Scope) -> str:
        client = scope.get("client")
        host = str(client[0]) if client else "unknown"
        digest = hashlib.sha256(host.encode("utf-8", errors="replace")).hexdigest()[:16]
        return f"anonymous:{digest}"

    @staticmethod
    def _validate_content_length(scope: Scope) -> int | None:
        values: list[bytes] = [
            raw_value
            for raw_name, raw_value in scope.get("headers", [])
            if raw_name.lower() == _CONTENT_LENGTH_HEADER
        ]
        if not values:
            return None
        if len(values) != 1:
            raise HttpSecurityError(
                400,
                "INVALID_CONTENT_LENGTH",
                "Content-Length header is invalid",
            )
        try:
            decoded = values[0].decode("ascii")
        except UnicodeDecodeError as exc:
            raise HttpSecurityError(
                400,
                "INVALID_CONTENT_LENGTH",
                "Content-Length header is invalid",
            ) from exc
        if not decoded or len(decoded) > 20 or not decoded.isdecimal():
            raise HttpSecurityError(
                400,
                "INVALID_CONTENT_LENGTH",
                "Content-Length header is invalid",
            )
        return int(decoded)

    async def _bounded_receive(
        self,
        receive: Receive,
        declared_length: int | None,
    ) -> Receive:
        messages: list[Message] = []
        total_bytes = 0
        completed = False
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] == "http.disconnect":
                break
            if message["type"] != "http.request":
                raise HttpSecurityError(
                    400,
                    "INVALID_HTTP_BODY",
                    "Request body stream is invalid",
                )
            body = message.get("body", b"")
            if not isinstance(body, bytes):
                raise HttpSecurityError(
                    400,
                    "INVALID_HTTP_BODY",
                    "Request body stream is invalid",
                )
            total_bytes += len(body)
            if total_bytes > self.policy.max_body_bytes:
                raise self._body_too_large()
            if not message.get("more_body", False):
                completed = True
                break

        if completed and declared_length is not None and total_bytes != declared_length:
            raise HttpSecurityError(
                400,
                "CONTENT_LENGTH_MISMATCH",
                "Content-Length does not match the request body",
            )

        index = 0

        async def replay() -> Message:
            nonlocal index
            if index < len(messages):
                message = messages[index]
                index += 1
                return message
            return {"type": "http.request", "body": b"", "more_body": False}

        return replay

    @staticmethod
    def _body_too_large() -> HttpSecurityError:
        return HttpSecurityError(
            413,
            "REQUEST_BODY_TOO_LARGE",
            "Request body exceeds the configured limit",
        )

    def _log_rejection(self, scope: Scope, exc: HttpSecurityError) -> None:
        self.logger.warning(
            "HTTP security rejection code=%s status=%d method=%s path=%s",
            exc.code,
            exc.status_code,
            redact_sensitive(str(scope.get("method", "")))[:16],
            redact_sensitive(str(scope.get("path", ""))),
        )
