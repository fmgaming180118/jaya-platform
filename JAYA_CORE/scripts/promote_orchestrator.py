#!/usr/bin/env python3
"""Verifier/installer-only evolution promotion entrypoint.

Evidence generation, candidate signing, manifest signing, and human approval are
separate trusted workflows. This module only verifies their outputs, evaluates
the gate, dispatches an explicit canary check, installs atomically, and records
content-addressed audit receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import os
import re
import sys
import time
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.brain_v2.engine._evolution_install_storage import (  # noqa: E402
    ConfinedInstallStorage,
    EvolutionInstallError,
    is_linklike,
)
from src.brain_v2.engine._evolution_manifest_security import (  # noqa: E402
    SIGNATURE_ALGORITHM,
    signature_payload,
)
from src.brain_v2.engine.canary import (  # noqa: E402
    CanaryError,
    CanaryRegistry,
    CompositeCanaryRunner,
    get_canary_registry,
)
from src.brain_v2.engine.evolution_evidence import (  # noqa: E402
    CandidateEvidence,
    EvidenceReceiptVerifier,
    EvidenceVerificationError,
)
from src.brain_v2.engine.evolution_gate import (  # noqa: E402
    EvolutionCandidate,
    EvolutionGate,
    GateThresholds,
)
from src.brain_v2.engine.evolution_installer import (  # noqa: E402
    EvolutionInstaller,
    InstallResult,
    RollbackResult,
)
from src.brain_v2.engine.evolution_manifest_v1 import (  # noqa: E402
    EvolutionContractError,
    EvolutionManifestVerifier,
    EvolutionTrustStore,
    canonical_json,
    digest_bytes,
)

REVOCATION_SCHEMA_VERSION = "jaya-evolution-revocations-v1"
AUDIT_SCHEMA_VERSION = "jaya-evolution-promotion-audit-v1"
_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SIGNATURE_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_JSON_BYTES = 4 * 1024 * 1024


class PromotionError(RuntimeError):
    """Typed, secret-free promotion rejection."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Revocations:
    revocation_id: str
    issued_at: float
    expires_at: float
    candidate_ids: frozenset[str]
    manifest_ids: frozenset[str]
    approval_ids: frozenset[str]

    def assert_current(self, now: float) -> None:
        if now < self.issued_at - 300.0 or now >= self.expires_at:
            raise PromotionError(
                "REVOCATION_LIST_EXPIRED", "revocation list is not current"
            )

    def blocks(self, *, candidate_id: str, manifest_id: str, approval_id: str) -> bool:
        return (
            candidate_id in self.candidate_ids
            or manifest_id in self.manifest_ids
            or approval_id in self.approval_ids
        )


@dataclass(frozen=True)
class PromotionResult:
    status: str
    candidate_id: str
    manifest_digest: str
    install: InstallResult
    audit_receipt_path: str | None
    audit_receipt_digest: str | None


def _identifier(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _IDENTIFIER_RE.fullmatch(value):
        raise PromotionError("SCHEMA_INVALID", f"{field} is invalid")
    return value


def _timestamp(value: Any, field: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) <= 0
    ):
        raise PromotionError("SCHEMA_INVALID", f"{field} is invalid")
    return float(value)


def _load_json(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value)
    if is_linklike(path) or not path.is_file() or path.stat().st_size > _MAX_JSON_BYTES:
        raise PromotionError(
            "INPUT_INVALID", "promotion input must be a bounded regular JSON file"
        )
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PromotionError(
            "INPUT_INVALID", "promotion input JSON cannot be decoded"
        ) from exc
    if not isinstance(value, dict):
        raise PromotionError("INPUT_INVALID", "promotion input JSON must be an object")
    return value


def verify_revocations(
    document: Mapping[str, Any],
    *,
    trusted_keys: Mapping[str, bytes],
    now: float,
) -> Revocations:
    expected = {
        "schema_version",
        "revocation_id",
        "issued_at",
        "expires_at",
        "revoked_candidate_ids",
        "revoked_manifest_ids",
        "revoked_approval_ids",
        "signature",
    }
    if (
        set(document) != expected
        or document.get("schema_version") != REVOCATION_SCHEMA_VERSION
    ):
        raise PromotionError(
            "REVOCATION_LIST_INVALID", "revocation list schema is invalid"
        )
    signature = document.get("signature")
    if not isinstance(signature, Mapping) or set(signature) != {
        "algorithm",
        "key_id",
        "value",
    }:
        raise PromotionError(
            "REVOCATION_SIGNATURE_INVALID", "revocation signature is required"
        )
    if signature.get("algorithm") != SIGNATURE_ALGORITHM:
        raise PromotionError(
            "REVOCATION_SIGNATURE_INVALID", "revocation algorithm is unsupported"
        )
    key_id = _identifier(signature.get("key_id"), "revocation key_id")
    key = trusted_keys.get(key_id)
    supplied = signature.get("value")
    if (
        key is None
        or not isinstance(supplied, str)
        or not _SIGNATURE_RE.fullmatch(supplied)
    ):
        raise PromotionError(
            "REVOCATION_KEY_UNTRUSTED", "revocation key is not trusted"
        )
    expected_signature = hmac.new(
        key, signature_payload(document), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, supplied):
        raise PromotionError(
            "REVOCATION_SIGNATURE_INVALID", "revocation signature is invalid"
        )

    def identifiers(field: str) -> frozenset[str]:
        raw = document.get(field)
        if not isinstance(raw, list):
            raise PromotionError("REVOCATION_LIST_INVALID", f"{field} must be a list")
        parsed = [_identifier(item, field) for item in raw]
        if len(parsed) != len(set(parsed)):
            raise PromotionError(
                "REVOCATION_LIST_INVALID", f"{field} contains duplicates"
            )
        return frozenset(parsed)

    issued_at = _timestamp(document.get("issued_at"), "issued_at")
    expires_at = _timestamp(document.get("expires_at"), "expires_at")
    if expires_at <= issued_at:
        raise PromotionError("REVOCATION_LIST_INVALID", "revocation expiry is invalid")
    result = Revocations(
        revocation_id=_identifier(document.get("revocation_id"), "revocation_id"),
        issued_at=issued_at,
        expires_at=expires_at,
        candidate_ids=identifiers("revoked_candidate_ids"),
        manifest_ids=identifiers("revoked_manifest_ids"),
        approval_ids=identifiers("revoked_approval_ids"),
    )
    result.assert_current(now)
    return result


def _candidate(document: Mapping[str, Any]) -> EvolutionCandidate:
    expected = {
        "candidate_id",
        "source_hash",
        "created_at",
        "candidate_payload",
        "expected_perf_gain_pct",
        "rollback_target",
        "key_id",
        "signature_alg",
        "signature",
        "metadata",
    }
    if set(document) != expected:
        raise PromotionError(
            "CANDIDATE_INVALID", "candidate contains missing or unsupported fields"
        )
    _identifier(document.get("candidate_id"), "candidate_id")
    _identifier(document.get("key_id"), "candidate key_id")
    if document.get("signature_alg") != "HMAC-SHA256":
        raise PromotionError(
            "CANDIDATE_INVALID", "candidate signature algorithm is unsupported"
        )
    signature = document.get("signature")
    if not isinstance(signature, str) or not _SIGNATURE_RE.fullmatch(signature):
        raise PromotionError("CANDIDATE_INVALID", "candidate signature is required")
    if not isinstance(document.get("metadata"), dict):
        raise PromotionError(
            "CANDIDATE_INVALID", "candidate metadata must be an object"
        )
    candidate = EvolutionCandidate(**dict(document))
    if not candidate.source_hash.strip() or not candidate.candidate_payload.strip():
        raise PromotionError(
            "CANDIDATE_INVALID", "candidate source and payload are required"
        )
    return candidate


class PromotionOrchestrator:
    """Read-only verifier composition plus the separately mutating installer."""

    def __init__(
        self,
        *,
        core_data_root: Path,
        core_registry_root: Path,
        manifest_trust_store: EvolutionTrustStore,
        candidate_verification_secret: bytes,
        evidence_verification_secret: bytes,
        trusted_evidence_signers: Mapping[str, Iterable[str]],
        revocation_document: Mapping[str, Any],
        canary_registry: CanaryRegistry,
        thresholds: GateThresholds | None = None,
        runtime: str = "JAYA_CORE",
        runtime_version: str = "1.0",
        clock: Any = time.time,
    ) -> None:
        if manifest_trust_store.test_mode:
            raise PromotionError(
                "TEST_TRUST_FORBIDDEN", "promotion cannot use a test trust store"
            )
        if (
            not isinstance(candidate_verification_secret, bytes)
            or len(candidate_verification_secret) < 32
        ):
            raise PromotionError(
                "TRUST_CONFIGURATION_INVALID", "candidate verification key is required"
            )
        if (
            not isinstance(evidence_verification_secret, bytes)
            or len(evidence_verification_secret) < 32
        ):
            raise PromotionError(
                "TRUST_CONFIGURATION_INVALID", "evidence verification key is required"
            )
        if hmac.compare_digest(
            candidate_verification_secret, evidence_verification_secret
        ):
            raise PromotionError(
                "TRUST_CONFIGURATION_INVALID",
                "candidate and evidence keys must be distinct",
            )
        if not trusted_evidence_signers:
            raise PromotionError(
                "TRUST_CONFIGURATION_INVALID", "trusted evidence signers are required"
            )
        self._clock = clock
        self._revocations = verify_revocations(
            revocation_document,
            trusted_keys=manifest_trust_store.manifest_keys,
            now=float(clock()),
        )
        self._evidence_verifier = EvidenceReceiptVerifier(
            evidence_verification_secret,
            trusted_signers=trusted_evidence_signers,
            clock=clock,
        )
        self._gate = EvolutionGate(
            thresholds=thresholds or GateThresholds(),
            signing_secret=candidate_verification_secret,
            evidence_signing_secret=evidence_verification_secret,
            trusted_evidence_runners=set(trusted_evidence_signers),
            require_signed=True,
            require_verified_evidence=True,
            environment="production",
        )
        self._manifest_verifier = EvolutionManifestVerifier(
            trust_store=manifest_trust_store,
            runtime=runtime,
            runtime_version=runtime_version,
        )
        self._canary_registry = canary_registry
        self._composite_canary = CompositeCanaryRunner(canary_registry)
        self.installer = EvolutionInstaller(
            verifier=self._manifest_verifier,
            registry_root=core_registry_root,
            data_root=core_data_root,
            canary_runner=self._composite_canary,
            clock=clock,
        )
        self._storage = ConfinedInstallStorage(
            registry_root=core_registry_root,
            data_root=core_data_root,
        )

    @staticmethod
    def _receipt_digests(evidence: CandidateEvidence) -> frozenset[str]:
        return frozenset(
            {
                str(evidence.metadata.get("test_report_digest") or ""),
                str(evidence.metadata.get("benchmark_report_digest") or ""),
            }
        )

    @staticmethod
    def _assert_manifest_bindings(
        manifest: Mapping[str, Any],
        *,
        candidate: EvolutionCandidate,
        evidence: CandidateEvidence,
        expected_commit: str,
    ) -> None:
        candidate_section = manifest.get("candidate")
        provenance = manifest.get("provenance")
        receipts = manifest.get("evidence_receipts")
        if (
            not isinstance(candidate_section, Mapping)
            or candidate_section.get("candidate_id") != candidate.candidate_id
        ):
            raise PromotionError(
                "CANDIDATE_BINDING_INVALID", "manifest candidate does not match"
            )
        try:
            payload = json.loads(candidate.candidate_payload)
        except json.JSONDecodeError as exc:
            raise PromotionError(
                "CANDIDATE_INVALID", "candidate payload must be canonical JSON"
            ) from exc
        if candidate_section.get("payload") != payload:
            raise PromotionError(
                "CANDIDATE_BINDING_INVALID", "manifest payload does not match candidate"
            )
        if (
            not isinstance(provenance, Mapping)
            or provenance.get("source_revision") != expected_commit
        ):
            raise PromotionError(
                "PROVENANCE_INVALID", "manifest revision does not match evidence commit"
            )
        if not isinstance(receipts, list):
            raise PromotionError(
                "EVIDENCE_BINDING_INVALID", "manifest evidence is missing"
            )
        expected_by_type = {
            "test": (
                evidence.metadata.get("test_report_digest"),
                evidence.metadata.get("test_key_id"),
            ),
            "benchmark": (
                evidence.metadata.get("benchmark_report_digest"),
                evidence.metadata.get("benchmark_key_id"),
            ),
        }
        observed: dict[str, tuple[Any, Any]] = {}
        for receipt in receipts:
            if isinstance(receipt, Mapping):
                observed[str(receipt.get("receipt_type"))] = (
                    receipt.get("receipt_digest"),
                    receipt.get("verifier_key_id"),
                )
        if observed != expected_by_type:
            raise PromotionError(
                "EVIDENCE_BINDING_INVALID",
                "manifest evidence bindings do not match verified reports",
            )

    def promote(
        self,
        *,
        candidate_document: Mapping[str, Any],
        manifest: Mapping[str, Any],
        test_report_path: Path,
        benchmark_report_path: Path,
        artifact_source: Path,
        expected_commit: str,
        dry_run: bool = False,
        now: float | None = None,
    ) -> PromotionResult:
        current_time = float(now if now is not None else self._clock())
        self._revocations.assert_current(current_time)
        candidate = _candidate(candidate_document)
        evidence = self._evidence_verifier.verify_reports(
            test_report_path,
            benchmark_report_path,
            candidate_id=candidate.candidate_id,
            source_hash=candidate.source_hash,
            expected_commit=expected_commit,
        )
        receipt_digests = self._receipt_digests(evidence)
        verified = self._manifest_verifier.verify(
            manifest,
            verified_receipt_digests=receipt_digests,
            now=current_time,
        )
        self._assert_manifest_bindings(
            manifest,
            candidate=candidate,
            evidence=evidence,
            expected_commit=expected_commit,
        )
        if self._revocations.blocks(
            candidate_id=verified.candidate_id,
            manifest_id=verified.manifest_id,
            approval_id=verified.approval_id,
        ):
            raise PromotionError(
                "ARTIFACT_REVOKED", "candidate, manifest, or approval is revoked"
            )
        runner = self._canary_registry.get(verified.canary_check_id)
        supported, reason = runner.validate_environment()
        if not supported:
            raise PromotionError("CANARY_UNAVAILABLE", reason)
        decision = self._gate.evaluate(candidate, evidence)
        if not decision.accepted:
            raise PromotionError(decision.code.value, decision.reason)
        installed = self.installer.install(
            manifest,
            artifact_source=artifact_source,
            verified_receipt_digests=receipt_digests,
            dry_run=dry_run,
            now=current_time,
        )
        if dry_run:
            return PromotionResult(
                status="planned",
                candidate_id=candidate.candidate_id,
                manifest_digest=verified.manifest_digest,
                install=installed,
                audit_receipt_path=None,
                audit_receipt_digest=None,
            )
        audit_path, audit_digest = self._write_audit(
            action="install",
            registry_key=verified.registry_key,
            candidate_id=verified.candidate_id,
            manifest_digest=verified.manifest_digest,
            approval_id=verified.approval_id,
            details={
                "canary_receipt_path": installed.canary_receipt_path,
                "canary_receipt_digest": installed.canary_receipt_digest,
                "evidence_receipt_digests": sorted(receipt_digests),
                "revocation_list_id": self._revocations.revocation_id,
            },
            now=current_time,
        )
        return PromotionResult(
            status="installed",
            candidate_id=candidate.candidate_id,
            manifest_digest=verified.manifest_digest,
            install=installed,
            audit_receipt_path=audit_path,
            audit_receipt_digest=audit_digest,
        )

    def rollback(
        self, registry_key: str, *, now: float | None = None
    ) -> RollbackResult:
        result = self.installer.rollback(registry_key, now=now)
        self._write_audit(
            action="rollback",
            registry_key=result.registry_key,
            candidate_id="lifecycle",
            manifest_digest="sha256:" + "0" * 64,
            approval_id="lifecycle",
            details={
                "target_path": result.target_path,
                "restored_digest": result.restored_digest,
                "idempotent": result.idempotent,
            },
            now=float(now if now is not None else self._clock()),
        )
        return result

    def revoke(self, registry_key: str, *, now: float | None = None) -> RollbackResult:
        registry = self._storage.load_registry()
        entry = registry["installations"].get(registry_key)
        if not isinstance(entry, Mapping):
            raise PromotionError(
                "INSTALLATION_NOT_FOUND", "installation does not exist"
            )
        if not self._revocations.blocks(
            candidate_id=str(entry.get("candidate_id") or ""),
            manifest_id=str(entry.get("manifest_id") or ""),
            approval_id=str(entry.get("approval_id") or ""),
        ):
            raise PromotionError(
                "REVOCATION_NOT_AUTHORIZED",
                "signed revocation list does not revoke this install",
            )
        result = self.installer.rollback(registry_key, now=now)
        self._write_audit(
            action="revoke",
            registry_key=registry_key,
            candidate_id=str(entry.get("candidate_id") or "lifecycle"),
            manifest_digest=str(entry.get("manifest_digest") or "sha256:" + "0" * 64),
            approval_id=str(entry.get("approval_id") or "lifecycle"),
            details={
                "revocation_list_id": self._revocations.revocation_id,
                "restored_digest": result.restored_digest,
                "idempotent": result.idempotent,
            },
            now=float(now if now is not None else self._clock()),
        )
        return result

    def _write_audit(
        self,
        *,
        action: str,
        registry_key: str,
        candidate_id: str,
        manifest_digest: str,
        approval_id: str,
        details: Mapping[str, Any],
        now: float,
    ) -> tuple[str, str]:
        audit_root = self._storage.registry_root / "promotion-audit"
        if os.path.lexists(audit_root):
            if is_linklike(audit_root) or not audit_root.is_dir():
                raise PromotionError(
                    "AUDIT_PATH_INVALID", "audit path is not a regular directory"
                )
        else:
            audit_root.mkdir()
        body = {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "event_id": f"promotion-{uuid.uuid4().hex}",
            "action": action,
            "registry_key": registry_key,
            "candidate_id": candidate_id,
            "manifest_digest": manifest_digest,
            "approval_id": approval_id,
            "created_at": now,
            "details": dict(details),
        }
        receipt_digest = digest_bytes(canonical_json(body))
        receipt = {**body, "receipt_digest": receipt_digest}
        relative = f"promotion-audit/{receipt_digest.removeprefix('sha256:')}.json"
        self._storage.atomic_json_write(self._storage.registry_root / relative, receipt)
        return relative, receipt_digest


def _required_secret(variable: str) -> bytes:
    raw = os.getenv(variable, "")
    if len(raw.encode("utf-8")) < 32:
        raise PromotionError(
            "TRUST_CONFIGURATION_INVALID",
            f"{variable} is required and must contain at least 32 bytes",
        )
    return raw.encode("utf-8")


def _trusted_signers_from_environment() -> dict[str, set[str]]:
    raw = os.getenv("JAYA_EVOLUTION_EVIDENCE_TRUSTED_SIGNERS_JSON", "")
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise PromotionError(
            "TRUST_CONFIGURATION_INVALID", "trusted evidence signer map is required"
        ) from exc
    if not isinstance(document, dict):
        raise PromotionError(
            "TRUST_CONFIGURATION_INVALID",
            "trusted evidence signer map must be an object",
        )
    return {
        str(runner): set(key_ids)
        for runner, key_ids in document.items()
        if isinstance(key_ids, list)
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify and install an externally approved evolution artifact"
    )
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--test-receipt", required=True)
    parser.add_argument("--benchmark-receipt", required=True)
    parser.add_argument("--artifact-source", required=True)
    parser.add_argument("--revocations", required=True)
    parser.add_argument("--expected-commit", required=True)
    parser.add_argument("--core-data-root", required=True)
    parser.add_argument("--core-registry-root", required=True)
    parser.add_argument("--runtime-version", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        trust_store = EvolutionTrustStore.from_environment(environment="production")
        orchestrator = PromotionOrchestrator(
            core_data_root=Path(args.core_data_root),
            core_registry_root=Path(args.core_registry_root),
            manifest_trust_store=trust_store,
            candidate_verification_secret=_required_secret(
                "JAYA_EVOLUTION_SIGNING_KEY"
            ),
            evidence_verification_secret=_required_secret(
                "JAYA_EVOLUTION_EVIDENCE_SIGNING_KEY"
            ),
            trusted_evidence_signers=_trusted_signers_from_environment(),
            revocation_document=_load_json(args.revocations),
            canary_registry=get_canary_registry(),
            runtime_version=args.runtime_version,
        )
        result = orchestrator.promote(
            candidate_document=_load_json(args.candidate),
            manifest=_load_json(args.manifest),
            test_report_path=Path(args.test_receipt),
            benchmark_report_path=Path(args.benchmark_receipt),
            artifact_source=Path(args.artifact_source),
            expected_commit=args.expected_commit,
            dry_run=args.dry_run,
        )
        print(
            json.dumps(
                {
                    "status": result.status,
                    "candidate_id": result.candidate_id,
                    "manifest_digest": result.manifest_digest,
                    "audit_receipt_path": result.audit_receipt_path,
                    "audit_receipt_digest": result.audit_receipt_digest,
                },
                sort_keys=True,
            )
        )
        return 0
    except (
        PromotionError,
        EvidenceVerificationError,
        EvolutionContractError,
        EvolutionInstallError,
        CanaryError,
        ValueError,
    ) as exc:
        code = getattr(exc, "code", "PROMOTION_REJECTED")
        print(f"promotion rejected [{code}]: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
