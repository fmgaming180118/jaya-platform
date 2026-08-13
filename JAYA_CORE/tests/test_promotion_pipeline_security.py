"""Abuse tests for external evidence promotion and explicit canaries."""

from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.generate_evidence import (  # noqa: E402
    EvidenceGenerationError,
    RunnerIdentity,
    load_benchmark_observation,
    load_signing_secret,
)
from scripts.promote_orchestrator import (  # noqa: E402
    REVOCATION_SCHEMA_VERSION,
    PromotionError,
    PromotionOrchestrator,
    verify_revocations,
)
from src.brain_v2.engine._evolution_manifest_security import (  # noqa: E402
    signature_payload,
)
from src.brain_v2.engine.canary import (  # noqa: E402
    CanaryError,
    CanaryRegistry,
    GenericCanary,
    QLoRAAdapterCanary,
)
from src.brain_v2.engine.evolution_evidence import (  # noqa: E402
    EvidenceReceiptVerifier,
    EvidenceVerificationError,
)
from src.brain_v2.engine.evolution_gate import (  # noqa: E402
    EvolutionCandidate,
    EvolutionGate,
)
from src.brain_v2.engine.evolution_manifest_v1 import (  # noqa: E402
    ABSENT_RESTORE_DIGEST,
    EvolutionManifestSigner,
    EvolutionTrustStore,
    build_manifest_v1,
    digest_file,
)

COMMIT = "a" * 40
DATASET = "sha256:" + "d" * 64
SOURCE = "sha256:" + "c" * 64
RUNNER = "ci-phase2"
KEY_ID = "ci-phase2-key"
EVIDENCE_KEY = b"e" * 32
REVOCATION_KEY = b"r" * 32


def _report(report_type: str, now: float) -> dict:
    result = {"passed": True}
    if report_type == "benchmark":
        result.update(
            {
                "observed_perf_gain_pct": 12.0,
                "ram_delta_pct": 2.0,
                "cpu_delta_pct": 3.0,
            }
        )
    return {
        "schema_version": "jaya-evolution-evidence-report-v1",
        "report_type": report_type,
        "candidate_id": "candidate-safe",
        "source_hash": SOURCE,
        "commit": COMMIT,
        "runner": RUNNER,
        "created_at": now,
        "dataset_digest": DATASET,
        "nonce": f"{report_type}-nonce",
        "result": result,
        "key_id": KEY_ID,
        "signature_alg": "HMAC-SHA256",
    }


def test_generator_has_no_default_secret_and_rejects_zero_dataset() -> None:
    with pytest.raises(EvidenceGenerationError, match="exactly one"):
        load_signing_secret({})
    with pytest.raises(EvidenceGenerationError, match="non-zero"):
        RunnerIdentity.validated(
            runner_id=RUNNER,
            key_id=KEY_ID,
            commit=COMMIT,
            dataset_digest="sha256:" + "0" * 64,
        )


def test_generator_does_not_fabricate_missing_benchmark_metrics(tmp_path: Path) -> None:
    identity = RunnerIdentity.validated(
        runner_id=RUNNER,
        key_id=KEY_ID,
        commit=COMMIT,
        dataset_digest=DATASET,
    )
    observation = {
        "schema_version": "jaya-evolution-benchmark-observation-v1",
        "candidate_id": "candidate-safe",
        "source_hash": SOURCE,
        "commit": COMMIT,
        "runner": RUNNER,
        "dataset_digest": DATASET,
        "created_at": time.time(),
        "exit_code": 0,
        "gate_failures": [],
        "metrics": {"observed_perf_gain_pct": 99.0},
        "command_digest": "sha256:" + "1" * 64,
        "stdout_digest": "sha256:" + "2" * 64,
        "stderr_digest": "sha256:" + "3" * 64,
    }
    path = tmp_path / "benchmark.json"
    path.write_text(json.dumps(observation), encoding="utf-8")
    with pytest.raises(EvidenceGenerationError, match="without defaults"):
        load_benchmark_observation(
            path,
            identity=identity,
            candidate_id="candidate-safe",
            source_hash=SOURCE,
        )


def test_untrusted_self_signed_and_zero_digest_reports_are_rejected(
    tmp_path: Path,
) -> None:
    now = time.time()
    signer = EvidenceReceiptVerifier(EVIDENCE_KEY)
    verifier = EvidenceReceiptVerifier(
        EVIDENCE_KEY,
        trusted_signers={RUNNER: {KEY_ID}},
    )
    test_report = _report("test", now)
    test_report["key_id"] = "self-signed-key"
    test_path = tmp_path / "test.json"
    benchmark_path = tmp_path / "benchmark.json"
    test_path.write_text(json.dumps(signer.sign_report(test_report)), encoding="utf-8")
    benchmark_path.write_text(
        json.dumps(signer.sign_report(_report("benchmark", now))),
        encoding="utf-8",
    )
    with pytest.raises(EvidenceVerificationError, match="untrusted evidence signer"):
        verifier.verify_reports(
            test_path,
            benchmark_path,
            candidate_id="candidate-safe",
            source_hash=SOURCE,
            expected_commit=COMMIT,
        )

    zero = _report("test", now)
    zero["dataset_digest"] = "sha256:" + "0" * 64
    test_path.write_text(json.dumps(signer.sign_report(zero)), encoding="utf-8")
    with pytest.raises(EvidenceVerificationError, match="all-zero"):
        signer.verify_reports(
            test_path,
            benchmark_path,
            candidate_id="candidate-safe",
            source_hash=SOURCE,
            expected_commit=COMMIT,
        )


def test_unknown_generic_bin_and_placeholder_canaries_fail(tmp_path: Path) -> None:
    with pytest.raises(CanaryError) as unknown:
        CanaryRegistry().get("unknown-functional-check")
    assert unknown.value.code == "UNKNOWN_CHECK_ID"
    assert GenericCanary().run(tmp_path, {}).passed is False

    unsafe = tmp_path / "adapter_model.bin"
    unsafe.write_bytes(b"unsafe model")
    unsafe_manifest = type("Verified", (), {"artifact_digest": digest_file(unsafe)})()
    assert (
        QLoRAAdapterCanary(lambda *_: {}).run(unsafe, unsafe_manifest).passed is False
    )

    safe = tmp_path / "adapter.safetensors"
    safe.write_bytes(b"safetensors fixture")
    safe_manifest = type("Verified", (), {"artifact_digest": digest_file(safe)})()
    result = QLoRAAdapterCanary(
        lambda *_: {"passed": True, "placeholder": True, "mode": "real-inference"}
    ).run(safe, safe_manifest)
    assert result.passed is False
    assert result.details["code"] == "PLACEHOLDER_PROBE"


def test_signed_revocation_is_required_current_and_tamper_evident() -> None:
    now = time.time()
    document = {
        "schema_version": REVOCATION_SCHEMA_VERSION,
        "revocation_id": "revocations-current",
        "issued_at": now - 10,
        "expires_at": now + 3600,
        "revoked_candidate_ids": ["candidate-safe"],
        "revoked_manifest_ids": [],
        "revoked_approval_ids": [],
        "signature": {"algorithm": "HMAC-SHA256", "key_id": "revocation-key"},
    }
    document["signature"]["value"] = hmac.new(
        REVOCATION_KEY,
        signature_payload(document),
        hashlib.sha256,
    ).hexdigest()
    verified = verify_revocations(
        document,
        trusted_keys={"revocation-key": REVOCATION_KEY},
        now=now,
    )
    assert verified.blocks(
        candidate_id="candidate-safe",
        manifest_id="manifest-safe",
        approval_id="approval-safe",
    )
    document["revoked_candidate_ids"] = []
    with pytest.raises(PromotionError) as tampered:
        verify_revocations(
            document,
            trusted_keys={"revocation-key": REVOCATION_KEY},
            now=now,
        )
    assert tampered.value.code == "REVOCATION_SIGNATURE_INVALID"


def test_orchestrator_source_has_no_research_default_or_signing_workflow() -> None:
    source = (ROOT / "scripts" / "promote_orchestrator.py").read_text(encoding="utf-8")
    assert "JAYA_RESEARCH" not in source
    assert "research_outbox" not in source
    assert ".for_test(" not in source
    assert "sign_candidate(" not in source
    assert "sign_report(" not in source
    assert "subprocess" not in source


def test_safe_promotion_drill_replay_and_rollback(tmp_path: Path) -> None:
    now = time.time()
    candidate_key = b"c" * 32
    manifest_key = b"m" * 32
    approval_key = b"a" * 32
    payload = {"capability": "offline-research", "version": 1}
    artifact = tmp_path / "candidate.safetensors"
    artifact.write_bytes(b"verified safetensors fixture")
    candidate = EvolutionCandidate(
        candidate_id="candidate-safe",
        source_hash=SOURCE,
        created_at=now,
        candidate_payload=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        expected_perf_gain_pct=12.0,
        rollback_target="stable-v1",
    )
    external_candidate_signer = EvolutionGate(
        environment="production",
        signing_secret=candidate_key,
        evidence_signing_secret=EVIDENCE_KEY,
        trusted_evidence_runners={RUNNER},
    )
    external_candidate_signer.sign_candidate(candidate, key_id="candidate-builder")

    report_signer = EvidenceReceiptVerifier(EVIDENCE_KEY)
    test_report = report_signer.sign_report(_report("test", now))
    benchmark_report = report_signer.sign_report(_report("benchmark", now))
    test_path = tmp_path / "test-report.json"
    benchmark_path = tmp_path / "benchmark-report.json"
    test_path.write_text(json.dumps(test_report), encoding="utf-8")
    benchmark_path.write_text(json.dumps(benchmark_report), encoding="utf-8")

    manifest_signer = EvolutionManifestSigner(
        manifest_key_id="manifest-key",
        manifest_key=manifest_key,
        approval_key_id="approval-key",
        approval_key=approval_key,
    )
    manifest = build_manifest_v1(
        signer=manifest_signer,
        manifest_id="manifest-safe",
        candidate_id="candidate-safe",
        payload=payload,
        artifact_path=artifact,
        artifact_name=artifact.name,
        artifact_media_type="application/vnd.safetensors",
        provenance={
            "source_uri": "https://example.invalid/jaya",
            "source_revision": COMMIT,
            "builder_id": "trusted-builder",
            "built_at": now - 20,
            "reproducible": True,
        },
        license_info={
            "spdx_id": "Apache-2.0",
            "redistribution_allowed": True,
            "source_notice": "controlled fixture",
        },
        compatibility={
            "runtime": "JAYA_CORE",
            "target_versions": ["1.0"],
            "platform_tags": ["windows-x86_64"],
        },
        evidence_receipts=[
            {
                "receipt_type": "test",
                "receipt_digest": test_report["report_digest"],
                "verifier_key_id": KEY_ID,
                "verified": True,
            },
            {
                "receipt_type": "benchmark",
                "receipt_digest": benchmark_report["report_digest"],
                "verifier_key_id": KEY_ID,
                "verified": True,
            },
        ],
        target_path="models/candidate.safetensors",
        registry_key="candidate-safe",
        canary_check_id="qlora-adapter-inference-v1",
        expected_restore_digest=ABSENT_RESTORE_DIGEST,
        approver="human-reviewer",
        approval_id="approval-safe",
        approval_issued_at=now - 10,
        approval_expires_at=now + 3600,
        created_at=now - 5,
    )
    revocations = {
        "schema_version": REVOCATION_SCHEMA_VERSION,
        "revocation_id": "revocations-current",
        "issued_at": now - 10,
        "expires_at": now + 3600,
        "revoked_candidate_ids": [],
        "revoked_manifest_ids": [],
        "revoked_approval_ids": [],
        "signature": {"algorithm": "HMAC-SHA256", "key_id": "manifest-key"},
    }
    revocations["signature"]["value"] = hmac.new(
        manifest_key,
        signature_payload(revocations),
        hashlib.sha256,
    ).hexdigest()
    trust = EvolutionTrustStore(
        manifest_keys={"manifest-key": manifest_key},
        approval_keys={"approval-key": approval_key},
        environment="development",
    )
    registry = CanaryRegistry()
    registry.register(
        QLoRAAdapterCanary(
            lambda *_: {
                "passed": True,
                "mode": "real-inference",
                "probe_id": "trusted-probe",
                "model_loaded": True,
                "adapter_applied": True,
                "tokens_generated": 3,
                "inference_time_ms": 1.0,
                "output_digest": "sha256:" + "f" * 64,
            }
        )
    )
    data_root = tmp_path / "data"
    registry_root = tmp_path / "registry"
    data_root.mkdir()
    registry_root.mkdir()
    orchestrator = PromotionOrchestrator(
        core_data_root=data_root,
        core_registry_root=registry_root,
        manifest_trust_store=trust,
        candidate_verification_secret=candidate_key,
        evidence_verification_secret=EVIDENCE_KEY,
        trusted_evidence_signers={RUNNER: {KEY_ID}},
        revocation_document=revocations,
        canary_registry=registry,
        clock=lambda: now,
    )
    installed = orchestrator.promote(
        candidate_document=candidate.to_dict(),
        manifest=manifest,
        test_report_path=test_path,
        benchmark_report_path=benchmark_path,
        artifact_source=artifact,
        expected_commit=COMMIT,
    )
    assert installed.status == "installed"
    assert installed.audit_receipt_digest
    assert (data_root / "models" / artifact.name).is_file()
    with pytest.raises(PromotionError) as replay:
        orchestrator.promote(
            candidate_document=candidate.to_dict(),
            manifest=manifest,
            test_report_path=test_path,
            benchmark_report_path=benchmark_path,
            artifact_source=artifact,
            expected_commit=COMMIT,
        )
    assert replay.value.code == "REJECT_SECURITY"
    first = orchestrator.rollback("candidate-safe", now=now + 1)
    second = orchestrator.rollback("candidate-safe", now=now + 2)
    assert first.idempotent is False
    assert second.idempotent is True
    assert not (data_root / "models" / artifact.name).exists()
