"""Dependency-neutral privacy redaction shared by security and observability."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

_SENSITIVE_KEY = re.compile(
    r"password|secret|api[_-]?key|token|credential|private[_-]?key|"
    r"authorization|cookie|session[_-]?id|passport|credit[_-]?card|pin",
    re.IGNORECASE,
)
_MESSAGE_SECRET = re.compile(
    r"(?i)\b(password|secret|api[_-]?key|token|credential|private[_-]?key|"
    r"authorization|cookie|pin)\s*[:=]\s*([^\s,;]+)"
)


def redact_private(value: Any) -> Any:
    """Recursively redact secrets, including values embedded in message text."""

    if isinstance(value, Mapping):
        return {
            str(key): (
                "***REDACTED***"
                if _SENSITIVE_KEY.search(str(key))
                else redact_private(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_private(item) for item in value]
    if isinstance(value, str):
        return _MESSAGE_SECRET.sub(r"\1=***REDACTED***", value)
    return value


__all__ = ["redact_private"]
