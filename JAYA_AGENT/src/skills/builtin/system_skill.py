"""Capability-gated system resource monitoring for JAYA_AGENT."""

from __future__ import annotations

import os

import psutil
from security.capability_sandbox import require_active_capability
from skills.base_skill import Skill, skill_action

SYSTEM_METRICS_RESOURCE = "system://metrics"


class SystemControlSkill(Skill):
    """Expose bounded metrics without command or shell execution."""

    name = "system_skill"
    description = "System resource monitoring"

    @skill_action(
        "get_system_status",
        "Returns CPU and memory usage metrics",
        capability="system.status",
        fixed_resources=(SYSTEM_METRICS_RESOURCE,),
        timeout_seconds=2.0,
    )
    def get_system_status(self) -> str:
        require_active_capability(
            "system.status",
            (SYSTEM_METRICS_RESOURCE,),
        )
        cpu = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        process = psutil.Process(os.getpid())
        rss_mb = process.memory_info().rss / (1024 * 1024)
        return (
            f"CPU Usage: {cpu}% | System RAM: {memory.percent}% used | "
            f"JAYA Agent Process RAM (RSS): {rss_mb:.1f} MB"
        )
