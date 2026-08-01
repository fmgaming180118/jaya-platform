"""
modes.py — Execution mode controller and transition validator.
"""

from __future__ import annotations

from enum import Enum
from typing import Set

from src.identity.models import NodeClass
from .profiler import ResourceProfile


class ExecutionMode(str, Enum):
    ONLINE_FULL = "ONLINE_FULL"
    ONLINE_DEGRADED = "ONLINE_DEGRADED"
    OFFLINE_AUTONOMOUS = "OFFLINE_AUTONOMOUS"
    OFFLINE_SAFE = "OFFLINE_SAFE"
    EMERGENCY = "EMERGENCY"


class InvalidModeTransitionError(Exception):
    """Raised when an invalid mode transition is requested."""


_ALLOWED_TRANSITIONS: dict[ExecutionMode, Set[ExecutionMode]] = {
    ExecutionMode.ONLINE_FULL: {
        ExecutionMode.ONLINE_FULL,
        ExecutionMode.ONLINE_DEGRADED,
        ExecutionMode.OFFLINE_AUTONOMOUS,
        ExecutionMode.OFFLINE_SAFE,
        ExecutionMode.EMERGENCY,
    },
    ExecutionMode.ONLINE_DEGRADED: {
        ExecutionMode.ONLINE_FULL,
        ExecutionMode.ONLINE_DEGRADED,
        ExecutionMode.OFFLINE_AUTONOMOUS,
        ExecutionMode.OFFLINE_SAFE,
        ExecutionMode.EMERGENCY,
    },
    ExecutionMode.OFFLINE_AUTONOMOUS: {
        ExecutionMode.ONLINE_FULL,
        ExecutionMode.ONLINE_DEGRADED,
        ExecutionMode.OFFLINE_AUTONOMOUS,
        ExecutionMode.OFFLINE_SAFE,
        ExecutionMode.EMERGENCY,
    },
    ExecutionMode.OFFLINE_SAFE: {
        ExecutionMode.ONLINE_FULL,
        ExecutionMode.ONLINE_DEGRADED,
        ExecutionMode.OFFLINE_AUTONOMOUS,
        ExecutionMode.OFFLINE_SAFE,
        ExecutionMode.EMERGENCY,
    },
    ExecutionMode.EMERGENCY: {
        ExecutionMode.OFFLINE_SAFE,
        ExecutionMode.ONLINE_DEGRADED,
        ExecutionMode.EMERGENCY,
    },
}


class ExecutionModeController:
    """Controls and validates system execution mode transitions."""

    def __init__(self, initial_mode: ExecutionMode = ExecutionMode.ONLINE_FULL) -> None:
        self._current_mode = initial_mode

    @property
    def current_mode(self) -> ExecutionMode:
        return self._current_mode

    def transition_to(self, new_mode: ExecutionMode) -> ExecutionMode:
        allowed = _ALLOWED_TRANSITIONS.get(self._current_mode, set())
        if new_mode not in allowed:
            raise InvalidModeTransitionError(
                f"Cannot transition from {self._current_mode.value} to {new_mode.value}"
            )
        self._current_mode = new_mode
        return self._current_mode

    def auto_determine_mode(self, profile: ResourceProfile) -> ExecutionMode:
        """Determines recommended execution mode based on ResourceProfile."""
        if profile.power_mode == "CRITICAL" or profile.available_memory_mb < 64:
            target = ExecutionMode.EMERGENCY
        elif not profile.network_available:
            if profile.node_class in (NodeClass.CENTRAL, NodeClass.STANDARD, NodeClass.MISSION):
                target = ExecutionMode.OFFLINE_AUTONOMOUS
            else:
                target = ExecutionMode.OFFLINE_SAFE
        else:
            if profile.available_memory_mb < 512:
                target = ExecutionMode.ONLINE_DEGRADED
            else:
                target = ExecutionMode.ONLINE_FULL

        self.transition_to(target)
        return self._current_mode
