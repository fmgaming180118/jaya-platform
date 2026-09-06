"""Phase 1 gate for Pillar 31: Narrative Continuity.

Validates:
1. Bounded autobiographical event retention.
2. Runtime traces intent turns into narrative memory.
3. Twin feedback is incorporated into narrative history.
4. Optional persistence keeps continuity across engine instances.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.engine.narrative_continuity import NarrativeContinuity
from jaya_core.brain_v2.engine.runtime import IronEngine
from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from narrative_test_support import TestNarrativeSigner

_IDENTITY_SECRET = "phase1-narrative-identity-secret-at-least-32-bytes"


class TestNarrativeContinuityModule(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.signer = TestNarrativeSigner()

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_bounded_event_retention_keeps_latest_history(self):
        memory = NarrativeContinuity(
            Path(self.tmpdir.name) / "retention.sqlite3",
            self.signer,
            max_events=32,
            summary_window=5,
        )

        for idx in range(40):
            memory.remember_turn(user_text=f"turn {idx}")

        snap = memory.snapshot(limit=20, max_chars=1000)
        self.assertEqual(snap["total_events"], 40)
        self.assertEqual(snap["recent"][-1]["user"], "turn 39")
        memory.close()

    def test_snapshot_context_is_bounded(self):
        memory = NarrativeContinuity(
            Path(self.tmpdir.name) / "context.sqlite3",
            self.signer,
            max_events=32,
            summary_window=6,
        )
        for idx in range(12):
            memory.remember_turn(user_text=f"jelaskan mode lokal tahap {idx}")

        snap = memory.snapshot(limit=999, max_chars=2000)
        self.assertLessEqual(len(snap["context"]), 2000)
        self.assertTrue(snap["summary"])
        memory.close()


class TestRuntimeNarrativeIntegration(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.narrative_path = str(Path(self.tmpdir.name) / "runtime_narrative.json")
        self.anchor = DNAAnchor(
            Path(self.tmpdir.name) / "identity",
            EncryptedFileKeyStore(
                Path(self.tmpdir.name) / "keystore", _IDENTITY_SECRET
            ),
        )
        self.anchor.enroll()
        self.engines = []

    def tearDown(self):
        for engine in self.engines:
            narrative = getattr(engine, "_narrative", None)
            if narrative is not None:
                narrative.close()
                engine._narrative = None
        self.anchor.close()
        self.tmpdir.cleanup()

    def _build_engine(self) -> IronEngine:
        with patch.dict(os.environ, {"JAYA_NARRATIVE_PATH": self.narrative_path}, clear=False):
            engine = IronEngine(
                model_path="missing.jay",
                password="x",
                enable_twin=False,
                identity_anchor=self.anchor,
            )
            engine.ignite()
            resource_mon = getattr(engine, "_resource_mon", None)
            if resource_mon is not None:
                resource_mon.stop()
            self.engines.append(engine)
            return engine

    def test_execute_intent_updates_narrative_context(self):
        engine = self._build_engine()
        out = engine.execute_intent("open desktop")

        self.assertTrue(out["ok"])

        narrative = engine.narrative_context(limit=5, max_chars=700)
        self.assertTrue(narrative["ok"])
        self.assertGreaterEqual(narrative["total_events"], 1)
        self.assertIn("open desktop", narrative["context"].lower())

        status = engine.status()
        self.assertIn("narrative", status)
        self.assertIsInstance(status["narrative"], dict)

    def test_feedback_trace_is_recorded(self):
        engine = self._build_engine()
        engine.execute_intent("open desktop")

        engine.receive_twin_feedback(
            {
                "task": "OPTIMIZE_SEARCH",
                "result": {"score": 0.77},
                "config_update": {},
            }
        )

        narrative = engine.narrative_context(limit=10, max_chars=700)
        feedback_events = [
            item for item in narrative["recent"] if item.get("kind") == "feedback"
        ]

        self.assertTrue(feedback_events)
        self.assertEqual(feedback_events[-1]["task"], "OPTIMIZE_SEARCH")
        self.assertAlmostEqual(float(feedback_events[-1]["score"]), 0.77, places=6)

    def test_persistence_restores_previous_history(self):
        first_engine = self._build_engine()
        first_engine.execute_intent("open desktop")
        first_engine.receive_twin_feedback(
            {
                "task": "REPAIR",
                "result": {"score": 0.55},
                "config_update": {},
            }
        )

        second_engine = self._build_engine()
        narrative = second_engine.narrative_context(limit=10, max_chars=700)

        self.assertTrue(narrative["ok"])
        self.assertGreaterEqual(narrative["total_events"], 2)
        self.assertIn("open desktop", narrative["context"].lower())


if __name__ == "__main__":
    unittest.main()
