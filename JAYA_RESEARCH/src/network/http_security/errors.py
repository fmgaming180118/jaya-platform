"""Client-safe errors and redaction helpers for HTTP security."""

from __future__ import annotations

import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

_SECRET_FIELD_PATTERN = re.compile(
    r"(?i)(api[_-]?key|authorization|password|secret|token)"
)
_BEARER_PATTERN = re.compile(r"(?i)\b(bearer\s+)[^\s,;]+")
_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|authorization|password|secret|token)"
    r"(\s*[:=]\s*)([^\s,;&]+)"
)
_LONG_CREDENTIAL_PATTERN = re.compile(r"(?<![A-Za-z0-9._~+/=-])[A-Za-z0-9._~+/=-]{24,}")


class SecurityConfigurationError(ValueError):
    """Raised when HTTP security configuration is unsafe or malformed."""


class HttpSecurityError(RuntimeError):
    """A client-safe HTTP rejection raised by this package."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.safe_message = message
        self.headers = MappingProxyType(dict(headers or {}))


def redact_sensitive(value: Any) -> Any:
    """Return a log-safe copy with common secret fields and tokens redacted."""
    if isinstance(value, Mapping):
        return {
            str(key): (
                "[REDACTED]"
                if _SECRET_FIELD_PATTERN.search(str(key))
                else redact_sensitive(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        redacted = _BEARER_PATTERN.sub(r"\1[REDACTED]", value)
        redacted = _ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", redacted)
        redacted = _LONG_CREDENTIAL_PATTERN.sub("[REDACTED]", redacted)
        return "".join(
            character if character.isprintable() else "?" for character in redacted
        )[:512]
    return value


def configuration_error(message: str) -> SecurityConfigurationError:
    """Build a configuration exception without embedding configuration values."""
    return SecurityConfigurationError(message)
