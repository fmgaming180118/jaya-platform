"""
budget.py — Resource budget calculator for task execution.
"""

from __future__ import annotations

from src.cognitive.contracts import ResourceBudget
from src.identity.models import NodeClass
from .profiler import ResourceProfile


class ResourceBudgetCalculator:
    """Calculates resource budget for plans based on ResourceProfile."""

    def calculate(self, profile: ResourceProfile, urgency: str = "NORMAL") -> ResourceBudget:
        # Default baseline
        max_mem = min(profile.available_memory_mb // 2, 2048)
        max_mem = max(max_mem, 128)  # at least 128MB budget

        max_duration = 30
        if urgency == "HIGH":
            max_duration = 15
        elif urgency == "CRITICAL":
            max_duration = 5

        allow_network = profile.network_available
        allow_offload = profile.network_available and profile.node_class in (
            NodeClass.EDGE,
            NodeClass.STANDARD,
            NodeClass.CONSTRAINED,
        )

        if profile.power_mode == "SAVER" or profile.node_class == NodeClass.CONSTRAINED:
            max_mem = min(max_mem, 256)
            allow_offload = False

        return ResourceBudget(
            max_memory_mb=max_mem,
            max_duration_seconds=max_duration,
            allow_network=allow_network,
            allow_remote_offload=allow_offload,
        )
