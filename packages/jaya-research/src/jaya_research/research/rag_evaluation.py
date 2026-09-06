"""Versioned and evidence-bearing evaluation for grounded retrieval."""

from __future__ import annotations

import hashlib
import json
import math
import platform
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .retrieval_evidence import build_grounded_response

DATASET_SCHEMA_VERSION = "jaya-rag-eval-v2"
REPORT_SCHEMA_VERSION = "jaya-rag-eval-report-v2"


class RAGEvaluationError(ValueError):
    """Raised when a dataset, retriever result, or report is invalid."""


class RepresentationStatus(str, Enum):
    SMOKE_ONLY = "SMOKE_ONLY"
    CANDIDATE_UNREVIEWED = "CANDIDATE_UNREVIEWED"
    APPROVED_REPRESENTATIVE = "APPROVED_REPRESENTATIVE"


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise RAGEvaluationError("Value is not canonical JSON") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


def _is_commit_sha(value: Any) -> bool:
    text = str(value or "").casefold()
    return len(text) in {40, 64} and all(
        character in "0123456789abcdef" for character in text
    )


@dataclass(frozen=True)
class RAGEvaluationDataset:
    dataset_id: str
    version: str
    license_id: str
    license_url: str
    representation_status: RepresentationStatus
    provenance: dict[str, Any]
    representativeness: dict[str, Any]
    sources: tuple[dict[str, Any], ...]
    entries: tuple[dict[str, Any], ...]
    sha256: str

    @property
    def representative(self) -> bool:
        return self.representation_status is RepresentationStatus.APPROVED_REPRESENTATIVE


@dataclass(frozen=True)
class EvaluationRunContext:
    """Identity needed to reproduce and attest one evaluation run."""

    runner_id: str = "LOCAL_UNATTESTED"
    commit_sha: str = "NOASSERTION"
    code_sha256: str = ""
    environment_id: str = "LOCAL_UNATTESTED"


def load_evaluation_dataset(path: str | Path) -> RAGEvaluationDataset:
    """Load a digest-bound dataset with explicit legal/provenance metadata."""
    dataset_path = Path(path)
    try:
        payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RAGEvaluationError("Evaluation dataset could not be loaded") from exc
    if not isinstance(payload, dict):
        raise RAGEvaluationError("Evaluation dataset must be a JSON object")
    if payload.get("schema_version") != DATASET_SCHEMA_VERSION:
        raise RAGEvaluationError("Unsupported evaluation dataset schema")

    supplied_digest = str(payload.get("sha256") or "").casefold()
    if not _is_sha256(supplied_digest):
        raise RAGEvaluationError("Evaluation dataset requires a SHA-256 digest")
    unsigned = {key: value for key, value in payload.items() if key != "sha256"}
    computed_digest = _digest(unsigned)
    if supplied_digest != computed_digest:
        raise RAGEvaluationError("Evaluation dataset digest mismatch")

    dataset_id = str(payload.get("dataset_id") or "").strip()
    version = str(payload.get("version") or "").strip()
    if not dataset_id or not version:
        raise RAGEvaluationError("dataset_id and version are required")

    license_record = payload.get("license")
    if not isinstance(license_record, Mapping):
        raise RAGEvaluationError("Dataset license metadata is required")
    license_id = str(license_record.get("id") or "").strip()
    license_url = str(license_record.get("url") or "").strip()
    if (
        not license_id
        or license_id.upper() in {"UNKNOWN", "NOASSERTION", "UNVERIFIED"}
        or not license_url.startswith("https://")
    ):
        raise RAGEvaluationError("Dataset requires a verifiable license ID and URL")

    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise RAGEvaluationError("Dataset provenance metadata is required")
    required_provenance = ("origin", "source_uri", "created_at", "methodology")
    if any(not str(provenance.get(field) or "").strip() for field in required_provenance):
        raise RAGEvaluationError("Dataset provenance is incomplete")

    representation = payload.get("representativeness")
    if not isinstance(representation, Mapping):
        raise RAGEvaluationError("Representativeness metadata is required")
    try:
        representation_status = RepresentationStatus(
            str(representation.get("status") or "")
        )
    except ValueError as exc:
        raise RAGEvaluationError("Representativeness status is invalid") from exc
    for field in ("rationale", "sampling_method", "domains", "languages"):
        value = representation.get(field)
        if not value or (field in {"domains", "languages"} and not isinstance(value, list)):
            raise RAGEvaluationError("Representativeness metadata is incomplete")
    if representation_status is RepresentationStatus.APPROVED_REPRESENTATIVE:
        if (
            not str(representation.get("approved_by") or "").strip()
            or not str(representation.get("approved_at") or "").strip()
            or not _is_sha256(representation.get("approval_receipt_sha256"))
            or not str(representation.get("sampling_frame") or "").strip()
        ):
            raise RAGEvaluationError(
                "Representative datasets require external approval and sampling evidence"
            )

    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise RAGEvaluationError("Dataset sources are required")
    sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for source in raw_sources:
        if not isinstance(source, Mapping):
            raise RAGEvaluationError("Each dataset source must be an object")
        source_id = str(source.get("source_id") or "").strip()
        source_uri = str(source.get("source_uri") or "").strip()
        source_license = str(source.get("license_id") or "").strip()
        content = str(source.get("content") or "")
        content_sha256 = str(source.get("content_sha256") or "").casefold()
        if (
            not source_id
            or source_id in source_ids
            or not source_uri
            or source_license != license_id
            or not content
            or not _is_sha256(content_sha256)
            or content_sha256 != hashlib.sha256(content.encode("utf-8")).hexdigest()
        ):
            raise RAGEvaluationError("Dataset source contract is invalid")
        source_ids.add(source_id)
        sources.append(
            {
                "source_id": source_id,
                "source_uri": source_uri,
                "license_id": source_license,
                "content": content,
                "content_sha256": content_sha256,
            }
        )

    raw_entries = payload.get("entries")
    if not isinstance(raw_entries, list) or not raw_entries:
        raise RAGEvaluationError("Evaluation dataset entries are required")
    entries: list[dict[str, Any]] = []
    entry_ids: set[str] = set()
    for entry in raw_entries:
        if not isinstance(entry, Mapping):
            raise RAGEvaluationError("Each evaluation entry must be an object")
        entry_id = str(entry.get("id") or "").strip()
        query = str(entry.get("query") or "").strip()
        query_language = str(entry.get("query_language") or "").strip()
        relevant_raw = entry.get("relevant_source_ids")
        expect_abstain = entry.get("expect_abstain") is True
        if (
            not entry_id
            or entry_id in entry_ids
            or not query
            or not query_language
            or not isinstance(relevant_raw, list)
            or any(not isinstance(item, str) or item not in source_ids for item in relevant_raw)
            or (expect_abstain and relevant_raw)
            or (not expect_abstain and not relevant_raw)
        ):
            raise RAGEvaluationError("Evaluation entry contract is invalid")
        entry_ids.add(entry_id)
        entries.append(
            {
                "id": entry_id,
                "query": query,
                "query_language": query_language,
                "relevant_source_ids": list(dict.fromkeys(relevant_raw)),
                "expect_abstain": expect_abstain,
            }
        )

    return RAGEvaluationDataset(
        dataset_id=dataset_id,
        version=version,
        license_id=license_id,
        license_url=license_url,
        representation_status=representation_status,
        provenance=dict(provenance),
        representativeness=dict(representation),
        sources=tuple(sources),
        entries=tuple(entries),
        sha256=computed_digest,
    )


def _source_id(result: Mapping[str, Any]) -> str:
    for container in (result.get("metadata"), result.get("document"), result):
        if isinstance(container, Mapping):
            value = container.get("source_id")
            if value:
                return str(value)
    return ""


def _validated_results(value: Any, *, top_k: int) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise RAGEvaluationError("Retriever must return a sequence of mappings")
    results: list[Mapping[str, Any]] = []
    for result in list(value)[:top_k]:
        if not isinstance(result, Mapping):
            raise RAGEvaluationError("Retriever result must be a mapping")
        if not _source_id(result):
            raise RAGEvaluationError("Retriever result requires source_id")
        score = result.get("score")
        if score is not None:
            try:
                numeric_score = float(score)
            except (TypeError, ValueError) as exc:
                raise RAGEvaluationError("Retriever score must be numeric") from exc
            if not math.isfinite(numeric_score):
                raise RAGEvaluationError("Retriever score must be finite")
        results.append(result)
    return results


def _mean(values: Sequence[float], metric: str) -> float:
    if not values:
        raise RAGEvaluationError(f"Metric {metric} has no eligible entries")
    value = sum(values) / len(values)
    if not math.isfinite(value):
        raise RAGEvaluationError(f"Metric {metric} is non-finite")
    return round(value, 6)


def _percentile(values: Sequence[float], fraction: float) -> float:
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return round(ordered[index], 3)


def _module_code_sha256() -> str:
    try:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    except OSError:
        return ""


def evaluate_retriever(
    dataset: RAGEvaluationDataset,
    retriever: Callable[[str, int], Sequence[Mapping[str, Any]]],
    *,
    top_k: int = 5,
    target: float = 0.85,
    min_local_score: float = 0.55,
    run_context: EvaluationRunContext | None = None,
    clock_ns: Callable[[], int] = time.perf_counter_ns,
) -> dict[str, Any]:
    """Measure retrieval, citations, grounding, abstention, and latency."""
    if not 1 <= top_k <= 100:
        raise ValueError("top_k must be between 1 and 100")
    if not 0.0 <= target <= 1.0:
        raise ValueError("target must be between 0 and 1")
    if not 0.0 <= min_local_score <= 1.0:
        raise ValueError("min_local_score must be between 0 and 1")

    context = run_context or EvaluationRunContext(code_sha256=_module_code_sha256())
    code_sha256 = context.code_sha256 or _module_code_sha256()
    if code_sha256 and not _is_sha256(code_sha256):
        raise RAGEvaluationError("Run context code_sha256 is invalid")

    recalls: list[float] = []
    hits: list[float] = []
    reciprocal_ranks: list[float] = []
    citation_precision_scores: list[float] = []
    citation_recall_scores: list[float] = []
    grounded_scores: list[float] = []
    abstention_scores: list[float] = []
    latencies_ms: list[float] = []
    entry_reports: list[dict[str, Any]] = []

    for entry in dataset.entries:
        started = clock_ns()
        results = _validated_results(
            retriever(entry["query"], top_k),
            top_k=top_k,
        )
        elapsed_ns = clock_ns() - started
        if elapsed_ns < 0:
            raise RAGEvaluationError("Evaluation clock moved backwards")
        latency_ms = round(elapsed_ns / 1_000_000, 3)
        latencies_ms.append(latency_ms)

        source_ids = [_source_id(result) for result in results]
        relevant = set(entry["relevant_source_ids"])
        response = build_grounded_response(
            results,
            min_local_score=min_local_score,
        )
        citations = [
            citation
            for citation in response.get("citations", [])
            if isinstance(citation, Mapping)
        ]
        claims = [
            claim
            for claim in response.get("claims", [])
            if isinstance(claim, Mapping)
        ]
        cited_source_ids = {
            str(citation.get("source_id") or "") for citation in citations
        }
        citation_ids = {
            str(citation.get("citation_id") or "") for citation in citations
        }
        abstained = str(response.get("status") or "").startswith("ABSTAINED")
        expected_abstain = entry["expect_abstain"]
        abstention_accuracy = float(abstained == expected_abstain)
        abstention_scores.append(abstention_accuracy)

        if expected_abstain:
            recall = None
            hit = None
            reciprocal_rank = None
            citation_precision = 1.0 if not citations else 0.0
            citation_recall = 1.0 if not citations else 0.0
            grounded = 1.0 if abstained and not claims and not citations else 0.0
        else:
            retrieved_relevant = relevant.intersection(source_ids)
            recall = len(retrieved_relevant) / len(relevant)
            hit = float(bool(retrieved_relevant))
            reciprocal_rank = next(
                (
                    1.0 / rank
                    for rank, source_id in enumerate(source_ids, start=1)
                    if source_id in relevant
                ),
                0.0,
            )
            citation_precision = (
                len(cited_source_ids.intersection(relevant)) / len(cited_source_ids)
                if cited_source_ids
                else 0.0
            )
            citation_recall = len(cited_source_ids.intersection(relevant)) / len(relevant)
            grounded = float(
                bool(claims)
                and all(
                    bool(set(claim.get("citation_ids") or []).intersection(citation_ids))
                    for claim in claims
                )
            )
            recalls.append(recall)
            hits.append(hit)
            reciprocal_ranks.append(reciprocal_rank)

        citation_precision_scores.append(citation_precision)
        citation_recall_scores.append(citation_recall)
        grounded_scores.append(grounded)
        entry_reports.append(
            {
                "id": entry["id"],
                "query_language": entry["query_language"],
                "retrieved_source_ids": source_ids,
                "recall_at_k": None if recall is None else round(recall, 6),
                "hit_at_k": hit,
                "reciprocal_rank": (
                    None if reciprocal_rank is None else round(reciprocal_rank, 6)
                ),
                "citation_precision": round(citation_precision, 6),
                "citation_recall": round(citation_recall, 6),
                "groundedness": grounded,
                "abstention_accuracy": abstention_accuracy,
                "response_status": response.get("status"),
                "latency_ms": latency_ms,
            }
        )

    metrics = {
        "retrieval_recall_at_k": _mean(recalls, "retrieval_recall_at_k"),
        "retrieval_hit_rate_at_k": _mean(hits, "retrieval_hit_rate_at_k"),
        "mean_reciprocal_rank": _mean(reciprocal_ranks, "mean_reciprocal_rank"),
        "citation_precision": _mean(citation_precision_scores, "citation_precision"),
        "citation_recall": _mean(citation_recall_scores, "citation_recall"),
        "groundedness": _mean(grounded_scores, "groundedness"),
        "abstention_accuracy": _mean(abstention_scores, "abstention_accuracy"),
    }
    quality_metrics = tuple(metrics.values())
    local_target_met = all(value >= target for value in quality_metrics)
    config = {
        "top_k": top_k,
        "target": target,
        "min_local_score": min_local_score,
    }
    attested_run = bool(
        context.runner_id != "LOCAL_UNATTESTED"
        and context.environment_id != "LOCAL_UNATTESTED"
        and _is_commit_sha(context.commit_sha)
        and code_sha256
    )
    production_gate_passed = bool(
        local_target_met and dataset.representative and attested_run
    )
    report = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "dataset": {
            "id": dataset.dataset_id,
            "version": dataset.version,
            "sha256": dataset.sha256,
            "license_id": dataset.license_id,
            "representation_status": dataset.representation_status.value,
        },
        "run": {
            "runner_id": context.runner_id,
            "commit_sha": context.commit_sha,
            "code_sha256": code_sha256,
            "environment_id": context.environment_id,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "config": config,
            "config_sha256": _digest(config),
            "attested": attested_run,
        },
        "metrics": metrics,
        "latency_ms": {
            "p50": _percentile(latencies_ms, 0.50),
            "p95": _percentile(latencies_ms, 0.95),
            "max": round(max(latencies_ms), 3),
        },
        "entries": entry_reports,
        "local_target_met": local_target_met,
        "production_gate_passed": production_gate_passed,
        "status": (
            "VERIFIED_REPRESENTATIVE"
            if production_gate_passed
            else "LOCAL_SMOKE_PASSED"
            if local_target_met and not dataset.representative
            else "REPRESENTATIVE_RUN_UNATTESTED"
            if local_target_met and dataset.representative
            else "REGRESSION_FAILED"
        ),
    }
    return {**report, "report_sha256": _digest(report)}


def write_evaluation_report(report: Mapping[str, Any], path: str | Path) -> Path:
    """Write once; refuse to overwrite different evidence at the same path."""
    expected_digest = str(report.get("report_sha256") or "")
    unsigned = {key: value for key, value in report.items() if key != "report_sha256"}
    if not _is_sha256(expected_digest) or expected_digest != _digest(unsigned):
        raise RAGEvaluationError("Evaluation report digest is invalid")
    target = Path(path)
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if target.exists():
        try:
            current = target.read_text(encoding="utf-8")
        except OSError as exc:
            raise RAGEvaluationError("Existing report could not be read") from exc
        if current != serialized:
            raise RAGEvaluationError("Refusing to overwrite a different evaluation report")
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(serialized, encoding="utf-8")
    return target
