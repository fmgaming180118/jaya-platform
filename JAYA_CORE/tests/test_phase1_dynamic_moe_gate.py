"""Phase 1 gate for Pillar 34: Dynamic Sparsity MoE.

Validates:
1. Sparse expert selection under normal resource profile.
2. High resource pressure reduces active expert fan-out.
3. Risky commands prioritize safety-aware routing.
4. Runtime execute_intent exposes MoE route metadata.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.dynamic_moe import DynamicMoERouter
from src.brain_v2.engine.runtime import IronEngine


class _FakeResourceMonitor:
    def __init__(self, cpu: float, mem: float):
        self._cpu = cpu
        self._mem = mem

    def readings(self):
        return {"cpu_pct": self._cpu, "mem_pct": self._mem}


class TestDynamicMoERouter(unittest.TestCase):
    def test_sparse_selection_under_normal_pressure(self):
        router = DynamicMoERouter(max_active_experts=2)

        route = router.route(
            text="jelaskan bagaimana arsitektur sovereign bekerja",
            logic_expr=("QUERY", "GENERAL", "arsitektur"),
            cpu_pct=28.0,
            mem_pct=34.0,
        )

        self.assertLessEqual(int(route["active_count"]), 2)
        self.assertGreaterEqual(int(route["active_count"]), 1)

        weights = [float(item["weight"]) for item in route["active_experts"]]
        self.assertAlmostEqual(sum(weights), 1.0, places=3)

    def test_high_pressure_reduces_to_single_expert(self):
        router = DynamicMoERouter(max_active_experts=2)

        route = router.route(
            text="open deployment pipeline lalu rollback",
            logic_expr=("ACTION", "OPEN", "pipeline"),
            cpu_pct=96.0,
            mem_pct=92.0,
        )

        self.assertEqual(int(route["active_count"]), 1)

    def test_risk_signals_prioritize_safety(self):
        router = DynamicMoERouter(max_active_experts=2)

        route = router.route(
            text="delete semua data lama lalu rollback sistem",
            logic_expr=("ACTION", "DELETE", "data"),
            cpu_pct=22.0,
            mem_pct=30.0,
        )

        self.assertEqual(route["primary_expert"], "safety")


class TestRuntimeDynamicMoEIntegration(unittest.TestCase):
    def _build_engine(self) -> IronEngine:
        engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
        engine.ignite()

        resource_mon = getattr(engine, "_resource_mon", None)
        if resource_mon is not None:
            resource_mon.stop()

        return engine

    def test_execute_intent_exposes_moe_route(self):
        engine = self._build_engine()
        setattr(engine, "_resource_mon", _FakeResourceMonitor(cpu=95.0, mem=90.0))

        out = engine.execute_intent("open desktop lalu rollback snapshot")

        self.assertTrue(out["ok"])
        self.assertIn("moe_route", out)
        self.assertIn("moe_primary_expert", out)
        self.assertEqual(
            out["moe_primary_expert"],
            out["moe_route"]["primary_expert"],
        )
        self.assertEqual(int(out["moe_route"]["active_count"]), 1)

    def test_status_includes_dynamic_moe(self):
        engine = self._build_engine()

        status = engine.status()
        self.assertIn("dynamic_moe", status)
        self.assertIsInstance(status["dynamic_moe"], dict)


if __name__ == "__main__":
    unittest.main()
