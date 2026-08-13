"""Memory-layer tests, including contained reads and closed promotion."""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

agent_source = Path(__file__).resolve().parents[1] / "src"
if str(agent_source) not in sys.path:
    sys.path.insert(0, str(agent_source))

from JAYA_AGENT.src.memory.rag_memory import RAGMemoryEngine
from JAYA_AGENT.src.memory.sync_bridge import EcosystemSyncBridge, LegacySyncDisabled
from JAYA_AGENT.src.memory.working_memory import WorkingMemoryManager


class TestPhase4Memory(unittest.TestCase):
    def test_working_memory_compression(self) -> None:
        memory = WorkingMemoryManager(max_turns=5)
        for index in range(12):
            memory.add_turn("user", f"Test message turn #{index}")
        self.assertLessEqual(len(memory.history), 10)
        self.assertTrue(memory.summary)
        self.assertIn(
            "SUMMARY OF PRIOR CONVERSATION",
            memory.get_formatted_context(),
        )

    def test_rag_memory_retrieval(self) -> None:
        patches = RAGMemoryEngine().query_relevant_patches("Memory", limit=3)
        self.assertIsInstance(patches, list)

    def test_rag_memory_rejects_arbitrary_external_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            temporary_root = Path(temp)
            storage = temporary_root / "agent-data"
            storage.mkdir()
            external = temporary_root / "external" / "agentic_jarvis.db"
            external.parent.mkdir()
            external.touch()
            with self.assertRaises(ValueError):
                RAGMemoryEngine(
                    db_path=external,
                    storage_root=storage,
                )
            with self.assertRaises(ValueError):
                RAGMemoryEngine(
                    db_path=storage / "arbitrary.db",
                    storage_root=storage,
                )

    def test_rag_memory_reads_contained_database_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
            storage = Path(temp)
            database = storage / "agentic_jarvis.db"
            with closing(sqlite3.connect(database)) as connection:
                connection.execute(
                    "CREATE TABLE jarvis_patches ("
                    "patch_id TEXT, topic TEXT, statement TEXT, "
                    "bayes_confidence REAL)"
                )
                connection.execute(
                    "INSERT INTO jarvis_patches VALUES (?, ?, ?, ?)",
                    ("patch-1", "Memory Safety", "Use bounded retrieval", 0.91),
                )
                connection.commit()
            digest_before = database.read_bytes()
            rows = RAGMemoryEngine(
                db_path=database,
                storage_root=storage,
            ).query_relevant_patches("memory", limit=1)
            self.assertEqual(rows[0]["patch_id"], "patch-1")
            self.assertEqual(database.read_bytes(), digest_before)

    def test_unverified_direct_artifact_copy_is_disabled(self) -> None:
        with self.assertRaises(LegacySyncDisabled):
            EcosystemSyncBridge().sync_latest_evolution()


if __name__ == "__main__":
    unittest.main()
