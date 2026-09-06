"""Phase 1 Stage-6 gate: policy-history persistence and explicit procedure feedback loop."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.soul.agentic_rag import AgenticRAG


class TestPhase1PolicyFeedbackLoopGate(unittest.TestCase):
    def setUp(self):
        self._old_clarify = os.getenv("JAYA_CLARIFY_THRESHOLD")
        self._old_decay = os.getenv("JAYA_PROCEDURE_DECAY_HOURS")
        os.environ["JAYA_CLARIFY_THRESHOLD"] = "0.62"
        os.environ["JAYA_PROCEDURE_DECAY_HOURS"] = "120"

        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self._tmpdir.name) / "tmp_rag_stage6.db")
        self.rag = AgenticRAG(db_path=self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

        if self._old_clarify is None:
            os.environ.pop("JAYA_CLARIFY_THRESHOLD", None)
        else:
            os.environ["JAYA_CLARIFY_THRESHOLD"] = self._old_clarify

        if self._old_decay is None:
            os.environ.pop("JAYA_PROCEDURE_DECAY_HOURS", None)
        else:
            os.environ["JAYA_PROCEDURE_DECAY_HOURS"] = self._old_decay

    def _seed_procedure(self, trigger: str, confidence: float = 0.85, days_ago: int = 1) -> None:
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

    def test_apply_policy_writes_history(self):
        self._seed_procedure("sinkronisasi bahasa lokal perangkat", confidence=0.88)

        report = self.rag.apply_adaptive_policy(
            clarify_threshold=0.62,
            decay_hours=120,
            source="unit_test_apply",
        )
        self.assertTrue(report["applied"])
        self.assertTrue(report["history_written"])

        history = self.rag.get_policy_history(limit=5)
        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["source"], "unit_test_apply")
        self.assertIn("recommended_clarify_threshold", history[0])
        self.assertIn("recommended_decay_hours", history[0])

    def test_policy_history_summary_has_expected_fields(self):
        self._seed_procedure("stabilitas bahasa lokal perangkat", confidence=0.90)
        self.rag.apply_adaptive_policy(clarify_threshold=0.62, decay_hours=120, source="pass_1")
        self.rag.apply_adaptive_policy(clarify_threshold=0.70, decay_hours=140, source="pass_2")

        summary = self.rag.policy_history_summary(window=10)
        for key in [
            "count",
            "avg_clarify_threshold",
            "avg_decay_hours",
            "last_clarify_threshold",
            "last_decay_hours",
            "clarify_trend",
            "decay_trend",
        ]:
            self.assertIn(key, summary)

        self.assertGreaterEqual(summary["count"], 2)
        self.assertIsNotNone(summary["last_clarify_threshold"])
        self.assertIsNotNone(summary["last_decay_hours"])

    def test_feedback_success_updates_usage_counters(self):
        self._seed_procedure("sinkronisasi cache bahasa perangkat", confidence=0.87)

        out = self.rag.apply_procedure_feedback(
            query="cara sinkronisasi cache bahasa perangkat",
            success=True,
            language="id",
        )
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["usage_count"], 1)
        self.assertGreaterEqual(out["success_count"], 1)

    def test_feedback_failure_updates_failure_counter(self):
        self._seed_procedure("pemulihan bahasa lokal perangkat", confidence=0.84)

        out = self.rag.apply_procedure_feedback(
            query="langkah pemulihan bahasa lokal perangkat",
            success=False,
            language="id",
        )
        self.assertTrue(out["ok"])
        self.assertGreaterEqual(out["usage_count"], 1)
        self.assertGreaterEqual(out["failure_count"], 1)

    def test_feedback_returns_not_found_for_unknown_query(self):
        out = self.rag.apply_procedure_feedback(
            query="prosedur kuantum antarbintang yang tidak ada",
            success=True,
            language="id",
        )
        self.assertFalse(out["ok"])
        self.assertEqual(out["message"], "no_procedure_match")


if __name__ == "__main__":
    unittest.main()
