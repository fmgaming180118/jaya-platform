"""Integration tests for grounded responses emitted by both RAG clients."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from research.enhanced_rag import EnhancedRAGClient  # noqa: E402
from research.nvidia_rag_client import NVIDIARAGClient  # noqa: E402
from research.retrieval_evidence import (  # noqa: E402
    AnswerStatus,
    RetrievalEvidenceError,
    enrich_chunk_metadata,
)

CLIENT_TYPES = (EnhancedRAGClient, NVIDIARAGClient)
CITATION_FIELDS = {
    "source_id",
    "source_uri",
    "page_number",
    "span_start",
    "span_end",
    "chunk_sha256",
    "retrieval_score",
    "score_kind",
    "accessed_at",
    "license_id",
}


def _evidence(
    content: str,
    *,
    score: float = 0.9,
    source_id: str = "paper-1",
    claim_id: str | None = None,
    claim_value: str | None = None,
) -> dict[str, Any]:
    metadata = enrich_chunk_metadata(
        content,
        {
            "source_id": source_id,
            "source_uri": f"https://evidence.example/{source_id}",
            "page_number": 7,
            "word_start": 10,
            "word_end": 10 + len(content.split()),
            "license_id": "CC-BY-4.0",
            "claim_id": claim_id,
            "claim_value": claim_value,
        },
        accessed_at="2026-07-27T00:00:00+00:00",
    )
    return {
        "content": content,
        "snippet": content,
        "score": score,
        "metadata": metadata,
        "document": metadata,
    }


def _query_client(
    client_type: type[EnhancedRAGClient] | type[NVIDIARAGClient],
    results: list[dict[str, Any]],
) -> dict[str, Any]:
    client = client_type.__new__(client_type)
    client.web_search = None
    client.search = MagicMock(return_value=results)
    return client.query(
        "A phrase that is not present in retrieved evidence.",
        top_k=5,
        web_fallback=False,
    )


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
def test_client_ingestion_enrichment_and_provenance_survive_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    client_type: type[Any],
) -> None:
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    content = "Persisted evidence has immutable provenance."
    metadata = {
        "source": "persisted-paper.txt",
        "source_id": "persisted-paper",
        "source_uri": "https://evidence.example/persisted-paper",
        "page_number": 3,
        "license_id": "CC-BY-4.0",
        "accessed_at": "2026-07-27T00:00:00+00:00",
    }
    client = client_type(
        vector_store_path=str(tmp_path),
        workspace_id="grounded",
    )
    client.web_search = None
    ingestion = client.ingest_text(content, metadata=metadata)
    assert ingestion["chunks_added"] == 1

    reloaded = client_type(
        vector_store_path=str(tmp_path),
        workspace_id="grounded",
    )
    reloaded.web_search = None
    result = reloaded.search(content, top_k=1)[0]

    persisted = result["metadata"]
    assert persisted["source_id"] == "persisted-paper"
    assert persisted["source_uri"].startswith("https://")
    assert persisted["page_number"] == 3
    assert persisted["word_start"] == 0
    assert persisted["word_end"] == len(content.split())
    assert persisted["license_id"] == "CC-BY-4.0"
    assert persisted["accessed_at"] == "2026-07-27T00:00:00+00:00"
    assert len(persisted["chunk_sha256"]) == 64
    assert persisted["embedding"]["provider"] == "jaya_local"

    response = reloaded.query(content, top_k=1, web_fallback=False)
    citation = response["citations"][0]
    assert CITATION_FIELDS <= citation.keys()
    assert citation["chunk_sha256"] == persisted["chunk_sha256"]
    assert response["sources"] == [persisted["source_uri"]]


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
def test_low_score_causes_explicit_abstention(client_type: type[Any]) -> None:
    response = _query_client(
        client_type,
        [_evidence("This retrieval is too weak.", score=0.2)],
    )

    assert response["status"] == AnswerStatus.ABSTAINED_LOW_CONFIDENCE.value
    assert response["claims"] == []
    assert response["citations"] == []
    assert response["sources"] == []
    assert response["uses_internal_knowledge"] is False


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
def test_explicit_conflict_is_reported_without_synthesis(
    client_type: type[Any],
) -> None:
    response = _query_client(
        client_type,
        [
            _evidence(
                "The intervention increased the outcome.",
                source_id="positive-study",
                claim_id="effect-direction",
                claim_value="increase",
            ),
            _evidence(
                "The intervention decreased the outcome.",
                source_id="negative-study",
                claim_id="effect-direction",
                claim_value="decrease",
            ),
        ],
    )

    assert response["status"] == AnswerStatus.CONFLICTING_EVIDENCE.value
    assert response["claims"] == []
    assert len(response["citations"]) == 2
    assert response["promotable"] is False
    assert response["uses_internal_knowledge"] is False
    assert "increased" not in response["answer"]
    assert "decreased" not in response["answer"]


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
def test_tampered_chunk_digest_is_rejected_by_query(
    client_type: type[Any],
) -> None:
    result = _evidence("Digest-bound evidence.")
    result["metadata"]["chunk_sha256"] = "0" * 64

    with pytest.raises(RetrievalEvidenceError, match="hash"):
        _query_client(client_type, [result])


@pytest.mark.parametrize("client_type", CLIENT_TYPES)
def test_answer_is_extractive_and_every_claim_resolves_to_full_citation(
    client_type: type[Any],
) -> None:
    evidence_text = "The retrieved measurement is exactly 42."
    response = _query_client(client_type, [_evidence(evidence_text)])

    assert response["status"] == AnswerStatus.ANSWERED.value
    assert response["uses_internal_knowledge"] is False
    assert evidence_text in response["answer"]
    assert "A phrase that is not present" not in response["answer"]

    citations_by_id = {
        citation["citation_id"]: citation
        for citation in response["citations"]
    }
    for claim in response["claims"]:
        assert claim["text"] == evidence_text
        assert claim["claim_kind"] == "EXTRACTIVE_RETRIEVAL"
        for citation_id in claim["citation_ids"]:
            assert CITATION_FIELDS <= citations_by_id[citation_id].keys()
