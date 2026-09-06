"""Compatibility boundary for Pillar 6.

Automatic entropy-driven task injection was removed because it bypassed owner
authorization and Cognitive Silence. New code must use
``engine.spontaneity.SpontaneityEngine.explore`` with an explicit request.
"""

from __future__ import annotations

from typing import Any


class EntropySpark:
    """Disabled legacy scheduler retained only for import compatibility."""

    def __init__(self, idle_threshold: float = 15.0, cooldown: float = 30.0) -> None:
        if idle_threshold < 0 or cooldown < 0:
            raise ValueError("idle_threshold and cooldown cannot be negative")
        self.idle_threshold = float(idle_threshold)
        self.cooldown = float(cooldown)
        self._blocked_ticks = 0

    def tick(self, twin: Any) -> None:
        """Record the blocked legacy trigger without queueing or executing work."""
        self._blocked_ticks += 1

    def status(self) -> dict[str, object]:
        return {
            "available": False,
            "status": "EXPLICIT_AUTHORIZATION_REQUIRED",
            "automatic_generation": False,
            "blocked_ticks": self._blocked_ticks,
            "idle_threshold": self.idle_threshold,
            "cooldown": self.cooldown,
        }


__all__ = ["EntropySpark"]
