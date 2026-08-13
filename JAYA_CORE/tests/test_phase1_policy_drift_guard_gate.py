"""Phase 1 Stage-7 gate: policy drift guardrails against oscillation."""

import math
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.soul.agentic_rag import AgenticRAG


class TestPhase1PolicyDriftGuardGate(unittest.TestCase):
    def setUp(self):
        self._env_backup = {
            "JAYA_CLARIFY_THRESHOLD": os.getenv("JAYA_CLARIFY_THRESHOLD"),
            "JAYA_PROCEDURE_DECAY_HOURS": os.getenv("JAYA_PROCEDURE_DECAY_HOURS"),
            "JAYA_POLICY_GUARD_WINDOW": os.getenv("JAYA_POLICY_GUARD_WINDOW"),
            "JAYA_POLICY_GUARD_CLARIFY_STEP": os.getenv("JAYA_POLICY_GUARD_CLARIFY_STEP"),
            "JAYA_POLICY_GUARD_DECAY_STEP_HOURS": os.getenv("JAYA_POLICY_GUARD_DECAY_STEP_HOURS"),
            "JAYA_POLICY_GUARD_COOLDOWN_SECONDS": os.getenv("JAYA_POLICY_GUARD_COOLDOWN_SECONDS"),
        }

        os.environ["JAYA_CLARIFY_THRESHOLD"] = "0.62"
        os.environ["JAYA_PROCEDURE_DECAY_HOURS"] = "120"
        os.environ["JAYA_POLICY_GUARD_WINDOW"] = "10"
        os.environ["JAYA_POLICY_GUARD_CLARIFY_STEP"] = "0.05"
        os.environ["JAYA_POLICY_GUARD_DECAY_STEP_HOURS"] = "12"
        os.environ["JAYA_POLICY_GUARD_COOLDOWN_SECONDS"] = "0"

        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self._tmpdir.name) / "tmp_rag_stage7.db")
        self.rag = AgenticRAG(db_path=self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()
        for key, value in self._env_backup.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _seed_policy_history(self, clarify: float, decay: float, source: str = "seed") -> None:
        payload = {
            "base_clarify_threshold": clarify,
            "base_decay_hours": decay,
            "recommended_clarify_threshold": clarify,
            "recommended_decay_hours": decay,
            "clarify_mode": "stable",
            "decay_mode": "stable",
            "reasons": ["seed"],
            "snapshot": {"seed": True},
        }
        self.assertTrue(self.rag.log_policy_decision(payload, source=source))

    def test_step_clamp_limits_large_jump(self):
        self._seed_policy_history(clarify=0.62, decay=120.0)

        candidate = {
            "base_clarify_threshold": 0.62,
            "base_decay_hours": 120.0,
            "recommended_clarify_threshold": 0.85,
            "recommended_decay_hours": 180.0,
            "clarify_mode": "less_clarification",
            "decay_mode": "longer_retention",
            "reasons": ["manual_extreme"],
            "snapshot": {},
        }
        out = self.rag.apply_policy_guardrails(candidate, source="unit_test")

        self.assertTrue(out["guardrail_applied"])
        self.assertIn("step_clamp", out["guardrail_reasons"])
        self.assertLessEqual(abs(out["recommended_clarify_threshold"] - 0.62), 0.05 + 1e-9)
        self.assertLessEqual(abs(out["recommended_decay_hours"] - 120.0), 12.0 + 1e-9)

    def test_oscillation_dampening_is_triggered(self):
        # Alternating up/down history should trigger anti-oscillation damping.
        self._seed_policy_history(clarify=0.58, decay=110.0, source="seed_1")
        self._seed_policy_history(clarify=0.66, decay=130.0, source="seed_2")
        self._seed_policy_history(clarify=0.57, decay=108.0, source="seed_3")
        self._seed_policy_history(clarify=0.67, decay=132.0, source="seed_4")

        candidate = {
            "base_clarify_threshold": 0.62,
            "base_decay_hours": 120.0,
            "recommended_clarify_threshold": 0.54,
            "recommended_decay_hours": 96.0,
            "clarify_mode": "more_clarification",
            "decay_mode": "faster_forgetting",
            "reasons": ["sparse_memory_signal"],
            "snapshot": {},
        }
        out = self.rag.apply_policy_guardrails(candidate, source="unit_test")

        self.assertTrue(out["guardrail_applied"])
        self.assertIn("oscillation_dampening", out["guardrail_reasons"])

    def test_cooldown_blend_reduces_fast_update(self):
        os.environ["JAYA_POLICY_GUARD_COOLDOWN_SECONDS"] = "3600"
        self._seed_policy_history(clarify=0.62, decay=120.0)

        candidate = {
            "base_clarify_threshold": 0.62,
            "base_decay_hours": 120.0,
            "recommended_clarify_threshold": 0.40,
            "recommended_decay_hours": 70.0,
            "clarify_mode": "more_clarification",
            "decay_mode": "faster_forgetting",
            "reasons": ["low_success_rate"],
            "snapshot": {},
        }
        out = self.rag.apply_policy_guardrails(candidate, source="unit_test")

        self.assertTrue(out["guardrail_applied"])
        self.assertIn("cooldown_blend", out["guardrail_reasons"])
        self.assertGreater(out["recommended_clarify_threshold"], 0.57)

    def test_apply_adaptive_policy_returns_guardrail_metadata(self):
        self._seed_policy_history(clarify=0.80, decay=150.0)

        report = self.rag.apply_adaptive_policy(
            clarify_threshold=0.62,
            decay_hours=120,
            source="unit_stage7",
        )

        self.assertTrue(report["applied"])
        self.assertIn("raw_recommended_clarify_threshold", report)
        self.assertIn("raw_recommended_decay_hours", report)
        self.assertIn("guardrail_applied", report)
        self.assertIn("guardrail_reasons", report)

        history = self.rag.get_policy_history(limit=1)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["source"], "unit_stage7")

    def test_policy_guardrail_status_reports_flip_risk(self):
        self._seed_policy_history(clarify=0.59, decay=111.0, source="flip_1")
        self._seed_policy_history(clarify=0.65, decay=128.0, source="flip_2")
        self._seed_policy_history(clarify=0.58, decay=109.0, source="flip_3")
        self._seed_policy_history(clarify=0.66, decay=131.0, source="flip_4")
        self._seed_policy_history(clarify=0.57, decay=107.0, source="flip_5")

        status = self.rag.policy_guardrail_status(window=10)
        self.assertGreaterEqual(status["clarify_sign_flips"], 2)
        self.assertIn(status["risk_level"], {"medium", "high"})

    def test_guardrails_sanitize_non_finite_candidate_values(self):
        self._seed_policy_history(clarify=0.62, decay=120.0, source="seed_finite")

        candidate = {
            "base_clarify_threshold": 0.62,
            "base_decay_hours": 120.0,
            "recommended_clarify_threshold": float("nan"),
            "recommended_decay_hours": float("inf"),
            "clarify_mode": "stable",
            "decay_mode": "stable",
            "reasons": ["non_finite_input"],
            "snapshot": {},
        }
        out = self.rag.apply_policy_guardrails(candidate, source="unit_test")

        self.assertTrue(math.isfinite(out["recommended_clarify_threshold"]))
        self.assertTrue(math.isfinite(out["recommended_decay_hours"]))
        self.assertGreaterEqual(out["recommended_clarify_threshold"], 0.35)
        self.assertLessEqual(out["recommended_clarify_threshold"], 0.90)
        self.assertGreaterEqual(out["recommended_decay_hours"], 24.0)


if __name__ == "__main__":
    unittest.main()
