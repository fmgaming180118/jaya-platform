"""Deterministic security and lifecycle tests for evolution manifest v1."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jaya_core.brain_v2.engine.evolution_installer import (  # noqa: E402
    EvolutionInstaller,
    EvolutionInstallError,
)
from jaya_core.brain_v2.engine.evolution_manifest_v1 import (  # noqa: E402
    ABSENT_RESTORE_DIGEST,
    EvolutionContractError,
    EvolutionManifestSigner,
    EvolutionManifestVerifier,
    EvolutionTrustStore,
    build_manifest_v1,
    canonical_json,
    digest_bytes,
    digest_file,
)

NOW = 2_000_000_000.0
MANIFEST_KEY_ID = "manifest-test-key"
APPROVAL_KEY_ID = "approval-test-key"
MANIFEST_KEY = b"m" * 32
APPROVAL_KEY = b"a" * 32
TEST_RECEIPT_DIGEST = digest_bytes(b"verified test receipt")
BENCHMARK_RECEIPT_DIGEST = digest_bytes(b"verified benchmark receipt")
VERIFIED_RECEIPTS = frozenset(
    {
        TEST_RECEIPT_DIGEST,
        BENCHMARK_RECEIPT_DIGEST,
    }
)


@pytest.fixture
def signer() -> EvolutionManifestSigner:
    return EvolutionManifestSigner(
        manifest_key_id=MANIFEST_KEY_ID,
        manifest_key=MANIFEST_KEY,
        approval_key_id=APPROVAL_KEY_ID,
        approval_key=APPROVAL_KEY,
    )


@pytest.fixture
def verifier() -> EvolutionManifestVerifier:
    trust = EvolutionTrustStore.for_test(
        manifest_key_id=MANIFEST_KEY_ID,
        manifest_key=MANIFEST_KEY,
        approval_key_id=APPROVAL_KEY_ID,
        approval_key=APPROVAL_KEY,
    )
    return EvolutionManifestVerifier(
        trust_store=trust,
        runtime="JAYA_CORE",
        runtime_version="1.0",
    )


def _build_manifest(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    *,
    artifact_path: Path | None = None,
    target_path: str = "packages/candidate.bin",
    expected_restore_digest: str = ABSENT_RESTORE_DIGEST,
    approval_expires_at: float = NOW + 3600,
) -> tuple[dict, Path]:
    source = artifact_path or (tmp_path / "staging" / "candidate.bin")
    source.parent.mkdir(parents=True, exist_ok=True)
    if not source.exists():
        source.write_bytes(b"trusted evolution artifact v1")
    manifest = build_manifest_v1(
        signer=signer,
        manifest_id="manifest-candidate-v1",
        candidate_id="candidate-v1",
        payload={
            "capability": "offline-research",
            "version": 1,
        },
        artifact_path=source,
        artifact_name="candidate.bin",
        artifact_media_type="application/octet-stream",
        provenance={
            "source_uri": "https://example.invalid/jaya/core",
            "source_revision": "abcdef1234567890",
            "builder_id": "trusted-builder",
            "built_at": NOW - 120,
            "reproducible": True,
        },
        license_info={
            "spdx_id": "Apache-2.0",
            "redistribution_allowed": True,
            "source_notice": "JAYA controlled build fixture",
        },
        compatibility={
            "runtime": "JAYA_CORE",
            "target_versions": ["1.0"],
            "platform_tags": ["windows-x86_64", "linux-x86_64"],
        },
        evidence_receipts=[
            {
                "receipt_type": "test",
                "receipt_digest": TEST_RECEIPT_DIGEST,
                "verifier_key_id": "ci-test-verifier",
                "verified": True,
            },
            {
                "receipt_type": "benchmark",
                "receipt_digest": BENCHMARK_RECEIPT_DIGEST,
                "verifier_key_id": "ci-benchmark-verifier",
                "verified": True,
            },
        ],
        target_path=target_path,
        registry_key="candidate-v1",
        canary_check_id="candidate-load-check",
        expected_restore_digest=expected_restore_digest,
        approver="human-reviewer",
        approval_id="approval-candidate-v1",
        approval_issued_at=NOW - 60,
        approval_expires_at=approval_expires_at,
        created_at=NOW - 30,
    )
    return manifest, source


def _installer(
    tmp_path: Path,
    verifier: EvolutionManifestVerifier,
) -> tuple[EvolutionInstaller, Path, Path]:
    registry_root = tmp_path / "registry"
    data_root = tmp_path / "data"
    registry_root.mkdir(exist_ok=True)
    data_root.mkdir(exist_ok=True)

    def canary(path: Path, verified) -> dict:
        return {
            "passed": path.is_file() and digest_file(path) == verified.artifact_digest,
            "loaded_candidate": verified.candidate_id,
        }

    return (
        EvolutionInstaller(
            verifier=verifier,
            registry_root=registry_root,
            data_root=data_root,
            canary_runner=canary,
            clock=lambda: NOW,
        ),
        registry_root,
        data_root,
    )


def _resign_approval_and_manifest(
    manifest: dict,
    signer: EvolutionManifestSigner,
) -> dict:
    updated = copy.deepcopy(manifest)
    updated["human_approval"] = signer.sign_approval(updated["human_approval"])
    return signer.sign_manifest(updated)


def _create_directory_link(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
        return
    except (NotImplementedError, OSError) as exc:
        symlink_error = exc
    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return
    pytest.skip(f"Directory links are unavailable: {symlink_error}")


def _remove_directory_link(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
        return
    is_junction = getattr(link, "is_junction", None)
    if is_junction and is_junction():
        link.rmdir()


def test_production_trust_without_signing_or_approval_keys_fails_closed() -> None:
    with pytest.raises(EvolutionContractError) as exc_info:
        EvolutionTrustStore(
            manifest_keys={},
            approval_keys={},
            environment="production",
        )

    assert exc_info.value.code == "TRUST_KEYS_REQUIRED"


def test_missing_and_tampered_manifest_signatures_are_rejected(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, _ = _build_manifest(tmp_path, signer)
    missing = copy.deepcopy(manifest)
    missing.pop("signature")
    tampered = copy.deepcopy(manifest)
    tampered["candidate"]["payload"]["version"] = 2

    with pytest.raises(EvolutionContractError) as missing_error:
        verifier.verify(
            missing,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )
    with pytest.raises(EvolutionContractError) as tampered_error:
        verifier.verify(
            tampered,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )

    assert missing_error.value.code == "MANIFEST_SIGNATURE_MISSING"
    assert tampered_error.value.code == "MANIFEST_SIGNATURE_INVALID"


def test_verifier_is_read_only_and_returns_immutable_install_fields(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, _ = _build_manifest(tmp_path, signer)
    original = copy.deepcopy(manifest)

    verified = verifier.verify(
        manifest,
        verified_receipt_digests=VERIFIED_RECEIPTS,
        now=NOW,
    )

    assert manifest == original
    assert verified.target_path == "packages/candidate.bin"
    with pytest.raises((AttributeError, TypeError)):
        verified.target_path = "../mutated.bin"


def test_missing_tampered_and_expired_human_approval_are_rejected(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, _ = _build_manifest(tmp_path, signer)
    missing = copy.deepcopy(manifest)
    missing.pop("human_approval")
    missing = signer.sign_manifest(missing)

    tampered = copy.deepcopy(manifest)
    tampered["human_approval"]["approver"] = "different-reviewer"
    tampered = signer.sign_manifest(tampered)

    expired, _ = _build_manifest(
        tmp_path,
        signer,
        approval_expires_at=NOW - 1,
    )

    with pytest.raises(EvolutionContractError) as missing_error:
        verifier.verify(
            missing,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )
    with pytest.raises(EvolutionContractError) as tampered_error:
        verifier.verify(
            tampered,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )
    with pytest.raises(EvolutionContractError) as expired_error:
        verifier.verify(
            expired,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )

    assert missing_error.value.code == "APPROVAL_MISSING"
    assert tampered_error.value.code == "APPROVAL_SIGNATURE_INVALID"
    assert expired_error.value.code == "APPROVAL_EXPIRED"


@pytest.mark.parametrize(
    "unsafe_target",
    [
        "../outside.bin",
        "/absolute/outside.bin",
        r"C:\absolute\outside.bin",
        "packages/%2e%2e/outside.bin",
    ],
)
def test_signed_absolute_traversal_and_encoded_targets_are_rejected(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
    unsafe_target: str,
) -> None:
    manifest, source = _build_manifest(tmp_path, signer)
    malicious = copy.deepcopy(manifest)
    malicious["install_plan"]["target_path"] = unsafe_target
    malicious["human_approval"]["target_binding"]["install_path"] = unsafe_target
    malicious = _resign_approval_and_manifest(malicious, signer)
    installer, _, _ = _installer(tmp_path, verifier)

    with pytest.raises(EvolutionContractError) as exc_info:
        installer.install(
            malicious,
            artifact_source=source,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )

    assert exc_info.value.code == "UNSAFE_INSTALL_PATH"
    assert not (tmp_path / "outside.bin").exists()


def test_symlink_target_is_rejected_without_touching_outside_or_source(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, source = _build_manifest(tmp_path, signer)
    source_before = source.read_bytes()
    installer, _, data_root = _installer(tmp_path, verifier)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = data_root / "packages"
    _create_directory_link(link, outside)
    try:
        with pytest.raises(EvolutionInstallError) as exc_info:
            installer.install(
                manifest,
                artifact_source=source,
                verified_receipt_digests=VERIFIED_RECEIPTS,
                now=NOW,
            )

        assert exc_info.value.code == "SYMLINK_REJECTED"
        assert not (outside / "candidate.bin").exists()
        assert source.read_bytes() == source_before
    finally:
        _remove_directory_link(link)


def test_artifact_digest_mismatch_is_rejected_before_any_write(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, source = _build_manifest(tmp_path, signer)
    source.write_bytes(b"tampered after manifest signing")
    installer, registry_root, data_root = _installer(tmp_path, verifier)

    with pytest.raises(EvolutionInstallError) as exc_info:
        installer.install(
            manifest,
            artifact_source=source,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )

    assert exc_info.value.code == "ARTIFACT_DIGEST_MISMATCH"
    assert list(registry_root.iterdir()) == []
    assert list(data_root.iterdir()) == []


def test_unverified_evidence_digest_is_rejected(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, _ = _build_manifest(tmp_path, signer)

    with pytest.raises(EvolutionContractError) as exc_info:
        verifier.verify(
            manifest,
            verified_receipt_digests={TEST_RECEIPT_DIGEST},
            now=NOW,
        )

    assert exc_info.value.code == "EVIDENCE_NOT_VERIFIED"


def test_dry_run_is_read_only_and_source_overwrite_is_rejected(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, source = _build_manifest(tmp_path, signer)
    source_before = source.read_bytes()
    installer, registry_root, data_root = _installer(tmp_path, verifier)

    result = installer.install(
        manifest,
        artifact_source=source,
        verified_receipt_digests=VERIFIED_RECEIPTS,
        dry_run=True,
        now=NOW,
    )

    assert result.status == "planned"
    assert source.read_bytes() == source_before
    assert list(registry_root.iterdir()) == []
    assert list(data_root.iterdir()) == []

    in_place_source = data_root / "packages" / "candidate.bin"
    in_place_source.parent.mkdir()
    in_place_source.write_bytes(b"in-place source")
    in_place_manifest, _ = _build_manifest(
        tmp_path,
        signer,
        artifact_path=in_place_source,
        expected_restore_digest=digest_file(in_place_source),
    )
    with pytest.raises(EvolutionInstallError) as exc_info:
        installer.install(
            in_place_manifest,
            artifact_source=in_place_source,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )

    assert exc_info.value.code == "SOURCE_OVERWRITE_REJECTED"
    assert in_place_source.read_bytes() == b"in-place source"


def test_successful_install_writes_verified_canary_and_rejects_replay(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    manifest, source = _build_manifest(tmp_path, signer)
    source_before = source.read_bytes()
    installer, registry_root, data_root = _installer(tmp_path, verifier)

    installed = installer.install(
        manifest,
        artifact_source=source,
        verified_receipt_digests=VERIFIED_RECEIPTS,
        now=NOW,
    )

    target = data_root / "packages" / "candidate.bin"
    assert installed.status == "installed"
    assert target.read_bytes() == source_before
    assert source.read_bytes() == source_before
    receipt_path = data_root / installed.canary_receipt_path
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    receipt_digest = receipt.pop("receipt_digest")
    assert receipt["passed"] is True
    assert receipt["observed_artifact_digest"] == digest_file(target)
    assert receipt_digest == digest_bytes(canonical_json(receipt))
    registry = json.loads(
        (registry_root / "evolution-installs-v1.json").read_text(encoding="utf-8")
    )
    assert installed.manifest_digest in registry["consumed_manifests"]

    with pytest.raises(EvolutionInstallError) as replay_error:
        installer.install(
            manifest,
            artifact_source=source,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )
    assert replay_error.value.code == "MANIFEST_REPLAY"


def test_failed_canary_atomically_restores_previous_target(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    installer, registry_root, data_root = _installer(tmp_path, verifier)
    target = data_root / "packages" / "candidate.bin"
    target.parent.mkdir()
    target.write_bytes(b"stable artifact before failed canary")
    restore_digest = digest_file(target)
    manifest, source = _build_manifest(
        tmp_path,
        signer,
        expected_restore_digest=restore_digest,
    )
    source_before = source.read_bytes()
    installer.canary_runner = lambda _path, _verified: {"passed": False}

    with pytest.raises(EvolutionInstallError) as exc_info:
        installer.install(
            manifest,
            artifact_source=source,
            verified_receipt_digests=VERIFIED_RECEIPTS,
            now=NOW,
        )

    assert exc_info.value.code == "CANARY_FAILED"
    assert digest_file(target) == restore_digest
    assert source.read_bytes() == source_before
    assert list(registry_root.iterdir()) == []


def test_rollback_restores_digest_and_second_call_is_idempotent(
    tmp_path: Path,
    signer: EvolutionManifestSigner,
    verifier: EvolutionManifestVerifier,
) -> None:
    installer, _, data_root = _installer(tmp_path, verifier)
    target = data_root / "packages" / "candidate.bin"
    target.parent.mkdir()
    target.write_bytes(b"stable artifact before evolution")
    restore_digest = digest_file(target)
    manifest, source = _build_manifest(
        tmp_path,
        signer,
        expected_restore_digest=restore_digest,
    )

    installer.install(
        manifest,
        artifact_source=source,
        verified_receipt_digests=VERIFIED_RECEIPTS,
        now=NOW,
    )
    assert digest_file(target) != restore_digest

    first = installer.rollback("candidate-v1", now=NOW + 1)
    second = installer.rollback("candidate-v1", now=NOW + 2)

    assert first.idempotent is False
    assert second.idempotent is True
    assert first.restored_digest == restore_digest
    assert second.restored_digest == restore_digest
    assert digest_file(target) == restore_digest
