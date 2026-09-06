"""Strict, read-only schema and signature verification for manifest v1."""

from __future__ import annotations

import hashlib
import hmac
import math
import re
import time
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ._evolution_manifest_security import (
    ABSENT_RESTORE_DIGEST,
    IDENTIFIER_PATTERN,
    SCHEMA_VERSION,
    SIGNATURE_ALGORITHM,
    SPDX_PATTERN,
    EvolutionContractError,
    EvolutionTrustStore,
    bounded_string,
    canonical_json,
    digest_bytes,
    identifier,
    require_exact_keys,
    require_mapping,
    signature_payload,
    tagged_digest,
    timestamp,
    validate_relative_install_path,
)


@dataclass(frozen=True)
class VerifiedEvolutionManifest:
    """Immutable subset authorized for the mutating installer."""

    manifest_id: str
    manifest_digest: str
    candidate_id: str
    payload_digest: str
    artifact_name: str
    artifact_digest: str
    artifact_size_bytes: int
    target_path: str
    registry_key: str
    canary_check_id: str
    expected_restore_digest: str
    approval_id: str
    approval_expires_at: float
    evidence_receipt_digests: tuple[str, ...]


class EvolutionManifestVerifier:
    """Read-only verifier that resolves a signed document into immutable fields."""

    _TOP_LEVEL_KEYS = {
        "schema_version",
        "manifest_id",
        "created_at",
        "candidate",
        "provenance",
        "license",
        "compatibility",
        "evidence_receipts",
        "human_approval",
        "install_plan",
        "rollback_plan",
        "signature",
    }

    def __init__(
        self,
        *,
        trust_store: EvolutionTrustStore,
        runtime: str,
        runtime_version: str,
        max_future_skew_seconds: float = 300.0,
    ) -> None:
        self.trust_store = trust_store
        self.runtime = identifier(runtime, field="runtime")
        self.runtime_version = bounded_string(
            runtime_version,
            field="runtime_version",
            maximum=128,
        )
        if not math.isfinite(max_future_skew_seconds) or max_future_skew_seconds < 0:
            raise EvolutionContractError(
                "TRUST_CONFIGURATION_INVALID",
                "Future timestamp skew must be finite and non-negative",
            )
        self.max_future_skew_seconds = float(max_future_skew_seconds)

    @staticmethod
    def _verify_signature(
        document: Mapping[str, Any],
        *,
        trusted_keys: Mapping[str, bytes],
        prefix: str,
    ) -> None:
        signature = document.get("signature")
        if not isinstance(signature, Mapping):
            raise EvolutionContractError(
                f"{prefix}_SIGNATURE_MISSING",
                f"{prefix.title()} signature is required",
            )
        require_exact_keys(
            signature,
            {"algorithm", "key_id", "value"},
            field=f"{prefix.lower()} signature",
        )
        if signature.get("algorithm") != SIGNATURE_ALGORITHM:
            raise EvolutionContractError(
                f"{prefix}_SIGNATURE_INVALID",
                f"{prefix.title()} signature algorithm is unsupported",
            )
        key_id = identifier(
            signature.get("key_id"),
            field=f"{prefix.lower()} signature key",
        )
        trusted_key = trusted_keys.get(key_id)
        if trusted_key is None:
            raise EvolutionContractError(
                f"{prefix}_KEY_UNTRUSTED",
                f"{prefix.title()} signing key is not trusted",
            )
        supplied = signature.get("value")
        if not isinstance(supplied, str) or not re.fullmatch(r"[0-9a-f]{64}", supplied):
            raise EvolutionContractError(
                f"{prefix}_SIGNATURE_MISSING",
                f"{prefix.title()} signature is required",
            )
        expected = hmac.new(
            trusted_key,
            signature_payload(document),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, supplied):
            raise EvolutionContractError(
                f"{prefix}_SIGNATURE_INVALID",
                f"{prefix.title()} signature verification failed",
            )

    def verify(
        self,
        manifest: Mapping[str, Any],
        *,
        verified_receipt_digests: Iterable[str],
        now: float | None = None,
    ) -> VerifiedEvolutionManifest:
        """Verify without filesystem writes or mutation of the input mapping."""
        document = require_mapping(manifest, field="manifest")
        if "signature" not in document:
            raise EvolutionContractError(
                "MANIFEST_SIGNATURE_MISSING",
                "Manifest signature is required",
            )
        if "human_approval" not in document:
            raise EvolutionContractError(
                "APPROVAL_MISSING",
                "Human approval is required",
            )
        require_exact_keys(document, self._TOP_LEVEL_KEYS, field="manifest")
        if document.get("schema_version") != SCHEMA_VERSION:
            raise EvolutionContractError(
                "SCHEMA_UNSUPPORTED",
                "Evolution manifest schema is unsupported",
            )
        self._verify_signature(
            document,
            trusted_keys=self.trust_store.manifest_keys,
            prefix="MANIFEST",
        )

        current_time = float(now if now is not None else time.time())
        if not math.isfinite(current_time) or current_time <= 0:
            raise EvolutionContractError("CLOCK_INVALID", "Verifier clock is invalid")
        created_at = timestamp(document.get("created_at"), field="created_at")
        if created_at > current_time + self.max_future_skew_seconds:
            raise EvolutionContractError(
                "MANIFEST_FROM_FUTURE",
                "Manifest creation time is outside the allowed clock skew",
            )
        manifest_id = identifier(document.get("manifest_id"), field="manifest_id")

        candidate = require_mapping(document.get("candidate"), field="candidate")
        require_exact_keys(
            candidate,
            {"candidate_id", "payload", "payload_digest", "artifact"},
            field="candidate",
        )
        candidate_id = identifier(
            candidate.get("candidate_id"),
            field="candidate_id",
        )
        payload = require_mapping(
            candidate.get("payload"),
            field="candidate.payload",
        )
        payload_digest = tagged_digest(
            candidate.get("payload_digest"),
            field="candidate.payload_digest",
        )
        computed_payload_digest = digest_bytes(canonical_json(payload))
        if not hmac.compare_digest(payload_digest, computed_payload_digest):
            raise EvolutionContractError(
                "PAYLOAD_DIGEST_MISMATCH",
                "Candidate payload digest does not match its content",
            )

        artifact = require_mapping(
            candidate.get("artifact"),
            field="candidate.artifact",
        )
        require_exact_keys(
            artifact,
            {"name", "digest", "size_bytes", "media_type"},
            field="candidate.artifact",
        )
        artifact_name = bounded_string(
            artifact.get("name"),
            field="candidate.artifact.name",
            maximum=180,
        )
        if Path(artifact_name).name != artifact_name or "/" in artifact_name:
            raise EvolutionContractError(
                "SCHEMA_INVALID",
                "Artifact name must not contain a path",
            )
        artifact_digest = tagged_digest(
            artifact.get("digest"),
            field="candidate.artifact.digest",
        )
        artifact_size = artifact.get("size_bytes")
        if (
            isinstance(artifact_size, bool)
            or not isinstance(artifact_size, int)
            or artifact_size < 1
        ):
            raise EvolutionContractError(
                "SCHEMA_INVALID",
                "Artifact size must be a positive integer",
            )
        bounded_string(
            artifact.get("media_type"),
            field="candidate.artifact.media_type",
            maximum=128,
        )

        self._verify_provenance(document.get("provenance"), current_time)
        self._verify_license(document.get("license"))
        compatibility = self._verify_compatibility(document.get("compatibility"))
        receipt_digests = self._verify_evidence(
            document.get("evidence_receipts"),
            verified_receipt_digests,
        )
        install = self._verify_install_plan(document.get("install_plan"))
        restore_digest = self._verify_rollback_plan(document.get("rollback_plan"))
        approval_id, approval_expiry = self._verify_approval(
            document.get("human_approval"),
            candidate_id=candidate_id,
            payload_digest=payload_digest,
            artifact_digest=artifact_digest,
            compatibility=compatibility,
            install=install,
            current_time=current_time,
        )

        return VerifiedEvolutionManifest(
            manifest_id=manifest_id,
            manifest_digest=digest_bytes(canonical_json(document)),
            candidate_id=candidate_id,
            payload_digest=payload_digest,
            artifact_name=artifact_name,
            artifact_digest=artifact_digest,
            artifact_size_bytes=artifact_size,
            target_path=install["target_path"],
            registry_key=install["registry_key"],
            canary_check_id=install["canary_check_id"],
            expected_restore_digest=restore_digest,
            approval_id=approval_id,
            approval_expires_at=approval_expiry,
            evidence_receipt_digests=receipt_digests,
        )

    def _verify_provenance(self, value: Any, current_time: float) -> None:
        provenance = require_mapping(value, field="provenance")
        require_exact_keys(
            provenance,
            {
                "source_uri",
                "source_revision",
                "builder_id",
                "built_at",
                "reproducible",
            },
            field="provenance",
        )
        bounded_string(provenance.get("source_uri"), field="provenance.source_uri")
        bounded_string(
            provenance.get("source_revision"),
            field="provenance.source_revision",
            maximum=128,
        )
        identifier(provenance.get("builder_id"), field="provenance.builder_id")
        built_at = timestamp(
            provenance.get("built_at"),
            field="provenance.built_at",
        )
        if built_at > current_time + self.max_future_skew_seconds:
            raise EvolutionContractError(
                "PROVENANCE_FROM_FUTURE",
                "Artifact provenance time is outside the allowed clock skew",
            )
        if provenance.get("reproducible") is not True:
            raise EvolutionContractError(
                "PROVENANCE_NOT_REPRODUCIBLE",
                "Artifact provenance must identify a reproducible build",
            )

    @staticmethod
    def _verify_license(value: Any) -> None:
        license_info = require_mapping(value, field="license")
        require_exact_keys(
            license_info,
            {"spdx_id", "redistribution_allowed", "source_notice"},
            field="license",
        )
        spdx_id = license_info.get("spdx_id")
        if not isinstance(spdx_id, str) or not SPDX_PATTERN.fullmatch(spdx_id):
            raise EvolutionContractError(
                "LICENSE_INVALID",
                "Artifact license must use a bounded SPDX identifier",
            )
        bounded_string(
            license_info.get("source_notice"),
            field="license.source_notice",
        )
        if license_info.get("redistribution_allowed") is not True:
            raise EvolutionContractError(
                "LICENSE_NOT_ALLOWED",
                "Artifact license does not permit installation",
            )

    def _verify_compatibility(self, value: Any) -> dict[str, Any]:
        compatibility = require_mapping(value, field="compatibility")
        require_exact_keys(
            compatibility,
            {"runtime", "target_versions", "platform_tags"},
            field="compatibility",
        )
        runtime = identifier(
            compatibility.get("runtime"),
            field="compatibility.runtime",
        )
        versions = compatibility.get("target_versions")
        platforms = compatibility.get("platform_tags")
        if (
            not isinstance(versions, list)
            or not versions
            or any(
                not isinstance(version, str) or not version or len(version) > 128
                for version in versions
            )
        ):
            raise EvolutionContractError(
                "COMPATIBILITY_INVALID",
                "Compatibility target versions are invalid",
            )
        if (
            not isinstance(platforms, list)
            or not platforms
            or any(
                not isinstance(platform, str)
                or not IDENTIFIER_PATTERN.fullmatch(platform)
                for platform in platforms
            )
        ):
            raise EvolutionContractError(
                "COMPATIBILITY_INVALID",
                "Compatibility platform tags are invalid",
            )
        if runtime != self.runtime or self.runtime_version not in versions:
            raise EvolutionContractError(
                "TARGET_INCOMPATIBLE",
                "Manifest is not compatible with this runtime target",
            )
        return {
            "runtime": runtime,
            "target_versions": list(versions),
        }

    @staticmethod
    def _verify_evidence(
        value: Any,
        verified_receipt_digests: Iterable[str],
    ) -> tuple[str, ...]:
        if not isinstance(value, list) or not value:
            raise EvolutionContractError(
                "EVIDENCE_MISSING",
                "Verified evidence receipts are required",
            )
        trusted = {
            tagged_digest(item, field="verified_receipt_digests")
            for item in verified_receipt_digests
        }
        seen_types: set[str] = set()
        required_digests: set[str] = set()
        for receipt in value:
            entry = require_mapping(receipt, field="evidence receipt")
            require_exact_keys(
                entry,
                {
                    "receipt_type",
                    "receipt_digest",
                    "verifier_key_id",
                    "verified",
                },
                field="evidence receipt",
            )
            receipt_type = identifier(
                entry.get("receipt_type"),
                field="evidence.receipt_type",
            )
            if receipt_type in seen_types:
                raise EvolutionContractError(
                    "EVIDENCE_INVALID",
                    "Evidence receipt types must be unique",
                )
            seen_types.add(receipt_type)
            required_digests.add(
                tagged_digest(
                    entry.get("receipt_digest"),
                    field="evidence.receipt_digest",
                )
            )
            identifier(
                entry.get("verifier_key_id"),
                field="evidence.verifier_key_id",
            )
            if entry.get("verified") is not True:
                raise EvolutionContractError(
                    "EVIDENCE_NOT_VERIFIED",
                    "Evidence receipts must be externally verified",
                )
        if not {"test", "benchmark"}.issubset(seen_types):
            raise EvolutionContractError(
                "EVIDENCE_MISSING",
                "Test and benchmark evidence receipts are required",
            )
        if not required_digests.issubset(trusted):
            raise EvolutionContractError(
                "EVIDENCE_NOT_VERIFIED",
                "Manifest evidence is absent from the trusted verification result",
            )
        return tuple(sorted(required_digests))

    @staticmethod
    def _verify_install_plan(value: Any) -> dict[str, str]:
        install = require_mapping(value, field="install_plan")
        require_exact_keys(
            install,
            {"mode", "target_path", "registry_key", "canary"},
            field="install_plan",
        )
        if install.get("mode") != "atomic-copy":
            raise EvolutionContractError(
                "INSTALL_PLAN_INVALID",
                "Only atomic-copy install plans are supported",
            )
        target_path = validate_relative_install_path(install.get("target_path"))
        registry_key = identifier(
            install.get("registry_key"),
            field="install_plan.registry_key",
        )
        canary = require_mapping(install.get("canary"), field="install_plan.canary")
        require_exact_keys(
            canary,
            {"required", "check_id"},
            field="install_plan.canary",
        )
        if canary.get("required") is not True:
            raise EvolutionContractError(
                "INSTALL_PLAN_INVALID",
                "A post-install canary is mandatory",
            )
        check_id = identifier(
            canary.get("check_id"),
            field="install_plan.canary.check_id",
        )
        return {
            "target_path": target_path,
            "registry_key": registry_key,
            "canary_check_id": check_id,
        }

    @staticmethod
    def _verify_rollback_plan(value: Any) -> str:
        rollback = require_mapping(value, field="rollback_plan")
        require_exact_keys(
            rollback,
            {"strategy", "expected_restore_digest"},
            field="rollback_plan",
        )
        if rollback.get("strategy") != "restore-previous-v1":
            raise EvolutionContractError(
                "ROLLBACK_PLAN_INVALID",
                "Rollback strategy is unsupported",
            )
        restore_digest = rollback.get("expected_restore_digest")
        if restore_digest != ABSENT_RESTORE_DIGEST:
            restore_digest = tagged_digest(
                restore_digest,
                field="rollback_plan.expected_restore_digest",
            )
        return restore_digest

    def _verify_approval(
        self,
        value: Any,
        *,
        candidate_id: str,
        payload_digest: str,
        artifact_digest: str,
        compatibility: Mapping[str, Any],
        install: Mapping[str, str],
        current_time: float,
    ) -> tuple[str, float]:
        approval = require_mapping(value, field="human_approval")
        require_exact_keys(
            approval,
            {
                "approval_id",
                "approver",
                "issued_at",
                "expires_at",
                "candidate_binding",
                "target_binding",
                "signature",
            },
            field="human_approval",
        )
        self._verify_signature(
            approval,
            trusted_keys=self.trust_store.approval_keys,
            prefix="APPROVAL",
        )
        approval_id = identifier(
            approval.get("approval_id"),
            field="human_approval.approval_id",
        )
        identifier(approval.get("approver"), field="human_approval.approver")
        issued_at = timestamp(
            approval.get("issued_at"),
            field="human_approval.issued_at",
        )
        expires_at = timestamp(
            approval.get("expires_at"),
            field="human_approval.expires_at",
        )
        if issued_at > current_time + self.max_future_skew_seconds:
            raise EvolutionContractError(
                "APPROVAL_FROM_FUTURE",
                "Human approval is outside the allowed clock skew",
            )
        if expires_at <= issued_at:
            raise EvolutionContractError(
                "APPROVAL_INVALID",
                "Human approval expiry must follow its issue time",
            )
        if current_time >= expires_at:
            raise EvolutionContractError(
                "APPROVAL_EXPIRED",
                "Human approval has expired",
            )

        candidate_binding = require_mapping(
            approval.get("candidate_binding"),
            field="human_approval.candidate_binding",
        )
        expected_candidate = {
            "candidate_id": candidate_id,
            "payload_digest": payload_digest,
            "artifact_digest": artifact_digest,
        }
        if dict(candidate_binding) != expected_candidate:
            raise EvolutionContractError(
                "APPROVAL_BINDING_INVALID",
                "Human approval is not bound to this candidate",
            )

        target_binding = require_mapping(
            approval.get("target_binding"),
            field="human_approval.target_binding",
        )
        expected_target = {
            "runtime": compatibility["runtime"],
            "target_versions": compatibility["target_versions"],
            "install_path": install["target_path"],
            "registry_key": install["registry_key"],
        }
        if dict(target_binding) != expected_target:
            raise EvolutionContractError(
                "APPROVAL_BINDING_INVALID",
                "Human approval is not bound to this install target",
            )
        return approval_id, expires_at
