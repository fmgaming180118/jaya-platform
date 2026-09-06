"""Independent verifier for the public JAYA Research artifact contract.

Core deliberately owns this verifier. Importing the Research implementation
would couple both runtimes and let Research code execute inside Core.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

SCHEMA_VERSION = "1.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,127}$")
_SHA256 = re.compile(r"^[a-fA-F0-9]{64}$")
_REVIEWABLE_EVIDENCE = frozenset({"EMPIRICAL", "DERIVED"})


class ResearchArtifactVerificationError(ValueError):
    """Raised when an inbox artifact cannot cross the Core trust boundary."""


def canonical_json(value: Mapping[str, Any]) -> str:
    """Return the canonical JSON representation used by the public contract."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ResearchArtifactVerificationError(
            "artifact contains non-canonical JSON values"
        ) from exc


@dataclass(frozen=True, slots=True)
class VerifiedResearchArtifact:
    """Immutable subset consumed by Core after contract verification."""

    artifact_id: str
    artifact_type: str
    finding_id: str
    evidence_kind: str
    subject: str
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    reproducibility: Mapping[str, Any]
    license_info: Mapping[str, Any]
    confidence: float
    content_sha256: str
    created_at: str


def _mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchArtifactVerificationError(f"{field} must be an object")
    return value


def _validate_timestamp(raw: Any) -> str:
    value = str(raw or "")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ResearchArtifactVerificationError("created_at must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ResearchArtifactVerificationError("created_at must include a timezone")
    return value


def _validate_source_hashes(provenance: Mapping[str, Any]) -> None:
    hashes = provenance.get("source_hashes")
    if (
        not isinstance(hashes, list)
        or not hashes
        or any(
            not isinstance(item, str) or not _SHA256.fullmatch(item) for item in hashes
        )
    ):
        raise ResearchArtifactVerificationError(
            "provenance.source_hashes must contain SHA-256 digests"
        )


def verify_research_artifact(
    artifact: Mapping[str, Any],
    *,
    require_reviewable: bool = True,
) -> VerifiedResearchArtifact:
    """Verify schema, digest, evidence, provenance, and review eligibility.

    This function never invents missing confidence or evidence. The caller may
    disable ``require_reviewable`` only for diagnostics; ingestion keeps it on.
    """
    if not isinstance(artifact, Mapping):
        raise ResearchArtifactVerificationError("artifact must be an object")
    if str(artifact.get("schema_version") or "") != SCHEMA_VERSION:
        raise ResearchArtifactVerificationError("unsupported artifact schema version")
    if artifact.get("producer") != "JAYA_RESEARCH":
        raise ResearchArtifactVerificationError("unsupported artifact producer")

    artifact_id = str(artifact.get("artifact_id") or "")
    finding_id = str(artifact.get("finding_id") or "")
    if not _SAFE_ID.fullmatch(artifact_id):
        raise ResearchArtifactVerificationError("invalid artifact_id")
    if not _SAFE_ID.fullmatch(finding_id):
        raise ResearchArtifactVerificationError("invalid finding_id")

    artifact_type = str(artifact.get("artifact_type") or "").strip()
    subject = str(artifact.get("subject") or "").strip()
    if not artifact_type:
        raise ResearchArtifactVerificationError("artifact_type is required")
    if not subject:
        raise ResearchArtifactVerificationError("subject is required")

    supplied_digest = str(artifact.get("content_sha256") or "")
    if not _SHA256.fullmatch(supplied_digest):
        raise ResearchArtifactVerificationError("content_sha256 must be SHA-256")
    unsigned = {
        key: value for key, value in artifact.items() if key != "content_sha256"
    }
    expected_digest = hashlib.sha256(
        canonical_json(unsigned).encode("utf-8")
    ).hexdigest()
    if not hmac.compare_digest(supplied_digest.lower(), expected_digest):
        raise ResearchArtifactVerificationError("artifact content digest mismatch")

    evidence_kind = str(artifact.get("evidence_kind") or "")
    status = str(artifact.get("status") or "")
    if require_reviewable and (
        status != "PENDING_REVIEW" or evidence_kind not in _REVIEWABLE_EVIDENCE
    ):
        raise ResearchArtifactVerificationError(
            "only reviewable EMPIRICAL or DERIVED artifacts may enter Core"
        )

    payload = _mapping(artifact.get("payload"), "payload")
    provenance = _mapping(artifact.get("provenance"), "provenance")
    reproducibility = _mapping(artifact.get("reproducibility"), "reproducibility")
    license_info = _mapping(artifact.get("license"), "license")
    _validate_source_hashes(provenance)
    if not str(license_info.get("id") or "").strip():
        raise ResearchArtifactVerificationError("license.id is required")

    if evidence_kind == "EMPIRICAL":
        dataset_digest = str(provenance.get("dataset_sha256") or "")
        if not _SHA256.fullmatch(dataset_digest):
            raise ResearchArtifactVerificationError(
                "empirical artifact requires provenance.dataset_sha256"
            )
        try:
            run_count = int(reproducibility.get("run_count"))
        except (TypeError, ValueError, OverflowError) as exc:
            raise ResearchArtifactVerificationError(
                "reproducibility.run_count is invalid"
            ) from exc
        if reproducibility.get("reproduced") is not True or run_count < 2:
            raise ResearchArtifactVerificationError(
                "empirical artifact has not been independently reproduced"
            )

    try:
        confidence = float(artifact["confidence"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ResearchArtifactVerificationError(
            "artifact confidence is required and must be numeric"
        ) from exc
    if not 0.0 <= confidence <= 1.0:
        raise ResearchArtifactVerificationError(
            "artifact confidence must be between 0 and 1"
        )

    return VerifiedResearchArtifact(
        artifact_id=artifact_id,
        artifact_type=artifact_type,
        finding_id=finding_id,
        evidence_kind=evidence_kind,
        subject=subject,
        payload=dict(payload),
        provenance=dict(provenance),
        reproducibility=dict(reproducibility),
        license_info=dict(license_info),
        confidence=confidence,
        content_sha256=supplied_digest.lower(),
        created_at=_validate_timestamp(artifact.get("created_at")),
    )
