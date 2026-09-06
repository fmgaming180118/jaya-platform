"""Grounding and versioned RAG evaluation contract tests."""

from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from jaya_research.research.evaluation_cli import build_fixture_retriever
from jaya_research.research.rag_evaluation import (
    EvaluationRunContext,
    RAGEvaluationError,
    evaluate_retriever,
    load_evaluation_dataset,
    write_evaluation_report,
)
from jaya_research.research.retrieval_evidence import (
    AnswerStatus,
    RetrievalEvidenceError,
    build_grounded_response,
    enrich_chunk_metadata,
)

DATASET_PATH = (
    Path(__file__).resolve().parents[1]
    / "benchmarks"
    / "baselines"
    / "rag_smoke_v2.json"
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


def test_source_label_cannot_masquerade_as_complete_provenance() -> None:
    content = "A labelled chunk without an openable evidence location."
    metadata = enrich_chunk_metadata(
        content,
        {
            "source": "local",
            "page_number": 1,
            "word_start": 0,
            "word_end": len(content.split()),
            "license_id": "CC-BY-4.0",
        },
    )

    response = build_grounded_response(
        [{"content": content, "score": 0.9, "metadata": metadata}]
    )

    assert metadata["source_uri_kind"] == "DERIVED_LABEL"
    assert response["evidence_quality"] == "INCOMPLETE_PROVENANCE"
    assert response["promotable"] is False


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
    dataset = load_evaluation_dataset(DATASET_PATH)

    def retriever(query: str, _top_k: int):
        if "alpha" in query.casefold():
            return [_result("Alpha evidence.", source_id="synthetic-alpha")]
        if "beta" in query.casefold():
            return [_result("Beta evidence.", source_id="synthetic-beta")]
        return []

    clock_values = iter([0, 1_000_000, 1_000_000, 3_000_000, 3_000_000, 6_000_000])
    report = evaluate_retriever(
        dataset,
        retriever,
        target=0.85,
        clock_ns=lambda: next(clock_values),
    )

    assert report["local_target_met"] is True
    assert report["production_gate_passed"] is False
    assert report["status"] == "LOCAL_SMOKE_PASSED"
    assert all(value == 1.0 for value in report["metrics"].values())
    assert report["dataset"]["representation_status"] == "SMOKE_ONLY"
    assert report["run"]["attested"] is False
    assert report["latency_ms"] == {"p50": 2.0, "p95": 3.0, "max": 3.0}
    assert len(report["report_sha256"]) == 64


def test_dataset_digest_tampering_is_rejected(tmp_path: Path) -> None:
    source = DATASET_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["entries"][0]["query"] = "tampered query"
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(RAGEvaluationError, match="digest"):
        load_evaluation_dataset(path)


def _canonical_digest(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _write_resigned_dataset(path: Path, payload: dict) -> Path:
    unsigned = {key: value for key, value in payload.items() if key != "sha256"}
    payload = {**unsigned, "sha256": _canonical_digest(unsigned)}
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_dataset_requires_license_provenance_and_external_representation_approval(
    tmp_path: Path,
) -> None:
    source = DATASET_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["license"] = {"id": "UNKNOWN", "url": ""}
    invalid_license = _write_resigned_dataset(tmp_path / "license.json", payload)
    with pytest.raises(RAGEvaluationError, match="license"):
        load_evaluation_dataset(invalid_license)

    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["representativeness"]["status"] = "APPROVED_REPRESENTATIVE"
    unapproved = _write_resigned_dataset(tmp_path / "unapproved.json", payload)
    with pytest.raises(RAGEvaluationError, match="external approval"):
        load_evaluation_dataset(unapproved)


def test_source_content_digest_and_relevant_ids_are_validated(tmp_path: Path) -> None:
    source = DATASET_PATH
    payload = json.loads(source.read_text(encoding="utf-8"))
    payload["sources"][0]["content"] = "changed without source digest update"
    path = _write_resigned_dataset(tmp_path / "source-tamper.json", payload)

    with pytest.raises(RAGEvaluationError, match="source contract"):
        load_evaluation_dataset(path)


def test_report_is_reproducible_with_injected_clock_and_write_once(
    tmp_path: Path,
) -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)

    def retriever(query: str, _top_k: int):
        if "Alpha" in query:
            return [_result("Alpha evidence.", source_id="synthetic-alpha")]
        if "Beta" in query:
            return [_result("Beta evidence.", source_id="synthetic-beta")]
        return []

    context = EvaluationRunContext(
        runner_id="ci-runner",
        commit_sha="a" * 40,
        code_sha256="b" * 64,
        environment_id="ci-python-3.11",
    )

    def run_with(latencies: list[int]):
        ticks = [0]
        for latency in latencies:
            ticks.extend([ticks[-1], ticks[-1] + latency])
        values = iter(ticks[1:])
        return evaluate_retriever(
            dataset,
            retriever,
            run_context=context,
            clock_ns=lambda: next(values),
        )

    first = run_with([1_000_000, 2_000_000, 3_000_000])
    second = run_with([1_000_000, 2_000_000, 3_000_000])
    changed = run_with([2_000_000, 2_000_000, 3_000_000])

    assert first == second
    assert first["report_sha256"] == second["report_sha256"]
    assert first["production_gate_passed"] is False
    report_path = write_evaluation_report(first, tmp_path / "report.json")
    assert write_evaluation_report(second, report_path) == report_path
    with pytest.raises(RAGEvaluationError, match="overwrite"):
        write_evaluation_report(changed, report_path)


def test_malformed_retriever_result_fails_instead_of_scoring_zero() -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)

    with pytest.raises(RAGEvaluationError, match="source_id"):
        evaluate_retriever(dataset, lambda _query, _top_k: [{"score": 0.9}])


def test_repository_fixture_runner_is_bilingual_and_abstains() -> None:
    dataset = load_evaluation_dataset(DATASET_PATH)
    retriever = build_fixture_retriever(dataset)

    alpha = retriever("Which evidence protocol does Alpha use?", 5)
    beta = retriever("Protokol bukti apa yang digunakan Beta?", 5)
    unknown = retriever("Which source documents a quantum weather controller?", 5)

    assert [item["metadata"]["source_id"] for item in alpha] == ["synthetic-alpha"]
    assert [item["metadata"]["source_id"] for item in beta] == ["synthetic-beta"]
    assert unknown == []
    assert alpha[0]["metadata"]["license_id"] == "CC0-1.0"
