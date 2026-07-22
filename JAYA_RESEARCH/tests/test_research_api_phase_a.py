"""Minimal API tests for Phase A endpoints."""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from network.research_api import app  # noqa: E402


class DummyRAG:
    def __init__(self):
        self.ingested = []

    def ingest_text(self, text, metadata=None):
        self.ingested.append((text, metadata))
        return {"status": "success", "chunks_added": 1, "workspace_id": "default"}

    def search(self, query, top_k=5, workspace_id="default"):
        return [{"document": {"file_name": "doc.md"}, "snippet": f"match for {query}", "score": 0.9}]


class DummyGraph:
    def get_context(self, query):
        return f"graph context for {query}"


client = TestClient(app)


@patch("network.research_api.get_engines")
def test_ingest_endpoint(mock_get_engines):
    dummy_rag = DummyRAG()
    mock_get_engines.return_value = (dummy_rag, DummyGraph())

    response = client.post("/ingest", json={"text": "hello rag", "metadata": {"source": "notes.md"}, "workspace_id": "default"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["chunks_added"] == 1


@patch("network.research_api.get_engines")
def test_recursive_research_endpoint(mock_get_engines):
    dummy_rag = DummyRAG()
    mock_get_engines.return_value = (dummy_rag, DummyGraph())

    response = client.post("/research/recursive", json={"query": "RAG", "depth": 2, "workspace_id": "default"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == "RAG"
    assert payload["depth_reached"] >= 1
    assert payload["sources"]
    assert "Vector Context" in payload["synthesis"] or "Graph Context" in payload["synthesis"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-v"]))
