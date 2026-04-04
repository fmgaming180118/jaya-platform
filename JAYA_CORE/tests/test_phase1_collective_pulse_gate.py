"""Phase 1 gate for Pillar 32: Collective Pulse.

Validates:
1. Offline turns keep pulse in local_solo mode.
2. Online high-trust signals can reach collective_sync mode.
3. Runtime execute_intent emits collective pulse metadata.
4. Twin feedback updates collective pulse history.
"""

import sys
import unittest
from pathlib import Path
from typing import Any, Dict

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.collective_pulse import CollectivePulse
from src.brain_v2.engine.runtime import IronEngine


class _FakeResourceMonitor:
    def __init__(self, cpu: float, mem: float):
        self._cpu = cpu
        self._mem = mem

    def readings(self) -> Dict[str, float]:
        return {"cpu_pct": self._cpu, "mem_pct": self._mem}

    def status(self) -> Dict[str, Any]:
        return {
            "running": False,
            "psutil": False,
            "readings": self.readings(),
            "reading_count": 0,
            "silence_active": False,
        }


class _FakeHybrid:
    def __init__(self, online: bool):
        self._online = bool(online)

    @property
    def is_online(self):
        return self._online


class TestCollectivePulseModule(unittest.TestCase):
    def test_offline_mode_prefers_local_solo(self):
        pulse = CollectivePulse(max_events=64, history_window=10)

        for _ in range(10):
            pulse.ingest_turn(
                text="jelaskan mode lokal",
                activation_topk=0.07,
                primary_expert="logic",
                is_online=False,
            )

        state = pulse.pulse()
        self.assertEqual(state["mode"], "local_solo")
        self.assertGreaterEqual(float(state["pulse_score"]), 0.0)
        self.assertLessEqual(float(state["pulse_score"]), 1.0)

    def test_online_high_trust_can_reach_collective_sync(self):
        pulse = CollectivePulse(max_events=64, history_window=12)

        for idx in range(6):
            pulse.ingest_turn(
                text=f"query design strategy {idx}",
                activation_topk=0.10,
                primary_expert="logic",
                is_online=True,
            )
            pulse.ingest_peer_signal(
                peer_id=f"peer-{idx}",
                trust=0.92,
                novelty=0.35,
                cohesion=0.93,
                is_online=True,
            )

        state = pulse.pulse()
        self.assertEqual(state["mode"], "collective_sync")
        self.assertGreaterEqual(float(state["pulse_score"]), 0.72)


class TestRuntimeCollectivePulseIntegration(unittest.TestCase):
    def _build_engine(self, online: bool) -> IronEngine:
        engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
        engine.ignite()

        resource_mon = getattr(engine, "_resource_mon", None)
        if resource_mon is not None:
            resource_mon.stop()

        setattr(engine, "_resource_mon", _FakeResourceMonitor(cpu=35.0, mem=42.0))
        setattr(engine, "_hybrid", _FakeHybrid(online=online))
        return engine

    def test_execute_intent_emits_collective_pulse(self):
        engine = self._build_engine(online=True)

        out = engine.execute_intent("open desktop and explain architecture")

        self.assertTrue(out["ok"])
        self.assertIn("collective_pulse", out)
        self.assertIn("mode", out["collective_pulse"])
        self.assertIn("pulse_score", out["collective_pulse"])

        status = engine.status()
        self.assertIn("collective_pulse", status)
        self.assertIsInstance(status["collective_pulse"], dict)

    def test_feedback_updates_collective_history(self):
        engine = self._build_engine(online=True)

        engine.execute_intent("jelaskan roadmap")
        engine.receive_twin_feedback(
            {
                "task": "OPTIMIZE_QUERY",
                "result": {"score": 0.88},
                "config_update": {},
            }
        )

        status = engine.status()
        pulse = status["collective_pulse"]
        self.assertIsInstance(pulse, dict)
        self.assertGreaterEqual(int(pulse.get("events", 0)), 2)
        self.assertIn("current", pulse)


if __name__ == "__main__":
    unittest.main()
