"""
Built-in Memory Manager Skill for JAYA_AGENT.
Triggers SQLite WAL mode optimization and memory cap garbage collection.
"""

import sys
import os
from typing import Dict, Any
from ..base_skill import Skill, skill_action

try:
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
    research_src = os.path.join(root_dir, "JAYA_RESEARCH", "src")
    if research_src not in sys.path:
        sys.path.insert(0, research_src)
    from memory_manager import MemoryManager
    mm = MemoryManager()
except Exception:
    mm = None


class MemoryManagerSkill(Skill):
    name = "memory_skill"
    description = "SQLite WAL optimization and RAM garbage collection"

    @skill_action("optimize_memory", "Runs SQLite WAL indexing and garbage collection")
    def optimize_memory(self) -> str:
        if mm is None:
            return "MemoryManager module unavailable."
        mm.optimize_sqlite_database()
        ram_info = mm.enforce_memory_cap(max_ram_mb=200)
        return f"Memory optimized. Current RAM RSS: {ram_info.get('current_rss_mb')} MB (Cap: 200 MB)"
