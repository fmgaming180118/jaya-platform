"""Phase 2 tests for deterministic rollback behavior."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.evolution_gate import EvolutionGate
from src.brain_v2.engine.runtime import IronEngine


class TestPhase2Rollback(unittest.TestCase):
    def test_rollback_idempotent(self):
        gate = EvolutionGate()
        gate.register_stable_snapshot("stable-v1", {"topk_ratio": 0.10, "mode": "safe"})

        ok1, payload1 = gate.rollback("stable-v1")
        ok2, payload2 = gate.rollback("stable-v1")

        self.assertTrue(ok1)
        self.assertTrue(ok2)
        self.assertEqual(payload1["snapshot"], payload2["snapshot"])
        self.assertTrue(payload2["idempotent"])

    def test_rollback_unknown_target(self):
        gate = EvolutionGate()
        ok, payload = gate.rollback("missing")
        self.assertFalse(ok)
        self.assertEqual(payload["error"], "unknown_snapshot")

    def test_runtime_evolution_hooks_smoke(self):
        engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
        engine._init_security()
        engine._init_intelligence()

        reg = engine.register_stable_state("stable-v1", {"version": 1})
        self.assertTrue(reg["ok"])

        signed = engine.sign_evolution_candidate(
            {
                "candidate_id": "cand-rt-1",
                "source_hash": "h123",
                "candidate_payload": "safe optimize candidate",
                "expected_perf_gain_pct": 10.0,
            },
            key_id="local",
        )
        self.assertTrue(signed["ok"])

        decision = engine.evaluate_evolution_candidate(
            signed["candidate"],
            {
                "tests_passed": True,
                "benchmark_gate_passed": True,
                "observed_perf_gain_pct": 10.0,
                "ram_delta_pct": 2.0,
                "cpu_delta_pct": 2.0,
            },
        )
        self.assertTrue(decision["ok"])
        self.assertTrue(decision["decision"]["accepted"])

        rollback = engine.rollback_stable_state("stable-v1")
        self.assertTrue(rollback["ok"])
        self.assertEqual(rollback["target_label"], "stable-v1")

        audit = engine.evolution_audit_log(limit=20)
        self.assertTrue(audit["ok"])
        self.assertGreaterEqual(len(audit["events"]), 3)


if __name__ == "__main__":
    unittest.main()
