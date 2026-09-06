"""Unit tests for Enhanced RAG (Fase A.1)."""
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from jaya_research.research.enhanced_rag import (
    EnhancedRAGClient,
    VectorStore,
    NVIDIAEmbeddings,
    clean_text,
    chunk_text,
    chunk_pages,
    _normalize_vectors,
)


class TestTextProcessing(unittest.TestCase):
    def test_clean_text_removes_repeated_headers(self):
        text = "\n".join(["UNIVERSITAS X"] * 5 + ["Konten unik bab satu tentang RAG."])
        cleaned = clean_text(text)
        self.assertNotIn("UNIVERSITAS X", cleaned)
        self.assertIn("Konten unik", cleaned)

    def test_chunk_text_has_page_number(self):
        chunks = chunk_text("Satu paragraf panjang " * 80, page_number=3, base_metadata={"source": "t.pdf"})
        self.assertTrue(chunks)
        self.assertEqual(chunks[0]["metadata"]["page_number"], 3)

    def test_chunk_pages_per_page(self):
        pages = [(1, "Halaman satu " * 50), (2, "Halaman dua " * 50)]
        chunks = chunk_pages(pages, chunk_size=100, chunk_overlap=20, base_metadata={"source": "doc.pdf"})
        pages_found = {c["metadata"]["page_number"] for c in chunks}
        self.assertIn(1, pages_found)
        self.assertIn(2, pages_found)


class TestVectorStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.store = VectorStore(self.tmp, workspace_id="ws_a", dimension=8)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _make_embeddings(self, n: int) -> np.ndarray:
        rng = np.random.RandomState(42)
        return _normalize_vectors(rng.randn(n, 8).astype(np.float32))

    def test_add_and_search(self):
        chunks = ["alpha document", "beta document", "gamma unrelated"]
        embs = self._make_embeddings(3)
        metas = [
            {"source": "a.pdf", "workspace_id": "ws_a"},
            {"source": "a.pdf", "workspace_id": "ws_a"},
            {"source": "b.pdf", "workspace_id": "ws_a"},
        ]
        self.store.add_chunks(chunks, embs, metas)
        self.assertEqual(self.store.count(), 3)

        results = self.store.search(embs[0], top_k=2, filters={"workspace_id": "ws_a"})
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("alpha", results[0]["content"])

    def test_workspace_filter_excludes_other_workspace(self):
        chunks = ["secret ws_b content"]
        embs = self._make_embeddings(1)
        metas = [{"source": "x.pdf", "workspace_id": "ws_b"}]
        self.store.add_chunks(chunks, embs, metas)

        results = self.store.search(embs[0], top_k=5, filters={"workspace_id": "ws_a"})
        self.assertEqual(len(results), 0)

    def test_delete_by_source(self):
        chunks = ["one", "two"]
        embs = self._make_embeddings(2)
        metas = [{"source": "keep.pdf"}, {"source": "drop.pdf"}]
        self.store.add_chunks(chunks, embs, metas)
        removed = self.store.delete_by_source("drop.pdf")
        self.assertEqual(removed, 1)
        self.assertEqual(self.store.count(), 1)

    def test_persistence_reload(self):
        chunks = ["persist me"]
        embs = self._make_embeddings(1)
        metas = [{"source": "p.pdf"}]
        self.store.add_chunks(chunks, embs, metas)

        reloaded = VectorStore(self.tmp, workspace_id="ws_a", dimension=8)
        self.assertEqual(reloaded.count(), 1)
        stats = reloaded.stats()
        self.assertIn("p.pdf", stats["sources"])


class TestEnhancedRAGClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        os.environ.pop("NVIDIA_API_KEY", None)

        self.mock_embedder = MagicMock(spec=NVIDIAEmbeddings)
        self.mock_embedder.dimension = 8
        self.mock_embedder.embed_texts.side_effect = lambda texts: _normalize_vectors(
            np.array(
                [[float(i + 1)] * 8 for i, _ in enumerate(texts)],
                dtype=np.float32,
            )
        )

        with patch(
            "jaya_research.research.enhanced_rag.NVIDIAEmbeddings",
            return_value=self.mock_embedder,
        ), patch("jaya_research.research.enhanced_rag.WebSearchClient") as mock_ws:
            self.mock_web = mock_ws.return_value
            self.client = EnhancedRAGClient(
                vector_store_path=self.tmp,
                workspace_id="test_ws",
                use_embeddings=True,
            )

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ingest_text_and_search(self):
        text = "JAYA Research adalah asisten riset akademik berbasis RAG dan knowledge graph."
        result = self.client.ingest_text(text, metadata={"source": "notes.md"})
        self.assertEqual(result["chunks_added"], 1)

        results = self.client.search("asisten riset akademik", top_k=3)
        self.assertGreaterEqual(len(results), 1)
        self.assertIn("snippet", results[0])

    def test_get_context_for_query(self):
        self.client.ingest_text("Transformer architecture uses attention mechanisms.", metadata={"source": "t.pdf"})
        ctx = self.client.get_context_for_query("attention", top_k=2)
        self.assertIn("attention", ctx.lower())

    def test_query_local_only_high_score(self):
        self.client.vector_store.add_chunks(
            ["Local answer about RAG"],
            _normalize_vectors(np.array([[1.0] * 8], dtype=np.float32)),
            [{"file_name": "doc1.pdf", "workspace_id": "test_ws"}],
        )
        with patch.object(self.client, "search") as mock_search:
            mock_search.return_value = [{
                "document": {"file_name": "doc1.pdf"},
                "snippet": "Local answer",
                "score": 0.9,
            }]
            result = self.client.query("test query")
            self.assertIn("Local Research Data", result["answer"])
            self.assertNotIn("Web Search Results", result["answer"])
            self.mock_web.search.assert_not_called()

    def test_query_web_fallback_empty(self):
        self.mock_web.is_available.return_value = True
        self.mock_web.search.return_value = [{
            "document": {"title": "Web Title", "url": "http://example.com"},
            "snippet": "Web answer",
        }]
        with patch.object(self.client, "search", return_value=[]):
            result = self.client.query("unknown topic")
            self.assertIn("Web Search Results", result["answer"])
            self.mock_web.search.assert_called()


if __name__ == "__main__":
    unittest.main()
