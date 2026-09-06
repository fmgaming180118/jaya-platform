"""Deterministic offline acceptance tests for the Phase A RAG contract."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pypdf import PdfWriter
from jaya_research.research.enhanced_rag import (
    EnhancedRAGClient,
    NVIDIAEmbeddings,
    ProviderExecutionMode,
    _normalize_vectors,
)
from jaya_research.research.nvidia_rag_client import NVIDIARAGClient
from jaya_research.research.rag_client import NVIDIARAGClient as CompatibilityNVIDIAClient
from jaya_research.research.retrieval_evidence import AnswerStatus, enrich_chunk_metadata


class DeterministicEmbeddingAdapter:
    """Small injected adapter; deterministic and independent from network state."""

    dimension = 32

    def embed_texts(self, texts: list[str]) -> np.ndarray:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            for token in text.casefold().split():
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                vectors[row, int.from_bytes(digest[:4], "big") % self.dimension] += 1
        return _normalize_vectors(vectors)

    @staticmethod
    def get_provenance() -> dict[str, str]:
        return {
            "provider": "test_adapter",
            "model": "deterministic-token-hash",
            "version": "1",
            "type": "test_embedding_adapter",
        }

    @staticmethod
    def get_provider_identity() -> dict[str, Any]:
        return {
            "provider": "test_adapter",
            "model": "deterministic-token-hash",
            "version": "1",
            "implementation_type": "test_embedding_adapter",
            "execution_mode": ProviderExecutionMode.INJECTED.value,
            "is_fallback": False,
            "fallback_reason": None,
        }


def _client(
    store: Path,
    workspace: str,
    client_type: type[EnhancedRAGClient] = EnhancedRAGClient,
) -> EnhancedRAGClient:
    client = client_type(
        vector_store_path=str(store),
        workspace_id=workspace,
        embedder=DeterministicEmbeddingAdapter(),
    )
    client.web_search = None
    return client


@pytest.mark.parametrize("client_type", [EnhancedRAGClient, NVIDIARAGClient])
def test_replace_reload_delete_and_workspace_isolation_share_one_contract(
    tmp_path: Path,
    client_type: type[EnhancedRAGClient],
) -> None:
    store = tmp_path / "shared-store"
    alpha = _client(store, "alpha", client_type)
    beta = _client(store, "beta", client_type)

    first = alpha.ingest_text(
        "alpha obsolete measurement",
        {"source_id": "paper-alpha", "source_uri": "file:///alpha.txt"},
    )
    replacement = alpha.ingest_text(
        "alpha current measurement",
        {"source_id": "paper-alpha", "source_uri": "file:///alpha.txt"},
    )
    beta.ingest_text(
        "beta confidential evidence",
        {"source_id": "paper-beta", "source_uri": "file:///beta.txt"},
    )

    assert first["chunks_added"] == 1
    assert replacement["chunks_added"] == 1
    assert replacement["chunks_replaced"] == 1
    assert alpha.reload()["count"] == 1
    assert beta.reload()["count"] == 1
    assert alpha.get_stats()["total_count"] == 2
    assert all(
        result["metadata"]["workspace_id"] == "alpha"
        for result in alpha.search("beta confidential evidence", top_k=5)
    )
    assert alpha.delete_by_source("paper-alpha") == 1
    assert alpha.reload()["count"] == 0
    assert beta.reload()["count"] == 1
    assert beta.delete_by_source("paper-alpha") == 0


def test_low_context_abstains_and_reports_typed_fallback_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    client = EnhancedRAGClient(
        vector_store_path=str(tmp_path),
        workspace_id="fallback",
        embedder=NVIDIAEmbeddings(),
    )
    client.web_search = None

    response = client.query("evidence that is not indexed", web_fallback=True)

    assert response["status"] == AnswerStatus.ABSTAINED_NO_EVIDENCE.value
    assert response["claims"] == []
    assert response["citations"] == []
    identity = response["provider_identity"]
    assert identity["embedding"]["execution_mode"] == "LOCAL_FALLBACK"
    assert identity["embedding"]["is_fallback"] is True
    assert identity["embedding"]["fallback_reason"] == (
        "NVIDIA_API_KEY_NOT_CONFIGURED"
    )
    assert identity["web_fallback"]["status"] == "UNAVAILABLE"


def test_low_scored_context_is_never_exposed_as_answer_context(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path / "low-score", "low-score")
    weak = {
        "content": "Weakly related evidence.",
        "snippet": "Weakly related evidence.",
        "score": 0.2,
        "metadata": {
            "source_id": "weak-source",
            "source_uri": "https://evidence.example/weak",
        },
    }
    client.search = lambda *_args, **_kwargs: [weak]  # type: ignore[method-assign]

    response = client.query("unrelated question", web_fallback=False)

    assert response["status"] == AnswerStatus.ABSTAINED_LOW_CONFIDENCE.value
    assert response["claims"] == []
    assert client.get_context_for_query("unrelated question") == ""


def test_conflicting_evidence_never_produces_a_synthesized_claim(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path / "conflict", "conflict")
    client.ingest_text(
        "The treatment increased the measured outcome.",
        {
            "source_id": "study-up",
            "source_uri": "https://evidence.example/up",
            "page_number": 4,
            "license_id": "CC-BY-4.0",
            "claim_id": "treatment-direction",
            "claim_value": "increase",
        },
    )
    client.ingest_text(
        "The treatment decreased the measured outcome.",
        {
            "source_id": "study-down",
            "source_uri": "https://evidence.example/down",
            "page_number": 9,
            "license_id": "CC-BY-4.0",
            "claim_id": "treatment-direction",
            "claim_value": "decrease",
        },
    )

    response = client.query(
        "The treatment increased the measured outcome.",
        web_fallback=False,
    )

    assert response["status"] == AnswerStatus.CONFLICTING_EVIDENCE.value
    assert response["claims"] == []
    assert len(response["citations"]) == 2
    assert all(
        {
            "source_id",
            "source_uri",
            "page_number",
            "span_start",
            "span_end",
            "chunk_sha256",
            "retrieval_score",
            "accessed_at",
        }
        <= citation.keys()
        for citation in response["citations"]
    )


def test_provider_error_and_internal_knowledge_metadata_are_not_stored(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path / "rejected", "rejected")

    with pytest.raises(ValueError, match="Provider errors"):
        client.ingest_text(
            "timeout details",
            {"source": "bad", "provider_error": {"code": "timeout"}},
        )
    with pytest.raises(ValueError, match="Internal model knowledge"):
        client.ingest_text(
            "uncited model memory",
            {"source": "internal", "knowledge_origin": "internal_knowledge"},
        )

    assert client.get_stats()["count"] == 0


def test_failed_replacement_preserves_last_persisted_source(
    tmp_path: Path,
) -> None:
    store = tmp_path / "atomic-replace"
    client = _client(store, "atomic")
    client.ingest_text(
        "Last verified source content.",
        {"source_id": "stable-source"},
    )

    class FailingAdapter(DeterministicEmbeddingAdapter):
        def embed_texts(self, texts: list[str]) -> np.ndarray:
            raise RuntimeError("embedding provider unavailable")

    client.embedder = FailingAdapter()
    with pytest.raises(RuntimeError, match="embedding provider unavailable"):
        client.ingest_text(
            "Unpersisted replacement content.",
            {"source_id": "stable-source"},
        )

    reloaded = _client(store, "atomic")
    results = reloaded.search("Last verified source content", top_k=1)
    assert reloaded.get_stats()["count"] == 1
    assert results[0]["content"] == "Last verified source content."


def test_pdf_requiring_ocr_does_not_replace_existing_evidence(
    tmp_path: Path,
) -> None:
    pdf_path = tmp_path / "scan.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    with pdf_path.open("wb") as handle:
        writer.write(handle)
    client = _client(tmp_path / "pdf-store", "pdf")
    client.ingest_text(
        "Previously verified evidence remains available.",
        {"source": pdf_path.name},
    )

    result = client.ingest_file(str(pdf_path))

    assert result["status"] == "requires_ocr"
    assert result["extraction_status"] == "PARTIAL_OCR_REQUIRED"
    assert result["chunks_added"] == 0
    assert client.get_stats()["count"] == 1


def test_compatibility_module_exports_the_real_client() -> None:
    assert CompatibilityNVIDIAClient is NVIDIARAGClient


def test_retrieved_citation_preserves_access_time_and_chunk_digest(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path / "citation", "citation")
    accessed_at = "2026-08-01T00:00:00+00:00"
    text = "The measured latency is 42 milliseconds."
    metadata = enrich_chunk_metadata(
        text,
        {
            "source_id": "latency-paper",
            "source_uri": "https://evidence.example/latency",
            "page_number": 2,
            "word_start": 0,
            "word_end": len(text.split()),
            "license_id": "CC-BY-4.0",
        },
        accessed_at=accessed_at,
    )
    client.ingest_text(text, metadata)

    response = client.query(
        "measured latency 42 milliseconds",
        web_fallback=False,
    )
    citation = response["citations"][0]

    assert citation["accessed_at"] == accessed_at
    assert citation["chunk_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert citation["retrieval_score"] is not None
