"""
JAYA_CORE Research Bridge (Pillar 33 — Agentic RAG)
Reads discoveries from JAYA_RESEARCH evolution_memory.json and injects
them into JAYA_CORE's Agentic RAG database so that research findings
become part of JAYA's sovereign knowledge base.
"""
import hashlib
import json
import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Add JAYA_CORE root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core_config import core_config

logger = logging.getLogger("ResearchBridge")


class ResearchBridge:
    """
    Bridges JAYA_RESEARCH discoveries → JAYA_CORE AgenticRAG.

    Usage:
        bridge = ResearchBridge()
        summary = bridge.sync()
        print(summary)
    """

    def __init__(self):
        self.memory_path = Path(core_config.RESEARCH_MEMORY_PATH)
        self.rag_db_path = Path(core_config.AGENTIC_RAG_PATH)
        self._ensure_rag_schema()

    # ──────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────

    def sync(self) -> Dict[str, Any]:
        """
        Pull latest discoveries from JAYA_RESEARCH and write them
        into the CORE AgenticRAG facts store.
        Returns a summary dict with counts.
        """
        discoveries = self._load_research_memory()
        if not discoveries:
            logger.info("[Bridge] No research discoveries found at %s", self.memory_path)
            return {"status": "no_data", "synced": 0}

        new_count = 0
        skipped = 0

        with sqlite3.connect(str(self.rag_db_path)) as conn:
            for entry in discoveries:
                entry_id = self._entry_id(entry)
                if self._already_synced(conn, entry_id):
                    skipped += 1
                    continue

                fact = self._to_fact(entry)
                self._insert_fact(conn, entry_id, fact)
                new_count += 1

        logger.info("[Bridge] Sync complete — new: %d  skipped: %d", new_count, skipped)
        return {
            "status": "ok",
            "synced": new_count,
            "skipped": skipped,
            "total_discoveries": len(discoveries),
        }

    def status(self) -> Dict[str, Any]:
        """Return current bridge state without syncing."""
        discoveries = self._load_research_memory()
        with sqlite3.connect(str(self.rag_db_path)) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM agentic_facts WHERE source = 'research_bridge'"
            )
            synced = cursor.fetchone()[0]
        return {
            "research_memory_exists": self.memory_path.exists(),
            "total_discoveries": len(discoveries),
            "already_synced_in_core": synced,
            "rag_db": str(self.rag_db_path),
        }

    # ──────────────────────────────────────────────────────────────────
    # Internals
    # ──────────────────────────────────────────────────────────────────

    def _ensure_rag_schema(self) -> None:
        """Create the facts table if it doesn't exist."""
        self.rag_db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(str(self.rag_db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agentic_facts (
                    id          TEXT PRIMARY KEY,
                    source      TEXT NOT NULL,
                    topic       TEXT,
                    content     TEXT NOT NULL,
                    confidence  REAL DEFAULT 1.0,
                    created_at  REAL NOT NULL
                )
            """)

    def _load_research_memory(self) -> List[Dict[str, Any]]:
        """Load evolution_memory.json from JAYA_RESEARCH."""
        if not self.memory_path.exists():
            return []
        try:
            with open(self.memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # The memory file may be a list or a dict with 'discoveries' key
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                return data.get("discoveries", data.get("entries", []))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("[Bridge] Failed to load research memory: %s", exc)
        return []

    def _entry_id(self, entry: Dict[str, Any]) -> str:
        """Stable deterministic ID from entry content hash."""
        raw = json.dumps(entry, sort_keys=True, default=str).encode()
        return hashlib.sha256(raw).hexdigest()[:32]

    def _already_synced(self, conn: sqlite3.Connection, entry_id: str) -> bool:
        cursor = conn.execute(
            "SELECT 1 FROM agentic_facts WHERE id = ?", (entry_id,)
        )
        return cursor.fetchone() is not None

    def _to_fact(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        """Convert a research memory entry into a structured RAG fact."""
        # Common keys used by JAYA_RESEARCH evolution_memory
        topic = (
            entry.get("topic")
            or entry.get("query")
            or entry.get("name")
            or "Unknown Discovery"
        )
        content_parts = []
        if entry.get("summary"):
            content_parts.append(f"Summary: {entry['summary']}")
        if entry.get("hypothesis"):
            content_parts.append(f"Hypothesis: {entry['hypothesis']}")
        if entry.get("findings"):
            findings = entry["findings"]
            if isinstance(findings, list):
                content_parts.append("Findings: " + "; ".join(str(f) for f in findings[:5]))
            else:
                content_parts.append(f"Findings: {findings}")
        if not content_parts:
            content_parts.append(json.dumps(entry, default=str)[:512])

        return {
            "topic": str(topic),
            "content": "\n".join(content_parts),
            "confidence": float(entry.get("confidence", 0.9)),
        }

    def _insert_fact(
        self, conn: sqlite3.Connection, entry_id: str, fact: Dict[str, Any]
    ) -> None:
        conn.execute(
            """INSERT INTO agentic_facts (id, source, topic, content, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                entry_id,
                "research_bridge",
                fact["topic"],
                fact["content"],
                fact["confidence"],
                time.time(),
            ),
        )
        logger.debug("[Bridge] Inserted fact: %s", fact["topic"])


# ── CLI entry point ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    bridge = ResearchBridge()

    import argparse
    parser = argparse.ArgumentParser(description="JAYA Research → Core Discovery Bridge")
    parser.add_argument("--status", action="store_true", help="Show bridge status without syncing")
    args = parser.parse_args()

    if args.status:
        result = bridge.status()
    else:
        result = bridge.sync()

    print(json.dumps(result, indent=2))
