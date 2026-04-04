"""Phase 1 gate for Pillar 35: Activation Sparsity.

Validates:
1. High resource pressure lowers top-k activation ratio.
2. Action-risk intents preserve slightly more activation budget.
3. Runtime execute_intent applies adaptive top-k and exposes it.
4. Cognitive Silence forces minimum top-k.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.activation_sparsity import ActivationSparsityController
from src.brain_v2.engine.runtime import IronEngine


class _FakeResourceMonitor:
    def __init__(self, cpu: float, mem: float):
        self._cpu = cpu
        self._mem = mem

    def readings(self):
        return {"cpu_pct": self._cpu, "mem_pct": self._mem}


class TestActivationSparsityController(unittest.TestCase):
    def test_high_pressure_reduces_topk(self):
        controller = ActivationSparsityController(default_topk=0.10)

        decision = controller.decide(
            text="jelaskan arsitektur lokal secara rinci",
            base_topk=0.10,
            cpu_pct=92.0,
            mem_pct=88.0,
            is_silent=False,
        )

        self.assertLess(float(decision["target_topk"]), 0.10)
        self.assertGreaterEqual(float(decision["target_topk"]), 0.02)

    def test_action_risk_gets_slight_budget_bump(self):
        controller = ActivationSparsityController(default_topk=0.10)

        action_decision = controller.decide(
            text="hapus data lama lalu migrasi konfigurasi",
            base_topk=0.10,
            cpu_pct=30.0,
            mem_pct=30.0,
            is_silent=False,
        )
        general_decision = controller.decide(
            text="jelaskan konsep dasar",
            base_topk=0.10,
            cpu_pct=30.0,
            mem_pct=30.0,
            is_silent=False,
        )

        self.assertGreaterEqual(
            float(action_decision["target_topk"]),
            float(general_decision["target_topk"]),
        )

    def test_silence_forces_minimum_topk(self):
        controller = ActivationSparsityController(default_topk=0.10)

        decision = controller.decide(
            text="any request",
            base_topk=0.10,
            cpu_pct=5.0,
            mem_pct=10.0,
            is_silent=True,
        )

        self.assertAlmostEqual(float(decision["target_topk"]), 0.02, places=6)


class TestRuntimeActivationSparsityIntegration(unittest.TestCase):
    def _build_engine(self) -> IronEngine:
        engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
        engine.ignite()

        resource_mon = getattr(engine, "_resource_mon", None)
        if resource_mon is not None:
            resource_mon.stop()

        return engine

    def test_execute_intent_reports_activation_topk(self):
        engine = self._build_engine()
        engine.config.topk_ratio = 0.10
        setattr(engine, "_resource_mon", _FakeResourceMonitor(cpu=90.0, mem=90.0))

        out = engine.execute_intent("open desktop")

        self.assertTrue(out["ok"])
        self.assertIn("activation_topk", out)
        self.assertLessEqual(float(out["activation_topk"]), 0.10)
        self.assertGreaterEqual(float(out["activation_topk"]), 0.02)

    def test_status_exposes_activation_sparsity_block(self):
        engine = self._build_engine()

        status = engine.status()
        self.assertIn("activation_sparsity", status)
        self.assertIsInstance(status["activation_sparsity"], dict)


if __name__ == "__main__":
    unittest.main()
