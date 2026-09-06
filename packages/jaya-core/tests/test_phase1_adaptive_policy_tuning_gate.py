"""Phase 1 Stage-5 gate: adaptive policy tuning from procedural stats snapshots."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.soul.agentic_rag import AgenticRAG


class TestPhase1AdaptivePolicyTuningGate(unittest.TestCase):
    def setUp(self):
        self._old_clarify = os.getenv("JAYA_CLARIFY_THRESHOLD")
        self._old_decay = os.getenv("JAYA_PROCEDURE_DECAY_HOURS")
        os.environ["JAYA_CLARIFY_THRESHOLD"] = "0.62"
        os.environ["JAYA_PROCEDURE_DECAY_HOURS"] = "120"

        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self._tmpdir.name) / "tmp_rag_stage5.db")
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

    def _memorize(self, trigger: str, days_ago: int, confidence: float = 0.8) -> None:
        now = time.time()
        self.assertTrue(
            self.rag.memorize_procedure(
                trigger=trigger,
                steps=["langkah 1", "langkah 2"],
                language="id",
                source="unit_test",
                confidence=confidence,
                timestamp_override=now - (days_ago * 24 * 3600),
            )
        )

    def test_sparse_memory_recommends_more_clarification(self):
        self._memorize("sparse migration baseline", days_ago=1, confidence=0.70)

        report = self.rag.suggest_adaptive_policy(clarify_threshold=0.62, decay_hours=120)
        self.assertLess(report["recommended_clarify_threshold"], 0.62)
        self.assertEqual(report["clarify_mode"], "more_clarification")
        self.assertIn("sparse_memory_signal", report["reasons"])

    def test_reliable_history_relaxes_clarification_and_extends_decay(self):
        words = [
            "alpha",
            "bravo",
            "charlie",
            "delta",
            "echo",
            "foxtrot",
            "golf",
            "hotel",
        ]
        for word in words:
            self._memorize(f"reliable {word} migration procedure", days_ago=1, confidence=0.90)

        for word in words:
            ranked = self.rag.recall_procedure(f"{word} migration procedure", language="id", limit=1)
            self.assertEqual(len(ranked), 1)
            for _ in range(3):
                self.assertTrue(self.rag.record_procedure_usage(ranked[0]["id"], success=True))

        report = self.rag.suggest_adaptive_policy(clarify_threshold=0.62, decay_hours=120)
        self.assertGreater(report["recommended_clarify_threshold"], 0.62)
        self.assertGreater(report["recommended_decay_hours"], 120.0)
        self.assertIn("reliable_procedures", report["reasons"])

    def test_stale_ratio_shortens_decay_horizon(self):
        for idx in range(6):
            self._memorize(f"stale capsule {idx} old maintenance", days_ago=180, confidence=0.20)
        for idx in range(4):
            self._memorize(f"fresh capsule {idx} active maintenance", days_ago=1, confidence=0.82)

        report = self.rag.suggest_adaptive_policy(clarify_threshold=0.62, decay_hours=120)
        self.assertLess(report["recommended_decay_hours"], 120.0)
        self.assertIn("stale_ratio_high", report["reasons"])

    def test_apply_adaptive_policy_updates_environment(self):
        self._memorize("apply policy sparse baseline", days_ago=1, confidence=0.72)

        report = self.rag.apply_adaptive_policy(clarify_threshold=0.62, decay_hours=120)
        self.assertTrue(report["applied"])
        self.assertIn("previous_clarify_threshold", report)
        self.assertIn("previous_decay_hours", report)

        applied_clarify = float(os.environ["JAYA_CLARIFY_THRESHOLD"])
        applied_decay = float(os.environ["JAYA_PROCEDURE_DECAY_HOURS"])
        self.assertAlmostEqual(applied_clarify, round(report["recommended_clarify_threshold"], 2), places=2)
        self.assertAlmostEqual(applied_decay, round(report["recommended_decay_hours"], 1), places=1)


if __name__ == "__main__":
    unittest.main()
