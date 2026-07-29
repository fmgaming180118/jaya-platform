"""Agent adapter for the capability sandbox owned by JAYA OS."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parents[3]
_OS_SOURCE_DIR = _ROOT_DIR / "JAYA_OS" / "src"
if str(_OS_SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(_OS_SOURCE_DIR))

from jaya_os.capability_sandbox import (  # noqa: E402
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
