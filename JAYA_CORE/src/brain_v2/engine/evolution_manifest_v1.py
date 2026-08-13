"""Public evolution manifest v1 contract, builder, signer, and verifier API."""

from __future__ import annotations

import copy
import time
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from ._evolution_manifest_security import (
    ABSENT_RESTORE_DIGEST,
    SCHEMA_VERSION,
    EvolutionContractError,
    EvolutionManifestSigner,
    EvolutionTrustStore,
    canonical_json,
    digest_bytes,
    digest_file,
    validate_relative_install_path,
)
from ._evolution_manifest_verifier import (
    EvolutionManifestVerifier,
    VerifiedEvolutionManifest,
)

__all__ = [
    "ABSENT_RESTORE_DIGEST",
    "EvolutionContractError",
    "EvolutionManifestSigner",
    "EvolutionManifestVerifier",
    "EvolutionTrustStore",
    "SCHEMA_VERSION",
    "VerifiedEvolutionManifest",
    "build_manifest_v1",
    "canonical_json",
    "digest_bytes",
    "digest_file",
    "validate_relative_install_path",
]


def build_manifest_v1(
    *,
    signer: EvolutionManifestSigner,
    manifest_id: str,
    candidate_id: str,
    payload: Mapping[str, Any],
    artifact_path: str | Path,
    artifact_name: str,
    artifact_media_type: str,
    provenance: Mapping[str, Any],
    license_info: Mapping[str, Any],
    compatibility: Mapping[str, Any],
    evidence_receipts: Iterable[Mapping[str, Any]],
    target_path: str,
    registry_key: str,
    canary_check_id: str,
    expected_restore_digest: str,
    approver: str,
    approval_id: str,
    approval_issued_at: float,
    approval_expires_at: float,
    created_at: float | None = None,
) -> dict[str, Any]:
    """Build a fully bound and signed v1 manifest from an artifact."""
    artifact = Path(artifact_path)
    artifact_digest = digest_file(artifact)
    payload_copy = copy.deepcopy(dict(payload))
    payload_digest = digest_bytes(canonical_json(payload_copy))
    install_path = validate_relative_install_path(target_path)
    target_binding = {
        "runtime": compatibility.get("runtime"),
        "target_versions": copy.deepcopy(compatibility.get("target_versions")),
        "install_path": install_path,
        "registry_key": registry_key,
    }
    candidate_binding = {
        "candidate_id": candidate_id,
        "payload_digest": payload_digest,
        "artifact_digest": artifact_digest,
    }
    approval = signer.sign_approval(
        {
            "approval_id": approval_id,
            "approver": approver,
            "issued_at": float(approval_issued_at),
            "expires_at": float(approval_expires_at),
            "candidate_binding": candidate_binding,
            "target_binding": target_binding,
        }
    )
    unsigned = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": manifest_id,
        "created_at": float(created_at if created_at is not None else time.time()),
        "candidate": {
            "candidate_id": candidate_id,
            "payload": payload_copy,
            "payload_digest": payload_digest,
            "artifact": {
                "name": artifact_name,
                "digest": artifact_digest,
                "size_bytes": artifact.stat().st_size,
                "media_type": artifact_media_type,
            },
        },
        "provenance": copy.deepcopy(dict(provenance)),
        "license": copy.deepcopy(dict(license_info)),
        "compatibility": copy.deepcopy(dict(compatibility)),
        "evidence_receipts": [
            copy.deepcopy(dict(receipt)) for receipt in evidence_receipts
        ],
        "human_approval": approval,
        "install_plan": {
            "mode": "atomic-copy",
            "target_path": install_path,
            "registry_key": registry_key,
            "canary": {
                "required": True,
                "check_id": canary_check_id,
            },
        },
        "rollback_plan": {
            "strategy": "restore-previous-v1",
            "expected_restore_digest": expected_restore_digest,
        },
    }
    return signer.sign_manifest(unsigned)
