"""Phase 1 Stage-3 gate: procedural ranking with decay and usage feedback."""

import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.jaya_shell import process_offline_response
from jaya_core.brain_v2.soul.agentic_rag import AgenticRAG
from jaya_core.brain_v2.soul.lingua_logica import LinguaLogica


class TestPhase1ProceduralRankingGate(unittest.TestCase):
    def setUp(self):
        self.lingua = LinguaLogica()
        self._tmpdir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = str(Path(self._tmpdir.name) / "tmp_rag_stage3.db")
        self.rag = AgenticRAG(db_path=self.db_path)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_recent_procedure_beats_stale_even_with_lower_confidence(self):
        now = time.time()
        self.rag.memorize_procedure(
            trigger="migrasi device bahasa lokal lama",
            steps=["Langkah lama 1", "Langkah lama 2"],
            language="id",
            source="unit_test",
            confidence=0.95,
            timestamp_override=now - (30 * 24 * 3600),
        )
        self.rag.memorize_procedure(
            trigger="migrasi device bahasa lokal terbaru",
            steps=["Langkah baru 1", "Langkah baru 2"],
            language="id",
            source="unit_test",
            confidence=0.80,
            timestamp_override=now,
        )

        ranked = self.rag.recall_procedure("cara migrasi device bahasa lokal", language="id", limit=2)
        self.assertEqual(len(ranked), 2)
        self.assertIn("terbaru", ranked[0]["trigger"])
        self.assertGreaterEqual(ranked[0]["score"], ranked[1]["score"])

    def test_usage_feedback_improves_ranking(self):
        now = time.time()
        self.rag.memorize_procedure(
            trigger="reset layanan aman",
            steps=["Stop service", "Start service"],
            language="id",
            source="unit_test",
            confidence=0.80,
            timestamp_override=now,
        )
        self.rag.memorize_procedure(
            trigger="restart service cepat",
            steps=["Restart now"],
            language="id",
            source="unit_test",
            confidence=0.80,
            timestamp_override=now,
        )

        ranked = self.rag.recall_procedure("cara reset service", language="id", limit=2)
        self.assertEqual(len(ranked), 2)

        preferred_id = ranked[0]["id"]
        fallback_id = ranked[1]["id"]

        for _ in range(10):
            self.assertTrue(self.rag.record_procedure_usage(preferred_id, success=True))
        for _ in range(4):
            self.assertTrue(self.rag.record_procedure_usage(fallback_id, success=False))

        reranked = self.rag.recall_procedure("cara reset service", language="id", limit=2)
        self.assertEqual(preferred_id, reranked[0]["id"])
        self.assertGreater(reranked[0]["usage_count"], reranked[1]["usage_count"])

    def test_recall_contains_score_and_usage_stats(self):
        self.rag.memorize_procedure(
            trigger="diagnosa cache lokal",
            steps=["Periksa status", "Validasi hit-rate"],
            language="id",
            source="unit_test",
            confidence=0.84,
        )
        out = self.rag.recall_procedure("diagnosa cache", language="id", limit=1)
        self.assertEqual(len(out), 1)
        self.assertIn("score", out[0])
        self.assertIn("usage_count", out[0])
        self.assertIn("success_count", out[0])
        self.assertIn("failure_count", out[0])

    def test_shell_response_records_usage_feedback(self):
        self.rag.memorize_procedure(
            trigger="migrasi device bahasa lokal",
            steps=["Pindahkan berkas inti", "Jalankan mode offline"],
            language="id",
            source="unit_test",
            confidence=0.90,
        )

        ranked = self.rag.recall_procedure("bagaimana cara migrasi device", language="id", limit=1)
        self.assertEqual(len(ranked), 1)
        procedure_id = ranked[0]["id"]
        self.assertEqual(ranked[0]["usage_count"], 0)

        _ = process_offline_response(
            "Bagaimana cara migrasi device agar bahasa tetap jalan?",
            [],
            rag_instance=self.rag,
            lingua=self.lingua,
            procedure_results=ranked,
            clarify_threshold=0.62,
        )

        updated = self.rag.recall_procedure("bagaimana cara migrasi device", language="id", limit=1)
        self.assertEqual(updated[0]["id"], procedure_id)
        self.assertGreaterEqual(updated[0]["usage_count"], 1)
        self.assertGreater(updated[0]["last_used"], 0)

    def test_negative_limit_returns_empty_result(self):
        self.rag.memorize_procedure(
            trigger="uji batas limit negatif",
            steps=["Langkah 1", "Langkah 2"],
            language="id",
            source="unit_test",
            confidence=0.80,
        )

        ranked = self.rag.recall_procedure("uji batas limit", language="id", limit=-3)
        self.assertEqual(ranked, [])


if __name__ == "__main__":
    unittest.main()
