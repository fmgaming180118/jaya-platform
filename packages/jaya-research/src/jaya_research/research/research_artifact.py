"""Immutable, review-only artifact contract for JAYA Research outputs."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")


class ArtifactValidationError(ValueError):
    """Raised when a research artifact violates the public contract."""


class EvidenceKind(str, Enum):
    """Origin and scientific strength of an artifact's evidence."""

    SIMULATION = "SIMULATION"
    EMPIRICAL = "EMPIRICAL"
    DERIVED = "DERIVED"
    UNVERIFIED = "UNVERIFIED"


class ArtifactStatus(str, Enum):
    """Lifecycle status before a separate consumer reviews an artifact."""

    SIMULATION_ONLY = "SIMULATION_ONLY"
    DRAFT_INCOMPLETE = "DRAFT_INCOMPLETE"
    PENDING_REVIEW = "PENDING_REVIEW"


def _canonical_json(value: Mapping[str, Any]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _content_digest(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ResearchArtifact:
    """Versioned artifact created by Research and reviewed elsewhere."""

    artifact_id: str
    artifact_type: str
    finding_id: str
    evidence_kind: EvidenceKind
    status: ArtifactStatus
    subject: str
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    reproducibility: Mapping[str, Any]
    license_info: Mapping[str, Any]
    confidence: float
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    producer: str = "JAYA_RESEARCH"

    def unsigned_dict(self) -> dict[str, Any]:
        """Return all immutable fields covered by the content digest."""
        return {
            "schema_version": SCHEMA_VERSION,
            "artifact_id": self.artifact_id,
            "artifact_type": self.artifact_type,
            "finding_id": self.finding_id,
            "evidence_kind": self.evidence_kind.value,
            "status": self.status.value,
            "subject": self.subject,
            "payload": dict(self.payload),
            "provenance": dict(self.provenance),
            "reproducibility": dict(self.reproducibility),
            "license": dict(self.license_info),
            "confidence": float(self.confidence),
            "created_at": self.created_at,
            "producer": self.producer,
        }

    def to_dict(self) -> dict[str, Any]:
        """Serialize the artifact and bind every field to a SHA-256 digest."""
        payload = self.unsigned_dict()
        return {**payload, "content_sha256": _content_digest(payload)}


def determine_status(
    *,
    evidence_kind: EvidenceKind,
    provenance: Mapping[str, Any],
    reproducibility: Mapping[str, Any],
    license_info: Mapping[str, Any],
) -> ArtifactStatus:
    """Determine whether evidence is complete enough to request review."""
    if evidence_kind is EvidenceKind.SIMULATION:
        return ArtifactStatus.SIMULATION_ONLY

    source_hashes = provenance.get("source_hashes")
    has_sources = isinstance(source_hashes, list) and bool(source_hashes)
    has_license = bool(str(license_info.get("id") or "").strip())

    if evidence_kind is EvidenceKind.EMPIRICAL:
        reproduced = reproducibility.get("reproduced") is True
        run_count = int(reproducibility.get("run_count") or 0)
        has_dataset = bool(str(provenance.get("dataset_sha256") or "").strip())
        if (
            has_sources
            and has_license
            and has_dataset
            and reproduced
            and run_count >= 2
        ):
            return ArtifactStatus.PENDING_REVIEW
        return ArtifactStatus.DRAFT_INCOMPLETE

    if evidence_kind is EvidenceKind.DERIVED and has_sources and has_license:
        return ArtifactStatus.PENDING_REVIEW

    return ArtifactStatus.DRAFT_INCOMPLETE


def build_research_artifact(
    *,
    artifact_id: str,
    artifact_type: str,
    finding_id: str,
    evidence_kind: EvidenceKind | str,
    subject: str,
    payload: Mapping[str, Any],
    provenance: Mapping[str, Any],
    reproducibility: Mapping[str, Any],
    license_info: Mapping[str, Any],
    confidence: float,
) -> ResearchArtifact:
    """Validate fields and build an immutable Research-owned artifact."""
    if not _SAFE_ID.fullmatch(artifact_id):
        raise ArtifactValidationError(f"Unsafe artifact_id: {artifact_id!r}")
    if not _SAFE_ID.fullmatch(finding_id):
        raise ArtifactValidationError(f"Unsafe finding_id: {finding_id!r}")
    if not artifact_type.strip():
        raise ArtifactValidationError("artifact_type is required")
    if not subject.strip():
        raise ArtifactValidationError("subject is required")
    if not 0.0 <= float(confidence) <= 1.0:
        raise ArtifactValidationError("confidence must be between 0 and 1")

    try:
        normalized_kind = (
            evidence_kind
            if isinstance(evidence_kind, EvidenceKind)
            else EvidenceKind(str(evidence_kind).upper())
        )
    except ValueError as exc:
        raise ArtifactValidationError(
            f"Unsupported evidence_kind: {evidence_kind!r}"
        ) from exc

    status = determine_status(
        evidence_kind=normalized_kind,
        provenance=provenance,
        reproducibility=reproducibility,
        license_info=license_info,
    )
    return ResearchArtifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type.strip(),
        finding_id=finding_id,
        evidence_kind=normalized_kind,
        status=status,
        subject=subject.strip(),
        payload=dict(payload),
        provenance=dict(provenance),
        reproducibility=dict(reproducibility),
        license_info=dict(license_info),
        confidence=float(confidence),
    )


def validate_artifact_dict(artifact: Mapping[str, Any]) -> None:
    """Validate a serialized artifact, including its immutable digest."""
    if str(artifact.get("schema_version")) != SCHEMA_VERSION:
        raise ArtifactValidationError("Unsupported artifact schema version")
    artifact_id = str(artifact.get("artifact_id") or "")
    if not _SAFE_ID.fullmatch(artifact_id):
        raise ArtifactValidationError("Invalid artifact_id")
    finding_id = str(artifact.get("finding_id") or "")
    if not _SAFE_ID.fullmatch(finding_id):
        raise ArtifactValidationError("Invalid finding_id")
    if artifact.get("producer") != "JAYA_RESEARCH":
        raise ArtifactValidationError("Unsupported artifact producer")

    supplied_digest = str(artifact.get("content_sha256") or "")
    unsigned = {
        key: value for key, value in artifact.items() if key != "content_sha256"
    }
    expected_digest = _content_digest(unsigned)
    if not supplied_digest or not hmac.compare_digest(supplied_digest, expected_digest):
        raise ArtifactValidationError("Artifact content digest mismatch")

    try:
        kind = EvidenceKind(str(artifact.get("evidence_kind") or "UNVERIFIED"))
        status = ArtifactStatus(str(artifact.get("status") or "DRAFT_INCOMPLETE"))
        confidence = float(artifact.get("confidence"))
    except (TypeError, ValueError) as exc:
        raise ArtifactValidationError(
            "Artifact evidence kind, status, or confidence is invalid"
        ) from exc
    if not 0.0 <= confidence <= 1.0:
        raise ArtifactValidationError("Artifact confidence must be between 0 and 1")
    if not isinstance(artifact.get("payload"), Mapping):
        raise ArtifactValidationError("Artifact payload must be an object")
    provenance = artifact.get("provenance")
    reproducibility = artifact.get("reproducibility")
    license_info = artifact.get("license")
    if not isinstance(provenance, Mapping):
        raise ArtifactValidationError("Artifact provenance must be an object")
    if not isinstance(reproducibility, Mapping):
        raise ArtifactValidationError("Artifact reproducibility must be an object")
    if not isinstance(license_info, Mapping):
        raise ArtifactValidationError("Artifact license must be an object")
    try:
        expected_status = determine_status(
            evidence_kind=kind,
            provenance=provenance,
            reproducibility=reproducibility,
            license_info=license_info,
        )
    except (TypeError, ValueError, OverflowError) as exc:
        raise ArtifactValidationError(
            "Artifact reproducibility metadata is invalid"
        ) from exc
    if status is not expected_status:
        raise ArtifactValidationError(
            f"Artifact status {status.value} does not match evidence "
            f"requirements ({expected_status.value})"
        )


class ResearchArtifactOutbox:
    """Atomically persists immutable candidate artifacts inside Research."""

    def __init__(self, outbox_dir: Path | str):
        self.outbox_dir = Path(outbox_dir).resolve()
        self.outbox_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, artifact: ResearchArtifact) -> Path:
        """Write an artifact atomically without mutating any consumer module."""
        serialized = artifact.to_dict()
        validate_artifact_dict(serialized)
        target = (self.outbox_dir / f"{artifact.artifact_id}.json").resolve()
        try:
            target.relative_to(self.outbox_dir)
        except ValueError as exc:
            raise ArtifactValidationError("Artifact path escapes outbox") from exc
        if target.exists():
            raise FileExistsError(f"Artifact already exists: {target.name}")

        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{artifact.artifact_id}.",
            suffix=".tmp",
            dir=self.outbox_dir,
            text=True,
        )
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(serialized, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, target)
        except Exception:
            Path(temp_name).unlink(missing_ok=True)
            raise
        return target
