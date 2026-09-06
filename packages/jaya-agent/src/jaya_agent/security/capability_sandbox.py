"""Agent adapter for the capability sandbox owned by JAYA OS."""

from __future__ import annotations

from jaya_os.capability_sandbox import (
    ACTIVE_CAPABILITY,
    ActionPolicy,
    CapabilityDenied,
    CapabilityExecution,
    CapabilitySandbox,
    ProcessProfile,
    require_active_capability,
)

__all__ = [
    "ACTIVE_CAPABILITY",
    "ActionPolicy",
    "CapabilityDenied",
    "CapabilityExecution",
    "CapabilitySandbox",
    "ProcessProfile",
    "require_active_capability",
]
