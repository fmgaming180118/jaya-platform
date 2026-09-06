"""Validated resource-budget policy for task execution."""

from __future__ import annotations

from dataclasses import dataclass

from jaya_core.cognitive.contracts import ResourceBudget
from jaya_core.identity.models import NodeClass

from .profiler import ResourceProfile


@dataclass(frozen=True, slots=True)
class ResourceBudgetPolicy:
    memory_fraction: float = 0.5
    maximum_memory_mb: int = 2_048
    minimum_memory_mb: int = 128
    unknown_memory_budget_mb: int = 64
    normal_duration_seconds: int = 30
    high_duration_seconds: int = 15
    critical_duration_seconds: int = 5
    saver_memory_cap_mb: int = 256

    def __post_init__(self) -> None:
        if not 0 < self.memory_fraction <= 1:
            raise ValueError("memory_fraction must be in (0, 1]")
        integer_values = (
            self.maximum_memory_mb,
            self.minimum_memory_mb,
            self.unknown_memory_budget_mb,
            self.normal_duration_seconds,
            self.high_duration_seconds,
            self.critical_duration_seconds,
            self.saver_memory_cap_mb,
        )
        if any(value <= 0 for value in integer_values):
            raise ValueError("resource budget policy values must be positive")
        if self.minimum_memory_mb > self.maximum_memory_mb:
            raise ValueError("minimum_memory_mb must not exceed maximum_memory_mb")


class ResourceBudgetCalculator:
    """Calculate a conservative budget from observed metrics and policy."""

    def __init__(self, policy: ResourceBudgetPolicy | None = None) -> None:
        self.policy = policy or ResourceBudgetPolicy()

    def calculate(
        self,
        profile: ResourceProfile,
        urgency: str = "NORMAL",
    ) -> ResourceBudget:
        normalized_urgency = urgency.strip().upper()
        durations = {
            "NORMAL": self.policy.normal_duration_seconds,
            "HIGH": self.policy.high_duration_seconds,
            "CRITICAL": self.policy.critical_duration_seconds,
        }
        if normalized_urgency not in durations:
            raise ValueError(f"unsupported urgency: {urgency!r}")

        if profile.available_memory_mb is None:
            max_memory_mb = self.policy.unknown_memory_budget_mb
        else:
            calculated = int(profile.available_memory_mb * self.policy.memory_fraction)
            max_memory_mb = min(calculated, self.policy.maximum_memory_mb)
            max_memory_mb = max(max_memory_mb, self.policy.minimum_memory_mb)

        allow_network = profile.network_available is True
        allow_offload = allow_network and profile.node_class in (
            NodeClass.EDGE,
            NodeClass.STANDARD,
            NodeClass.CONSTRAINED,
        )

        if profile.power_mode in {"SAVER", "CRITICAL", "UNKNOWN"}:
            max_memory_mb = min(max_memory_mb, self.policy.saver_memory_cap_mb)
            allow_offload = False

        return ResourceBudget(
            max_memory_mb=max_memory_mb,
            max_duration_seconds=durations[normalized_urgency],
            allow_network=allow_network,
            allow_remote_offload=allow_offload,
        )


__all__ = ["ResourceBudgetCalculator", "ResourceBudgetPolicy"]
