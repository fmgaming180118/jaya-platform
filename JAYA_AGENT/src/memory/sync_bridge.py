"""
Automatic Ecosystem Sync Bridge for JAYA_AGENT.
Hot-reloads neural LoRA adapters (.pt) and SQLite agentic_jarvis.db patches from JAYA_RESEARCH.
"""

import sys
import os
import glob
import json
import sqlite3
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional


class EcosystemSyncBridge:
    """
    Automatic sync bridge linking JAYA_RESEARCH -> JAYA_AGENT / JAYA_CORE.
    """

    def __init__(self):
        self.root_dir = Path(__file__).resolve().parent.parent.parent.parent
        self.research_dir = self.root_dir / "JAYA_RESEARCH" / "data"
        self.core_dir = self.root_dir / "JAYA_CORE" / "data"
        self.agent_dir = self.root_dir / "JAYA_AGENT" / "data"

        self.agent_dir.mkdir(parents=True, exist_ok=True)
        print(f"[SYNC BRIDGE] Ecosystem Sync Bridge initialized.")

    def sync_latest_evolution(self) -> Dict[str, Any]:
        """
        Copies latest agentic_jarvis.db and LoRA adapters (.pt) from JAYA_RESEARCH into JAYA_AGENT.
        """
        synced_db = False
        synced_adapters = 0

        # 1. Sync SQLite Database
        src_db = self.research_dir / "agentic_jarvis.db"
        dest_db = self.agent_dir / "agentic_jarvis.db"
        if src_db.exists():
            try:
                shutil.copy2(src_db, dest_db)
                synced_db = True
            except Exception as e:
                print(f"[SYNC BRIDGE] DB copy notice: {e}")

        # 2. Sync LoRA Adapters
        src_adapters = glob.glob(str(self.research_dir / "adapters" / "*.pt"))
        dest_adapter_dir = self.agent_dir / "adapters"
        dest_adapter_dir.mkdir(parents=True, exist_ok=True)

        for adapter_path in src_adapters:
            try:
                shutil.copy2(adapter_path, dest_adapter_dir / Path(adapter_path).name)
                synced_adapters += 1
            except Exception:
                pass

        # 3. Read total patches count
        total_patches = 0
        if dest_db.exists():
            try:
                conn = sqlite3.connect(str(dest_db))
                total_patches = conn.execute("SELECT COUNT(*) FROM jarvis_patches").fetchone()[0]
                conn.close()
            except Exception:
                pass

        return {
            "synced_db": synced_db,
            "synced_adapters": synced_adapters,
            "total_patches": total_patches
        }
