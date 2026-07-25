"""
Built-in System Control & Resource Monitoring Skill for JAYA_AGENT.
"""

import sys
import os
import psutil
from typing import Dict, Any
from ..base_skill import Skill, skill_action


class SystemControlSkill(Skill):
    name = "system_skill"
    description = "System resource monitoring and execution control"

    @skill_action("get_system_status", "Returns CPU and RAM memory usage metrics")
    def get_system_status(self) -> str:
        cpu = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        process = psutil.Process(os.getpid())
        rss_mb = process.memory_info().rss / (1024 * 1024)

        return (
            f"CPU Usage: {cpu}% | System RAM: {mem.percent}% used | "
            f"JAYA Agent Process RAM (RSS): {rss_mb:.1f} MB (Cap: 200 MB)"
        )
