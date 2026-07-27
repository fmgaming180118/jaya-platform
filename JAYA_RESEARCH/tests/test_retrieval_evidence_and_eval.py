"""Grounding and versioned RAG evaluation contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.rag_evaluation import (
    RAGEvaluationError,
    evaluate_retriever,
    load_evaluation_dataset,
)
from research.retrieval_evidence import (
    AnswerStatus,
    RetrievalEvidenceError,
    build_grounded_response,
    enrich_chunk_metadata,
)


def _result(
    content: str,
    *,
    source_id: str = "source-a",
    score: float = 0.9,
    claim_id: str | None = None,
    claim_value: str | None = None,
) -> dict:
    metadata = enrich_chunk_metadata(
        content,
        {
            "source_id": source_id,
            "source_uri": f"https://example.test/{source_id}",
            "page_number": 1,
            "word_start": 0,
            "word_end": len(content.split()),
            "license_id": "CC-BY-4.0",
            "claim_id": claim_id,
            "claim_value": claim_value,
        },
        accessed_at="2026-07-26T00:00:00+00:00",
    )
    return {
        "content": content,
        "snippet": content,
        "score": score,
        "metadata": metadata,
        "document": metadata,
    }


def test_answer_claims_have_complete_openable_citations() -> None:
    response = build_grounded_response(
        [_result("The measured value is 42.", source_id="measurement-42")]
    )

    assert response["status"] == AnswerStatus.ANSWERED.value
    assert response["uses_internal_knowledge"] is False
    assert response["promotable"] is True
    assert response["claims"][0]["citation_ids"] == ["CIT-1"]
    citation = response["citations"][0]
    assert citation["source_uri"].startswith("https://")
    assert citation["page_number"] == 1
    assert citation["span_start"] == 0
    assert len(citation["chunk_sha256"]) == 64
    assert citation["retrieval_score"] == 0.9
    assert citation["accessed_at"] == "2026-07-26T00:00:00+00:00"


def test_empty_and_low_confidence_context_abstain() -> None:
    empty = build_grounded_response([])
    low = build_grounded_response([_result("Weak match", score=0.2)])

    assert empty["status"] == AnswerStatus.ABSTAINED_NO_EVIDENCE.value
    assert low["status"] == AnswerStatus.ABSTAINED_LOW_CONFIDENCE.value
    assert empty["claims"] == []
    assert low["promotable"] is False


def test_explicitly_conflicting_sources_are_not_reconciled_silently() -> None:
    response = build_grounded_response(
        [
            _result(
                "Treatment increased the outcome.",
                source_id="source-positive",
                claim_id="treatment-effect",
                claim_value="increase",
            ),
            _result(
                "Treatment decreased the outcome.",
                source_id="source-negative",
                claim_id="treatment-effect",
                claim_value="decrease",
            ),
        ]
    )

    assert response["status"] == AnswerStatus.CONFLICTING_EVIDENCE.value
    assert response["claims"] == []
    assert len(response["citations"]) == 2
    assert response["promotable"] is False


def test_tampered_chunk_digest_is_rejected() -> None:
    result = _result("Original evidence.")
    result["metadata"]["chunk_sha256"] = "0" * 64

    with pytest.raises(RetrievalEvidenceError, match="hash"):
        build_grounded_response([result])


def test_versioned_smoke_dataset_reports_metrics_but_not_production_gate() -> None:
    dataset_path = (
        Path(__file__).resolve().parents[1]
        / "evaluation"
        / "rag_smoke_v1.json"
    )
    dataset = load_evaluation_dataset(dataset_path)

    def retriever(query: str, _top_k: int):
        if "alpha" in query:
            return [_result("Alpha evidence.", source_id="synthetic-alpha")]
        if "beta" in query:
            return [_result("Beta evidence.", source_id="synthetic-beta")]
        return []

    report = evaluate_retriever(dataset, retriever, target=0.85)

    assert report["local_target_met"] is True
    assert report["production_gate_passed"] is False
    assert report["status"] == "SMOKE_ONLY_NOT_REPRESENTATIVE"
    assert all(value == 1.0 for value in report["metrics"].values())
    assert len(report["report_sha256"]) == 64


def test_dataset_digest_tampering_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "jaya-rag-eval-v1",
                "dataset_id": "tampered",
                "version": "1",
                "license": "CC0-1.0",
                "representative": False,
                "entries": [
                    {
                        "id": "one",
                        "query": "q",
                        "relevant_source_ids": ["s"],
                        "expect_abstain": False,
                    }
                ],
                "sha256": "0" * 64,
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(RAGEvaluationError, match="digest"):
        load_evaluation_dataset(path)

