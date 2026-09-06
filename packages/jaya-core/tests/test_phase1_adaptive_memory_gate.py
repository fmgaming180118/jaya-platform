"""Phase 1 Stage-2 gate: procedural memory capsules + uncertainty-aware clarification."""

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.jaya_shell import process_offline_response
from jaya_core.brain_v2.soul.agentic_rag import AgenticRAG
from jaya_core.brain_v2.soul.language_policy import get_policy
from jaya_core.brain_v2.soul.lingua_logica import LinguaLogica


class TestPhase1AdaptiveMemoryGate(unittest.TestCase):
    def setUp(self):
        self.lingua = LinguaLogica()
        self.id_pack = get_policy("id")
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self._tmpdir.name) / "tmp_rag_stage2.db")
        self.rag = AgenticRAG(db_path=self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_procedure_capsule_roundtrip(self):
        ok = self.rag.memorize_procedure(
            trigger="migrasi device bahasa lokal",
            steps=[
                "Pindahkan jaya.jay dan rag_vault.db.",
                "Jalankan mode offline.",
                "Uji query bahasa Indonesia.",
            ],
            language="id",
            source="unit_test",
            confidence=0.88,
        )
        self.assertTrue(ok)

        found = self.rag.recall_procedure("cara migrasi device", language="id", limit=2)
        self.assertGreaterEqual(len(found), 1)
        self.assertEqual(found[0]["trigger"], "migrasi device bahasa lokal")
        self.assertIn("Jalankan mode offline.", found[0]["steps"])

    def test_offline_prefers_procedure_for_step_queries(self):
        self.rag.memorize_procedure(
            trigger="migrasi device bahasa lokal",
            steps=[
                "Pindahkan jaya.jay dan rag_vault.db.",
                "Jalankan mode offline.",
                "Uji query campuran ID/EN.",
            ],
            language="id",
            source="unit_test",
            confidence=0.91,
        )
        procedures = self.rag.recall_procedure("bagaimana cara migrasi device", language="id", limit=1)

        response = process_offline_response(
            "Bagaimana cara migrasi device agar bahasa tetap jalan?",
            [],
            rag_instance=self.rag,
            lingua=self.lingua,
            procedure_results=procedures,
            clarify_threshold=0.62,
        )
        self.assertIn(self.id_pack["procedure_intro"], response)
        self.assertIn("Pindahkan jaya.jay", response)
        self.assertIn("unit_test", response)
        self.assertIn("0.91", response)

    def test_threshold_forces_clarification_when_uncertain(self):
        response = process_offline_response(
            "Jelaskan arsitektur lokal",
            [],
            rag_instance=self.rag,
            lingua=self.lingua,
            procedure_results=[],
            clarify_threshold=0.40,
        )
        self.assertIn(self.id_pack["clarify"], response)

    def test_threshold_allows_no_memory_response_when_relaxed(self):
        response = process_offline_response(
            "Jelaskan arsitektur lokal",
            [],
            rag_instance=self.rag,
            lingua=self.lingua,
            procedure_results=[],
            clarify_threshold=0.90,
        )
        self.assertIn(self.id_pack["no_memory"], response)


if __name__ == "__main__":
    unittest.main()
