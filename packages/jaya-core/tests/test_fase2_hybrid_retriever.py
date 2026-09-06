"""
test_fase2_hybrid_retriever.py — Unit tests for HybridRetriever (Fase 2 JAYA_CORE)

Tests cover:
  - BM25SparseIndex: add & search
  - DenseVectorIndex: helper utils (no model needed)
  - MicroGraphRAG: node/edge add, neighbor traversal, entity extraction
  - HybridRetriever: RRF fusion, retrieve_facts compatibility
"""

import sys
import os
import struct
import math
import tempfile
from pathlib import Path

repo_root = Path(__file__).resolve().parents[3]
jaya_core_dir = repo_root / "packages" / "jaya-core" / "src"
sys.path.insert(0, str(jaya_core_dir))

import sqlite3
import pytest
from jaya_core.brain_v2.soul.hybrid_retriever import (
    BM25SparseIndex,
    DenseVectorIndex,
    MicroGraphRAG,
    HybridRetriever,
    _blob_to_vec,
    _vec_to_blob,
    _cosine,
    _tokenize_bm25,
    RRF_K,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_db():
    """In-memory SQLite connection for tests."""
    conn = sqlite3.connect(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def tmp_retriever(tmp_path):
    """HybridRetriever backed by a temporary file DB."""
    db_path = str(tmp_path / "test_hybrid.db")
    yield HybridRetriever(db_path=db_path)


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_blob_roundtrip(self):
        vec = [0.1, 0.2, 0.5, -0.3, 1.0]
        blob = _vec_to_blob(vec)
        recovered = _blob_to_vec(blob)
        assert len(recovered) == len(vec)
        for a, b in zip(vec, recovered):
            assert abs(a - b) < 1e-5

    def test_cosine_identical(self):
        v = [1.0, 0.0, 0.0]
        assert abs(_cosine(v, v) - 1.0) < 1e-6

    def test_cosine_orthogonal(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        assert abs(_cosine(a, b)) < 1e-6

    def test_cosine_zero_vector(self):
        assert _cosine([0.0, 0.0], [1.0, 2.0]) == 0.0

    def test_tokenize_bm25(self):
        tokens = _tokenize_bm25("Hello, JAYA! Apa kabar?")
        assert "hello" in tokens
        assert "jaya" in tokens
        assert "apa" in tokens
        assert "kabar" in tokens


# ---------------------------------------------------------------------------
# BM25 Sparse Index Tests
# ---------------------------------------------------------------------------

class TestBM25SparseIndex:
    def test_add_and_count(self, tmp_db):
        idx = BM25SparseIndex(tmp_db)
        idx.add("doc1", "Skripsi Federated Learning", "Penelitian ini mengkaji federated learning pada sistem IoT.", "test")
        assert idx.count() == 1

    def test_search_returns_results(self, tmp_db):
        idx = BM25SparseIndex(tmp_db)
        idx.add("doc1", "Skripsi Federated Learning", "federated learning sistem privasi data.", "test")
        idx.add("doc2", "Python Programming", "Python digunakan untuk data science.", "test")
        results = idx.search("federated learning", limit=5)
        assert len(results) >= 1
        assert results[0]["chunk_id"] == "doc1"

    def test_search_empty_query(self, tmp_db):
        idx = BM25SparseIndex(tmp_db)
        results = idx.search("", limit=5)
        assert results == []

    def test_multiple_docs(self, tmp_db):
        idx = BM25SparseIndex(tmp_db)
        for i in range(5):
            idx.add(f"doc{i}", f"Topik {i}", f"Konten dokumen nomor {i} tentang riset.", "test")
        assert idx.count() == 5


# ---------------------------------------------------------------------------
# MicroGraphRAG Tests
# ---------------------------------------------------------------------------

class TestMicroGraphRAG:
    def test_add_node_and_edge(self, tmp_db):
        g = MicroGraphRAG(tmp_db)
        g.add_node("python", "Python Programming Language", "concept")
        g.add_node("data_science", "Data Science", "concept")
        g.add_edge("python", "digunakan_untuk", "data_science", weight=0.9)
        stats = g.stats()
        assert stats["nodes"] >= 2
        assert stats["edges"] >= 1

    def test_neighbor_traversal(self, tmp_db):
        g = MicroGraphRAG(tmp_db)
        g.add_edge("machine_learning", "bagian_dari", "artificial_intelligence")
        g.add_edge("artificial_intelligence", "digunakan_dalam", "robotika")
        neighbors = g.neighbors("machine_learning", max_hops=2)
        node_names = [n["node"] for n in neighbors]
        assert "artificial_intelligence" in node_names

    def test_entity_extraction(self, tmp_db):
        g = MicroGraphRAG(tmp_db)
        text = "Federated learning adalah metode machine learning yang mengutamakan privasi data. Python merupakan bahasa pemrograman populer."
        count = g.extract_entities_from_text(text, source_doc="bab2")
        assert count >= 1
        stats = g.stats()
        assert stats["edges"] >= 1

    def test_path_finding(self, tmp_db):
        g = MicroGraphRAG(tmp_db)
        g.add_edge("A", "leads_to", "B")
        g.add_edge("B", "leads_to", "C")
        path = g.query_path("A", "C", max_hops=3)
        assert path is not None
        assert "A" in path
        assert "C" in path

    def test_path_not_found(self, tmp_db):
        g = MicroGraphRAG(tmp_db)
        g.add_node("X", "X")
        g.add_node("Y", "Y")
        # No edge between X and Y
        path = g.query_path("X", "Y", max_hops=2)
        assert path is None


# ---------------------------------------------------------------------------
# HybridRetriever Integration Tests (BM25 only, no model needed)
# ---------------------------------------------------------------------------

class TestHybridRetriever:
    def test_add_document_bm25(self, tmp_retriever):
        result = tmp_retriever.add_document(
            "doc1",
            "Skripsi Federated Learning",
            "Penelitian ini mengkaji federated learning pada sistem terdistribusi.",
            source="bab1",
            extract_graph=True,
        )
        assert result["bm25_indexed"] is True
        assert result["doc_id"] == "doc1"

    def test_retrieve_bm25_fallback(self, tmp_retriever):
        """Test that retrieval works even without dense model (BM25 only path)."""
        tmp_retriever.add_document("doc1", "Federated Learning", "federated learning privasi data.", extract_graph=False)
        tmp_retriever.add_document("doc2", "Deep Learning", "neural network arsitektur.", extract_graph=False)
        # Force dense model to None to test BM25-only path
        tmp_retriever._dense._model = None
        results = tmp_retriever.retrieve("federated learning", limit=3)
        # Should still return results from BM25
        assert isinstance(results, list)

    def test_status(self, tmp_retriever):
        status = tmp_retriever.status()
        assert "bm25_chunks" in status
        assert "dense_chunks" in status
        assert "graph" in status

    def test_add_knowledge_compatibility(self, tmp_retriever):
        result = tmp_retriever.add_knowledge("Indonesia", "Indonesia adalah negara kepulauan terbesar.")
        assert result["bm25_indexed"] is True

    def test_retrieve_facts_format(self, tmp_retriever):
        """retrieve_facts() must return list of dicts with 'content' key."""
        tmp_retriever.add_document("f1", "JAYA AI", "JAYA adalah asisten AI berdaulat.", extract_graph=False)
        tmp_retriever._dense._model = None  # BM25 only
        facts = tmp_retriever.retrieve_facts("JAYA asisten", limit=2)
        assert isinstance(facts, list)
        for f in facts:
            assert "content" in f
            assert "source" in f


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
