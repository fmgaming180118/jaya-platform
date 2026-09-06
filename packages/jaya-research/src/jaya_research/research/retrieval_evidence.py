"""Citation, provenance, abstention, and conflict contracts for retrieval."""

from __future__ import annotations

import hashlib
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


class RetrievalEvidenceError(ValueError):
    """Raised when retrieved content or provenance is internally inconsistent."""


class AnswerStatus(str, Enum):
    ANSWERED = "ANSWERED"
    ABSTAINED_NO_EVIDENCE = "ABSTAINED_NO_EVIDENCE"
    ABSTAINED_LOW_CONFIDENCE = "ABSTAINED_LOW_CONFIDENCE"
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"


@dataclass(frozen=True)
class Citation:
    """Trace one extractive claim to an immutable retrieved chunk."""

    citation_id: str
    source_id: str
    source_uri: str
    page_number: int | None
    span_start: int | None
    span_end: int | None
    chunk_sha256: str
    retrieval_score: float | None
    score_kind: str
    accessed_at: str
    license_id: str
    snippet: str
    provenance_complete: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_traceable_source_uri(value: str) -> bool:
    """Reject labels masquerading as an openable evidence location."""
    normalized = value.strip()
    if not normalized or normalized.startswith("inline://"):
        return False
    parsed = urlparse(normalized)
    if parsed.scheme:
        return parsed.scheme.casefold() not in {"inline", "javascript", "data"}
    if Path(normalized).is_absolute() or PureWindowsPath(normalized).is_absolute():
        return True
    posix = PurePosixPath(normalized)
    return (
        len(posix.parts) >= 2
        and not posix.is_absolute()
        and all(part not in {"", ".", ".."} for part in posix.parts)
    )


def enrich_chunk_metadata(
    content: str,
    metadata: Mapping[str, Any] | None,
    *,
    accessed_at: str | None = None,
) -> dict[str, Any]:
    """Attach deterministic chunk identity and explicit provenance fields."""
    normalized = dict(metadata or {})
    chunk_sha256 = _sha256(content)
    supplied_hash = str(normalized.get("chunk_sha256") or "")
    if supplied_hash and supplied_hash != chunk_sha256:
        raise RetrievalEvidenceError("Supplied chunk hash does not match content")

    explicit_source_uri = str(
        normalized.get("source_uri")
        or normalized.get("uri")
        or normalized.get("url")
        or normalized.get("path")
        or normalized.get("file_path")
        or ""
    ).strip()
    derived_source_label = str(
        normalized.get("source")
        or normalized.get("file_name")
        or ""
    ).strip()
    source_uri = explicit_source_uri or derived_source_label
    supplied_uri_kind = str(normalized.get("source_uri_kind") or "").strip()
    source_uri_kind = supplied_uri_kind or (
        "PROVIDED"
        if explicit_source_uri
        else ("DERIVED_LABEL" if derived_source_label else "INLINE")
    )
    explicit_source_id = str(normalized.get("source_id") or "").strip()
    source_id = explicit_source_id or (
        f"source-{_sha256(source_uri)[:20]}"
        if source_uri
        else f"inline-{chunk_sha256[:20]}"
    )
    license_id = str(
        normalized.get("license_id")
        or normalized.get("license")
        or "UNKNOWN"
    ).strip()
    normalized.update(
        {
            "source_id": source_id,
            "source_uri": source_uri or f"inline://{chunk_sha256}",
            "source_uri_kind": source_uri_kind,
            "chunk_sha256": chunk_sha256,
            "accessed_at": str(
                normalized.get("accessed_at") or accessed_at or _utc_now()
            ),
            "license_id": license_id or "UNKNOWN",
            "source_id_kind": (
                "PROVIDED" if explicit_source_id else "DERIVED_SHA256"
            ),
        }
    )
    return normalized


def _metadata_for(result: Mapping[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata")
    document = result.get("document")
    merged: dict[str, Any] = {}
    if isinstance(document, Mapping):
        merged.update(document)
    if isinstance(metadata, Mapping):
        merged.update(metadata)
    for key in (
        "source_id",
        "source_uri",
        "source_uri_kind",
        "uri",
        "url",
        "path",
        "file_path",
        "file_name",
        "source",
        "title",
        "license_id",
        "accessed_at",
        "claim_id",
        "claim_value",
    ):
        if key in result and key not in merged:
            merged[key] = result[key]
    return merged


def citation_from_result(
    result: Mapping[str, Any],
    citation_index: int,
) -> Citation:
    """Validate one retrieval result and turn it into a citation."""
    content = str(result.get("content") or result.get("snippet") or "").strip()
    if not content:
        raise RetrievalEvidenceError("Retrieved evidence has no content")
    metadata = enrich_chunk_metadata(content, _metadata_for(result))
    supplied_hash = str(_metadata_for(result).get("chunk_sha256") or "")
    if supplied_hash and supplied_hash != metadata["chunk_sha256"]:
        raise RetrievalEvidenceError("Retrieved chunk digest mismatch")

    raw_score = result.get("score")
    score: float | None = None
    score_kind = "UNSCORED"
    if raw_score is not None:
        try:
            score = float(raw_score)
        except (TypeError, ValueError) as exc:
            raise RetrievalEvidenceError("Retrieval score is not numeric") from exc
        if not math.isfinite(score):
            raise RetrievalEvidenceError("Retrieval score must be finite")
        score_kind = str(result.get("score_kind") or "COSINE_SIMILARITY")

    page_value = metadata.get("page_number")
    try:
        page_number = int(page_value) if page_value is not None else None
    except (TypeError, ValueError) as exc:
        raise RetrievalEvidenceError("Citation page number is invalid") from exc

    def optional_int(name: str) -> int | None:
        value = metadata.get(name)
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise RetrievalEvidenceError(f"Citation {name} is invalid") from exc

    source_uri = str(metadata["source_uri"])
    license_id = str(metadata["license_id"])
    provenance_complete = bool(
        metadata.get("source_uri_kind") == "PROVIDED"
        and _is_traceable_source_uri(source_uri)
        and page_number is not None
        and optional_int("word_start") is not None
        and optional_int("word_end") is not None
        and license_id.upper() not in {"", "UNKNOWN", "UNSPECIFIED"}
    )
    return Citation(
        citation_id=f"CIT-{citation_index}",
        source_id=str(metadata["source_id"]),
        source_uri=source_uri,
        page_number=page_number,
        span_start=optional_int("word_start"),
        span_end=optional_int("word_end"),
        chunk_sha256=str(metadata["chunk_sha256"]),
        retrieval_score=score,
        score_kind=score_kind,
        accessed_at=str(metadata["accessed_at"]),
        license_id=license_id,
        snippet=content[:800],
        provenance_complete=provenance_complete,
    )


def _has_explicit_conflict(results: Sequence[Mapping[str, Any]]) -> bool:
    values_by_claim: dict[str, set[str]] = {}
    for result in results:
        metadata = _metadata_for(result)
        claim_id = str(metadata.get("claim_id") or "").strip()
        claim_value = str(metadata.get("claim_value") or "").strip().casefold()
        if claim_id and claim_value:
            values_by_claim.setdefault(claim_id, set()).add(claim_value)
    return any(len(values) > 1 for values in values_by_claim.values())


def build_grounded_response(
    local_results: Sequence[Mapping[str, Any]],
    web_results: Sequence[Mapping[str, Any]] = (),
    *,
    min_local_score: float = 0.55,
) -> dict[str, Any]:
    """Build an extractive response or abstain; never add internal knowledge."""
    if not 0.0 <= min_local_score <= 1.0:
        raise ValueError("min_local_score must be between 0 and 1")

    accepted: list[Mapping[str, Any]] = []
    had_local = bool(local_results)
    for result in local_results:
        try:
            score = float(result.get("score", 0.0))
        except (TypeError, ValueError):
            continue
        if math.isfinite(score) and score >= min_local_score:
            accepted.append(result)
    accepted.extend(web_results)

    if not accepted:
        status = (
            AnswerStatus.ABSTAINED_LOW_CONFIDENCE
            if had_local
            else AnswerStatus.ABSTAINED_NO_EVIDENCE
        )
        return {
            "status": status.value,
            "answer": (
                "Abstained: retrieved evidence was below the configured "
                "confidence threshold."
                if had_local
                else "Abstained: no retrievable evidence was available."
            ),
            "claims": [],
            "citations": [],
            "sources": [],
            "promotable": False,
            "uses_internal_knowledge": False,
        }

    citations = [
        citation_from_result(result, index)
        for index, result in enumerate(accepted, start=1)
    ]
    if _has_explicit_conflict(accepted):
        return {
            "status": AnswerStatus.CONFLICTING_EVIDENCE.value,
            "answer": (
                "Conflicting evidence was retrieved. No reconciled claim was "
                "produced; review the cited sources."
            ),
            "claims": [],
            "citations": [citation.to_dict() for citation in citations],
            "sources": [citation.source_uri for citation in citations],
            "promotable": False,
            "uses_internal_knowledge": False,
        }

    claims = [
        {
            "claim_id": f"CLAIM-{index}",
            "text": citation.snippet,
            "citation_ids": [citation.citation_id],
            "claim_kind": "EXTRACTIVE_RETRIEVAL",
        }
        for index, citation in enumerate(citations, start=1)
    ]
    answer = "\n".join(
        f"- [{citation.citation_id}] {citation.snippet}"
        for citation in citations
    )
    all_provenance_complete = all(
        citation.provenance_complete for citation in citations
    )
    return {
        "status": AnswerStatus.ANSWERED.value,
        "answer": answer,
        "claims": claims,
        "citations": [citation.to_dict() for citation in citations],
        "sources": [citation.source_uri for citation in citations],
        "evidence_quality": (
            "COMPLETE_PROVENANCE"
            if all_provenance_complete
            else "INCOMPLETE_PROVENANCE"
        ),
        "promotable": all_provenance_complete,
        "uses_internal_knowledge": False,
    }
