"""Capability-gated maintenance of Agent-owned installed memory."""

from __future__ import annotations

from collections.abc import Mapping

from security.capability_sandbox import require_active_capability
from skills.adapters import MemoryMaintenanceAdapter, SkillAdapterUnavailable
from skills.base_skill import Skill, skill_action

MEMORY_RESOURCE = "system://memory"


class MemoryManagerSkill(Skill):
    """Run memory maintenance only through an explicitly injected adapter."""

    name = "memory_skill"
    description = "SQLite and RAM maintenance"

    def __init__(self, manager: MemoryMaintenanceAdapter | None = None) -> None:
        self._manager = manager

    @skill_action(
        "optimize_memory",
        "Runs SQLite maintenance and garbage collection",
        capability="system.memory.optimize",
        fixed_resources=(MEMORY_RESOURCE,),
        timeout_seconds=10.0,
    )
    def optimize_memory(self) -> str:
        require_active_capability(
            "system.memory.optimize",
            (MEMORY_RESOURCE,),
        )
        if self._manager is None:
            raise SkillAdapterUnavailable("memory_maintenance")
        optimization = self._manager.optimize_sqlite_database()
        if isinstance(optimization, Mapping) and optimization.get("success") is False:
            raise RuntimeError("Memory maintenance adapter reported failure")
        ram_info = self._manager.enforce_memory_cap(max_ram_mb=200)
        if not isinstance(ram_info, Mapping):
            raise RuntimeError("Memory maintenance adapter returned invalid metrics")
        current_rss = ram_info.get("current_rss_mb")
        if not isinstance(current_rss, (int, float)):
            return "Memory maintenance completed; RSS is UNAVAILABLE"
        return f"Memory maintenance completed; RSS is {current_rss} MB"
