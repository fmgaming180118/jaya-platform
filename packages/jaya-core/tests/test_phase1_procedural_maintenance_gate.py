"""Phase 1 Stage-4 gate: procedural auto-prune policy and stats snapshot."""

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.soul.agentic_rag import AgenticRAG


class TestPhase1ProceduralMaintenanceGate(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self._tmpdir.name) / "tmp_rag_stage4.db")
        self.rag = AgenticRAG(db_path=self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def _insert_proc(self, trigger: str, days_ago: int, confidence: float = 0.8):
        now = time.time()
        self.assertTrue(
            self.rag.memorize_procedure(
                trigger=trigger,
                steps=["step 1", "step 2"],
                language="id",
                source="unit_test",
                confidence=confidence,
                timestamp_override=now - (days_ago * 24 * 3600),
            )
        )

    def test_prune_removes_stale_unused_capsules(self):
        self._insert_proc("stale alpha procedure", days_ago=120, confidence=0.30)
        self._insert_proc("fresh beta procedure", days_ago=1, confidence=0.70)

        before = self.rag.procedural_stats_snapshot(top_n=2)
        self.assertEqual(before["total_capsules"], 2)

        report = self.rag.prune_procedures(max_items=16, stale_days=45, min_health=0.40)
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["removed_stale"], 1)

        after = self.rag.procedural_stats_snapshot(top_n=2)
        self.assertEqual(after["total_capsules"], 1)

        remaining = self.rag.recall_procedure("fresh beta procedure", language="id", limit=1)
        self.assertEqual(len(remaining), 1)
        self.assertIn("fresh beta", remaining[0]["trigger"])

    def test_prune_enforces_max_items(self):
        for idx in range(24):
            self._insert_proc(f"overflow procedure {idx}", days_ago=2, confidence=0.65)

        report = self.rag.prune_procedures(max_items=16, stale_days=365, min_health=0.0)
        self.assertTrue(report["ok"])
        self.assertEqual(report["after"], 16)
        self.assertGreaterEqual(report["removed_overflow"], 8)

        stats = self.rag.procedural_stats_snapshot(top_n=5)
        self.assertEqual(stats["total_capsules"], 16)

    def test_snapshot_contains_expected_fields(self):
        self._insert_proc("snapshot alpha", days_ago=1, confidence=0.75)
        self._insert_proc("snapshot beta", days_ago=1, confidence=0.85)

        ranked = self.rag.recall_procedure("snapshot", language="id", limit=2)
        self.assertGreaterEqual(len(ranked), 1)
        self.assertTrue(self.rag.record_procedure_usage(ranked[0]["id"], success=True))

        snapshot = self.rag.procedural_stats_snapshot(top_n=3)
        for key in [
            "total_capsules",
            "by_language",
            "avg_confidence",
            "avg_usage",
            "total_usage",
            "success_rate",
            "stale_candidates",
            "top_capsules",
        ]:
            self.assertIn(key, snapshot)

        self.assertGreaterEqual(snapshot["total_capsules"], 2)
        self.assertIn("id", snapshot["top_capsules"][0])
        self.assertIn("health", snapshot["top_capsules"][0])

    def test_tidy_up_returns_prune_and_stats(self):
        self._insert_proc("tidy stale proc", days_ago=200, confidence=0.25)
        result = self.rag.tidy_up()
        self.assertIn("procedural_prune", result)
        self.assertIn("procedural_stats", result)
        self.assertIn("removed_total", result["procedural_prune"])

    def test_only_if_missing_preserves_existing_usage(self):
        self._insert_proc("seeded continuity procedure", days_ago=1, confidence=0.9)
        ranked = self.rag.recall_procedure("seeded continuity", language="id", limit=1)
        self.assertEqual(len(ranked), 1)
        procedure_id = ranked[0]["id"]

        for _ in range(3):
            self.assertTrue(self.rag.record_procedure_usage(procedure_id, success=True))

        self.assertTrue(
            self.rag.memorize_procedure(
                trigger="seeded continuity procedure",
                steps=["new step 1", "new step 2"],
                language="id",
                source="core_bootstrap",
                confidence=0.95,
                only_if_missing=True,
            )
        )

        updated = self.rag.recall_procedure("seeded continuity", language="id", limit=1)
        self.assertEqual(len(updated), 1)
        self.assertEqual(updated[0]["id"], procedure_id)
        self.assertGreaterEqual(updated[0]["usage_count"], 3)


if __name__ == "__main__":
    unittest.main()
