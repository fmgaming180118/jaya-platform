"""Public injection boundary for effects requested by JAYA Research clients."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

_SAFE_ACTION = re.compile(r"^[a-z][a-z0-9_.-]{2,127}$")
_SAFE_PROFILE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")


class CapabilityBoundaryError(RuntimeError):
    """Base error for denied or unavailable external capabilities."""


class CapabilityUnavailableError(CapabilityBoundaryError):
    """Raised when no authorized gateway was injected."""


class ArbitraryExecutionRejected(CapabilityBoundaryError):
    """Raised when a caller supplies shell text or source code for execution."""


class InvalidCapabilityRequest(CapabilityBoundaryError):
    """Raised when a structured request violates the public contract."""


@dataclass(frozen=True, slots=True)
class CapabilityRequest:
    """Structured request containing no shell command or source code."""

    action: str
    arguments: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not _SAFE_ACTION.fullmatch(self.action):
            raise InvalidCapabilityRequest("invalid capability action")
        if not isinstance(self.arguments, Mapping):
            raise InvalidCapabilityRequest("capability arguments must be an object")


class CapabilityGateway(Protocol):
    """Implemented by an authorized Agent/OS adapter outside Research."""

    def request(self, request: CapabilityRequest) -> Mapping[str, Any]:
        """Authorize and execute one structured, auditable request."""
        ...


def require_profile(value: str) -> str:
    """Validate an allowlisted execution-profile identifier."""
    profile = str(value or "").strip()
    if not _SAFE_PROFILE.fullmatch(profile):
        raise InvalidCapabilityRequest("invalid execution profile")
    return profile


def request_capability(
    gateway: CapabilityGateway | None,
    *,
    action: str,
    arguments: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Fail closed unless an explicit public gateway was injected."""
    if gateway is None:
        raise CapabilityUnavailableError(
            f"capability {action!r} is unavailable without an injected gateway"
        )
    result = gateway.request(CapabilityRequest(action=action, arguments=arguments))
    if not isinstance(result, Mapping):
        raise CapabilityBoundaryError("capability gateway returned an invalid receipt")
    return dict(result)
