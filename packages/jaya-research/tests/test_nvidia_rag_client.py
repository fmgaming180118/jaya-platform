"""Unit tests for NVIDIARAGClient (Phase A)."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock

import numpy as np

from jaya_research.research.nvidia_rag_client import NVIDIARAGClient
from jaya_research.research.enhanced_rag import NVIDIAEmbeddings, _normalize_vectors


class TestNVIDIARAGClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.pop("NVIDIA_API_KEY", None)

        self.mock_embedder = MagicMock(spec=NVIDIAEmbeddings)
        self.mock_embedder.dimension = 8
        self.mock_embedder.embed_texts.side_effect = lambda texts: _normalize_vectors(
            np.array([[float(i + 1)] * 8 for i, _ in enumerate(texts)], dtype=np.float32)
        )

        self.client = NVIDIARAGClient(
            vector_store_path=self.tmp,
            workspace_id="test_ws",
            use_embeddings=True,
            embedder=self.mock_embedder,
        )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ingest_text_and_search(self):
        result = self.client.ingest_text(
            "JAYA Research memakai RAG semantic untuk chat tesis.",
            metadata={"source": "notes.md"},
        )
        self.assertEqual(result["status"], "success")
        self.assertGreaterEqual(result["chunks_added"], 1)

        results = self.client.search("RAG semantic", top_k=3)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("snippet", results[0])

    def test_workspace_filter_is_respected(self):
        other = NVIDIARAGClient(
            vector_store_path=self.tmp,
            workspace_id="other_ws",
            use_embeddings=True,
            embedder=self.mock_embedder,
        )
        other.ingest_text("private workspace content", metadata={"source": "secret.md"})

        results = self.client.search("private workspace content", top_k=5)
        self.assertEqual(results, [])

    def test_query_returns_answer_and_sources(self):
        self.client.ingest_text(
            "Vector store and knowledge graph are combined for research answers.",
            metadata={"source": "answer.md"},
        )
        result = self.client.query("knowledge graph", top_k=2, web_fallback=False)
        self.assertIn("answer", result)
        self.assertIn("sources", result)
        self.assertTrue(result["sources"])


if __name__ == "__main__":
    unittest.main()
