"""API-key authentication and workspace-scoped identity helpers."""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from starlette.requests import Request

from .errors import HttpSecurityError, SecurityConfigurationError, configuration_error

_DUMMY_SECRET_DIGEST = hashlib.sha256(b"jaya-invalid-api-key").digest()
_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SCOPE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:._-]{0,127}$")
_WORKSPACE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def validate_identifier(value: str, *, field_name: str) -> str:
    """Validate an identifier used in security state or audit output."""
    normalized = str(value or "").strip()
    if not _IDENTIFIER_PATTERN.fullmatch(normalized):
        raise configuration_error(
            f"{field_name} must be 1-64 safe identifier characters"
        )
    return normalized


def _validate_scope(scope: str) -> str:
    normalized = str(scope or "").strip()
    if normalized != "*" and not _SCOPE_PATTERN.fullmatch(normalized):
        raise configuration_error("Scopes must be '*' or safe identifier strings")
    return normalized


def _normalize_workspace_id(workspace_id: str) -> str:
    normalized = str(workspace_id or "").strip()
    if not _WORKSPACE_PATTERN.fullmatch(normalized):
        raise HttpSecurityError(403, "WORKSPACE_FORBIDDEN", "Workspace access denied")
    return normalized.casefold()


def _validate_configured_workspace(workspace_id: str) -> str:
    normalized = str(workspace_id or "").strip()
    if normalized == "*":
        return normalized
    if not _WORKSPACE_PATTERN.fullmatch(normalized):
        raise configuration_error(
            "Workspace grants must be '*' or safe workspace identifiers"
        )
    return normalized.casefold()


@dataclass(frozen=True)
class ApiPrincipal:
    """Authenticated API identity with explicit scopes and workspace grants."""

    subject: str
    credential_id: str
    scopes: frozenset[str]
    workspace_ids: frozenset[str]
    is_test_identity: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "subject",
            validate_identifier(self.subject, field_name="subject"),
        )
        object.__setattr__(
            self,
            "credential_id",
            validate_identifier(self.credential_id, field_name="credential_id"),
        )
        scopes = frozenset(_validate_scope(scope) for scope in self.scopes)
        workspaces = frozenset(
            _validate_configured_workspace(workspace_id)
            for workspace_id in self.workspace_ids
        )
        if not scopes:
            raise configuration_error("At least one API scope is required")
        if not workspaces:
            raise configuration_error("At least one workspace grant is required")
        object.__setattr__(self, "scopes", scopes)
        object.__setattr__(self, "workspace_ids", workspaces)

    def has_scope(self, required_scope: str) -> bool:
        """Return whether this identity owns the exact scope or wildcard scope."""
        normalized = _validate_scope(required_scope)
        return "*" in self.scopes or normalized in self.scopes

    def can_access_workspace(self, workspace_id: str) -> bool:
        """Return whether this identity may access the normalized workspace."""
        normalized = _normalize_workspace_id(workspace_id)
        return "*" in self.workspace_ids or normalized in self.workspace_ids


@dataclass(frozen=True)
class WorkspaceIdentity:
    """A principal proven to be authorized for one workspace."""

    subject: str
    credential_id: str
    workspace_id: str
    scopes: frozenset[str]
    is_test_identity: bool = False


@dataclass(frozen=True, repr=False)
class ApiKeyCredential:
    """An API credential that retains only a one-way secret digest."""

    key_id: str
    principal: ApiPrincipal
    _secret_digest: bytes

    @classmethod
    def from_secret(
        cls,
        *,
        key_id: str,
        secret: str,
        subject: str,
        scopes: Iterable[str],
        workspace_ids: Iterable[str],
    ) -> ApiKeyCredential:
        """Build a credential without retaining or exposing the plaintext key."""
        normalized_key_id = validate_identifier(key_id, field_name="key_id")
        if not isinstance(secret, str):
            raise configuration_error("API key secrets must be strings")
        encoded_secret = secret.encode("utf-8")
        if (
            len(encoded_secret) < 32
            or len(encoded_secret) > 4096
            or secret != secret.strip()
            or any(character.isspace() or ord(character) < 32 for character in secret)
        ):
            raise configuration_error(
                "API key secrets must contain 32-4096 non-whitespace characters"
            )
        principal = ApiPrincipal(
            subject=subject,
            credential_id=normalized_key_id,
            scopes=frozenset(scopes),
            workspace_ids=frozenset(workspace_ids),
        )
        return cls(
            key_id=normalized_key_id,
            principal=principal,
            _secret_digest=hashlib.sha256(encoded_secret).digest(),
        )

    def __repr__(self) -> str:
        return f"ApiKeyCredential(key_id={self.key_id!r}, principal={self.principal!r})"


class ApiKeyAuthenticator:
    """Authenticate API keys using fixed-size, constant-time digest checks."""

    def __init__(self, credentials: Iterable[ApiKeyCredential] = ()) -> None:
        configured = tuple(credentials)
        key_ids = [credential.key_id for credential in configured]
        digests = [credential._secret_digest for credential in configured]
        if len(key_ids) != len(set(key_ids)):
            raise configuration_error("Duplicate API credential identifiers")
        if len(digests) != len(set(digests)):
            raise configuration_error("Duplicate API key secrets")
        self._credentials = configured

    @property
    def configured(self) -> bool:
        """Return whether at least one production credential is configured."""
        return bool(self._credentials)

    @classmethod
    def from_environment(
        cls,
        variable_name: str = "JAYA_RESEARCH_API_KEYS",
    ) -> ApiKeyAuthenticator:
        """Load a JSON credential list, or remain fail-closed when it is absent."""
        raw_value = os.getenv(variable_name)
        if raw_value is None or not raw_value.strip():
            return cls()
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise configuration_error(
                f"{variable_name} must contain valid credential JSON"
            ) from exc
        if not isinstance(payload, list):
            raise configuration_error(f"{variable_name} must contain a JSON list")

        credentials: list[ApiKeyCredential] = []
        try:
            for item in payload:
                if not isinstance(item, Mapping):
                    raise TypeError
                scopes = item["scopes"]
                workspace_ids = item["workspace_ids"]
                if isinstance(scopes, str) or isinstance(workspace_ids, str):
                    raise TypeError
                credentials.append(
                    ApiKeyCredential.from_secret(
                        key_id=item["key_id"],
                        secret=item["secret"],
                        subject=item["subject"],
                        scopes=scopes,
                        workspace_ids=workspace_ids,
                    )
                )
        except (KeyError, TypeError, SecurityConfigurationError) as exc:
            raise configuration_error(
                f"{variable_name} contains an invalid credential entry"
            ) from exc
        return cls(credentials)

    def authenticate(self, presented_secret: str) -> ApiPrincipal:
        """Authenticate without short-circuiting credential comparisons."""
        if not self.configured:
            raise HttpSecurityError(
                503,
                "AUTH_NOT_CONFIGURED",
                "API authentication is unavailable",
            )

        is_valid_input = (
            isinstance(presented_secret, str)
            and presented_secret == presented_secret.strip()
            and 0 < len(presented_secret.encode("utf-8")) <= 4096
            and not any(
                character.isspace() or ord(character) < 32
                for character in presented_secret
            )
        )
        candidate_digest = (
            hashlib.sha256(presented_secret.encode("utf-8")).digest()
            if is_valid_input
            else _DUMMY_SECRET_DIGEST
        )

        matched_principal: ApiPrincipal | None = None
        for credential in self._credentials:
            matches = secrets.compare_digest(
                credential._secret_digest,
                candidate_digest,
            )
            if matches:
                matched_principal = credential.principal

        if matched_principal is None:
            raise HttpSecurityError(
                401,
                "INVALID_API_KEY",
                "Authentication credentials are invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return matched_principal


def require_scope(principal: ApiPrincipal, required_scope: str) -> None:
    """Raise a client-safe 403 when a principal lacks a required scope."""
    if not principal.has_scope(required_scope):
        raise HttpSecurityError(403, "SCOPE_FORBIDDEN", "Permission denied")


def workspace_identity(
    principal: ApiPrincipal,
    workspace_id: str,
    *,
    required_scopes: Iterable[str] = (),
) -> WorkspaceIdentity:
    """Bind an authenticated principal to an authorized workspace."""
    normalized_workspace_id = _normalize_workspace_id(workspace_id)
    for required_scope in required_scopes:
        require_scope(principal, required_scope)
    if not principal.can_access_workspace(normalized_workspace_id):
        raise HttpSecurityError(
            403,
            "WORKSPACE_FORBIDDEN",
            "Workspace access denied",
        )
    return WorkspaceIdentity(
        subject=principal.subject,
        credential_id=principal.credential_id,
        workspace_id=normalized_workspace_id,
        scopes=principal.scopes,
        is_test_identity=principal.is_test_identity,
    )


def request_principal(
    request: Request,
    *,
    state_key: str = "jaya_principal",
) -> ApiPrincipal:
    """Read the authenticated principal attached by the middleware."""
    principal = getattr(request.state, state_key, None)
    if not isinstance(principal, ApiPrincipal):
        raise HttpSecurityError(
            401,
            "AUTHENTICATION_REQUIRED",
            "Authentication is required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return principal


def require_workspace_identity(
    request: Request,
    workspace_id: str,
    *,
    required_scopes: Iterable[str] = (),
    state_key: str = "jaya_principal",
) -> WorkspaceIdentity:
    """Resolve a request identity and authorize it for one workspace."""
    return workspace_identity(
        request_principal(request, state_key=state_key),
        workspace_id,
        required_scopes=required_scopes,
    )
