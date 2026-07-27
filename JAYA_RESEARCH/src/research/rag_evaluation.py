"""Versioned, deterministic evaluation harness for grounded retrieval."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .retrieval_evidence import build_grounded_response

DATASET_SCHEMA_VERSION = "jaya-rag-eval-v1"
REPORT_SCHEMA_VERSION = "jaya-rag-eval-report-v1"


class RAGEvaluationError(ValueError):
    """Raised when an evaluation dataset or retriever result is invalid."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RAGEvaluationDataset:
    dataset_id: str
    version: str
    license_id: str
    representative: bool
    entries: tuple[dict[str, Any], ...]
    sha256: str


def load_evaluation_dataset(path: str | Path) -> RAGEvaluationDataset:
    """Load and validate a legal, versioned retrieval dataset."""
    dataset_path = Path(path)
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RAGEvaluationError("Evaluation dataset could not be loaded") from exc
    if not isinstance(payload, dict):
        raise RAGEvaluationError("Evaluation dataset must be a JSON object")
    if payload.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise RAGEvaluationError("Unsupported evaluation dataset schema")
    dataset_id = str(payload.get("dataset_id") or "").strip()
    version = str(payload.get("version") or "").strip()
    license_id = str(payload.get("license") or "").strip()
    entries = payload.get("entries")
    if not dataset_id or not version or not license_id:
        raise RAGEvaluationError(
            "dataset_id, version, and license are required"
        )
    if not isinstance(entries, list) or not entries:
        raise RAGEvaluationError("Evaluation dataset entries are required")

    normalized_entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise RAGEvaluationError("Each evaluation entry must be an object")
        entry_id = str(entry.get("id") or "").strip()
        query = str(entry.get("query") or "").strip()
        relevant = entry.get("relevant_source_ids")
        expect_abstain = entry.get("expect_abstain") is True
        if (
            not entry_id
            or entry_id in seen_ids
            or not query
            or not isinstance(relevant, list)
            or (not expect_abstain and not relevant)
            or any(not isinstance(item, str) or not item for item in relevant)
        ):
            raise RAGEvaluationError("Evaluation entry contract is invalid")
        seen_ids.add(entry_id)
        normalized_entries.append(
            {
                "id": entry_id,
                "query": query,
                "relevant_source_ids": list(relevant),
                "expect_abstain": expect_abstain,
            }
        )

    unsigned = {key: value for key, value in payload.items() if key != "sha256"}
    computed_digest = _digest(unsigned)
    supplied_digest = str(payload.get("sha256") or "")
    if supplied_digest and supplied_digest != computed_digest:
        raise RAGEvaluationError("Evaluation dataset digest mismatch")
    return RAGEvaluationDataset(
        dataset_id=dataset_id,
        version=version,
        license_id=license_id,
        representative=payload.get("representative") is True,
        entries=tuple(normalized_entries),
        sha256=computed_digest,
    )


def _source_id(result: Mapping[str, Any]) -> str:
    metadata = result.get("metadata")
    document = result.get("document")
    for container in (metadata, document, result):
        if isinstance(container, Mapping):
            value = (
                container.get("source_id")
                or container.get("source")
                or container.get("file_name")
            )
            if value:
                return str(value)
    return ""


def evaluate_retriever(
    dataset: RAGEvaluationDataset,
    retriever: Callable[[str, int], Sequence[Mapping[str, Any]]],
    *,
    top_k: int = 5,
    target: float = 0.85,
) -> dict[str, Any]:
    """Measure retrieval, citation, grounding, and abstention deterministically."""
    if top_k < 1:
        raise ValueError("top_k must be positive")
    if not 0.0 <= target <= 1.0:
        raise ValueError("target must be between 0 and 1")

    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    citation_scores: list[float] = []
    grounded_scores: list[float] = []
    abstention_scores: list[float] = []
    entry_reports: list[dict[str, Any]] = []

    for entry in dataset.entries:
        raw_results = list(retriever(entry["query"], top_k))
        source_ids = [_source_id(result) for result in raw_results[:top_k]]
        relevant = set(entry["relevant_source_ids"])
        if entry["expect_abstain"]:
            recall = 1.0 if not raw_results else 0.0
            reciprocal_rank = 1.0 if not raw_results else 0.0
        else:
            retrieved_relevant = relevant.intersection(source_ids)
            recall = len(retrieved_relevant) / len(relevant)
            reciprocal_rank = next(
                (
                    1.0 / rank
                    for rank, source_id in enumerate(source_ids, start=1)
                    if source_id in relevant
                ),
                0.0,
            )

        response = build_grounded_response(raw_results)
        citations = response.get("citations", [])
        cited_source_ids = {
            str(citation.get("source_id") or "")
            for citation in citations
            if isinstance(citation, Mapping)
        }
        citation_correctness = (
            1.0
            if entry["expect_abstain"] and not citations
            else (
                len(cited_source_ids.intersection(relevant))
                / max(1, len(cited_source_ids))
            )
        )
        claims = response.get("claims", [])
        citation_ids = {
            str(citation.get("citation_id"))
            for citation in citations
            if isinstance(citation, Mapping)
        }
        grounded = 1.0 if all(
            isinstance(claim, Mapping)
            and bool(set(claim.get("citation_ids") or []).intersection(citation_ids))
            for claim in claims
        ) else 0.0
        abstained = str(response.get("status") or "").startswith("ABSTAINED")
        abstention_accuracy = float(abstained == entry["expect_abstain"])

        recalls.append(recall)
        reciprocal_ranks.append(reciprocal_rank)
        citation_scores.append(citation_correctness)
        grounded_scores.append(grounded)
        abstention_scores.append(abstention_accuracy)
        entry_reports.append(
            {
                "id": entry["id"],
                "recall_at_k": recall,
                "reciprocal_rank": reciprocal_rank,
                "citation_correctness": citation_correctness,
                "groundedness": grounded,
                "abstention_accuracy": abstention_accuracy,
                "response_status": response.get("status"),
            }
        )

    def mean(values: list[float]) -> float:
        value = sum(values) / len(values)
        if not math.isfinite(value):
            raise RAGEvaluationError("Evaluation produced a non-finite metric")
        return round(value, 6)

    metrics = {
        "retrieval_recall_at_k": mean(recalls),
        "mean_reciprocal_rank": mean(reciprocal_ranks),
        "citation_correctness": mean(citation_scores),
        "groundedness": mean(grounded_scores),
        "abstention_accuracy": mean(abstention_scores),
    }
    local_target_met = all(value >= target for value in metrics.values())
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset_id": dataset.dataset_id,
        "dataset_version": dataset.version,
        "dataset_sha256": dataset.sha256,
        "dataset_license": dataset.license_id,
        "representative_dataset": dataset.representative,
        "top_k": top_k,
        "target": target,
        "metrics": metrics,
        "entries": entry_reports,
        "local_target_met": local_target_met,
        "production_gate_passed": local_target_met and dataset.representative,
        "status": (
            "VERIFIED_REPRESENTATIVE"
            if local_target_met and dataset.representative
            else "SMOKE_ONLY_NOT_REPRESENTATIVE"
            if not dataset.representative
            else "REGRESSION_FAILED"
        ),
    }
    return {**report, "report_sha256": _digest(report)}

