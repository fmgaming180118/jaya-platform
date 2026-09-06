"""Executable evidence gates for P29 Binary Cortex."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from jaya_core.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    EncryptedFileKeyStore,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.binary_cortex import BinaryCortexService
from jaya_core.pillars.local_capabilities import BINARY_DOT_CAPABILITY_ID
from jaya_core.pillars.local_types import LocalPillarError
from jaya_core.security.cryptographic_skin import CryptographicSkin

_IDENTITY_SECRET = "p29-test-identity-secret-" + ("i" * 40)
_SKIN_SECRET = "p29-test-skin-secret-" + ("s" * 40)


def _components(root: Path) -> tuple[DNAAnchor, CryptographicSkin, BinaryCortexService]:
    identity_root = root / "identity"
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(identity_root / "keystore", _IDENTITY_SECRET),
    )
    try:
        anchor.load_identity()
    except DNAAnchorError:
        anchor.enroll()
    skin = CryptographicSkin(
        root / "core.db",
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    service = BinaryCortexService(
        artifact_root=root / "binary",
        cryptographic_skin=skin,
    )
    return anchor, skin, service


def _close(anchor: DNAAnchor, skin: CryptographicSkin) -> None:
    skin.close()
    anchor.close()


def _weights(rows: int, features: int) -> list[list[int]]:
    return [
        [1 if (row * 7 + column * 3) % 5 else -1 for column in range(features)]
        for row in range(rows)
    ]


def _dense(weights: list[list[int]], vector: list[int]) -> list[int]:
    return [sum(a * b for a, b in zip(row, vector, strict=True)) for row in weights]


def test_p029_packing_tail_bits_and_benchmark_match_dense_reference() -> None:
    service = BinaryCortexService()
    left = [1 if index % 3 else -1 for index in range(1_031)]
    right = [1 if index % 7 else -1 for index in range(1_031)]

    dot = service.dot(left, right)
    benchmark = service.benchmark(left, right, iterations=50)

    expected = sum(a * b for a, b in zip(left, right, strict=True))
    assert dot.data["dot_product"] == expected
    assert dot.data["packed_bytes"] == 129
    assert benchmark.data["dot_product"] == expected
    assert benchmark.data["binary_storage_bytes"] == 258
    assert benchmark.data["storage_compression_ratio"] > 31
    assert benchmark.data["binary_elapsed_ns"] > 0
    assert benchmark.data["dense_elapsed_ns"] > 0


def test_p029_authenticated_artifact_inference_receipt_and_restart(tmp_path: Path) -> None:
    weights = _weights(5, 73)
    vector = [1 if index % 4 else -1 for index in range(73)]
    anchor, skin, service = _components(tmp_path)
    try:
        installed = service.install_artifact("tail-model", weights)
        inferred = service.infer("tail-model", vector)
        receipt = service.verify_receipt(inferred.data["receipt_id"])
        artifact_path = Path(installed.data["artifact_path"])
        raw_artifact = artifact_path.read_bytes()
    finally:
        _close(anchor, skin)

    assert inferred.data["outputs"] == _dense(weights, vector)
    assert inferred.data["fallback_used"] is False
    expected_kernel = (
        "CPP20_XNOR_POPCOUNT"
        if service.kernel_profile()["compute"]["native_available"]
        else "PYTHON_INT_XNOR_POPCOUNT"
    )
    assert inferred.data["kernel"] == expected_kernel
    assert receipt.data["output_sha256"] == inferred.data["output_sha256"]
    assert installed.data["storage_compression_ratio"] >= 29.2
    assert b'"packed_rows"' not in raw_artifact

    restarted_anchor, restarted_skin, restarted = _components(tmp_path)
    try:
        inspected = restarted.inspect_artifact("tail-model")
        replayed = restarted.infer("tail-model", vector)
    finally:
        _close(restarted_anchor, restarted_skin)
    assert inspected.data["payload_sha256"] == installed.data["payload_sha256"]
    assert replayed.data["outputs"] == inferred.data["outputs"]


def test_p029_rejects_tampered_envelope_and_receipt(tmp_path: Path) -> None:
    anchor, skin, service = _components(tmp_path)
    try:
        installed = service.install_artifact("tamper-model", _weights(2, 16))
        artifact_path = Path(installed.data["artifact_path"])
        envelope = json.loads(artifact_path.read_text(encoding="utf-8"))
        envelope["ciphertext"] = "AAAA"
        artifact_path.write_text(json.dumps(envelope), encoding="utf-8")
        with pytest.raises(LocalPillarError) as tampered:
            service.inspect_artifact("tamper-model")
        assert tampered.value.code == "ARTIFACT_AUTHENTICATION_FAILED"

        service.install_artifact("receipt-model", _weights(2, 16))
        inferred = service.infer("receipt-model", [1] * 16)
        receipt_path = (
            tmp_path
            / "binary"
            / "receipts"
            / f"{inferred.data['receipt_id']}.jaya-binary-receipt.json"
        )
        receipt_envelope = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt_envelope["subject"] = "binary-receipt:forged"
        receipt_path.write_text(json.dumps(receipt_envelope), encoding="utf-8")
        with pytest.raises(LocalPillarError) as bad_receipt:
            service.verify_receipt(inferred.data["receipt_id"])
        assert bad_receipt.value.code == "RECEIPT_SCOPE_INVALID"
    finally:
        _close(anchor, skin)


def test_p029_unsupported_kernel_requires_explicit_labeled_fallback(tmp_path: Path) -> None:
    weights = _weights(3, 17)
    vector = [1 if index % 2 else -1 for index in range(17)]
    anchor, skin, service = _components(tmp_path)
    try:
        service.install_artifact("fallback-model", weights)
        unavailable = BinaryCortexService(
            artifact_root=tmp_path / "binary",
            cryptographic_skin=skin,
            kernel_probe=lambda: False,
        )
        with pytest.raises(LocalPillarError) as blocked:
            unavailable.infer("fallback-model", vector)
        assert blocked.value.code == "KERNEL_UNAVAILABLE"

        fallback = unavailable.infer("fallback-model", vector, allow_dense_fallback=True)
    finally:
        _close(anchor, skin)
    assert fallback.code == "DENSE_FALLBACK_EXECUTED"
    assert fallback.data["fallback_used"] is True
    assert fallback.data["kernel"] == "PYTHON_DENSE_REFERENCE_FALLBACK"
    assert fallback.data["outputs"] == _dense(weights, vector)


def test_p029_timeout_shape_resource_and_security_fail_closed(tmp_path: Path) -> None:
    with pytest.raises(LocalPillarError) as security:
        BinaryCortexService(artifact_root=tmp_path).install_artifact("no-security", _weights(1, 8))
    assert security.value.code == "ARTIFACT_SECURITY_UNAVAILABLE"

    anchor, skin, service = _components(tmp_path / "secured")
    try:
        service.install_artifact("bounded-model", _weights(2, 9))
        with pytest.raises(LocalPillarError) as shape:
            service.infer("bounded-model", [1] * 8)
        assert shape.value.code == "SHAPE_MISMATCH"
        with pytest.raises(LocalPillarError) as traversal:
            service.inspect_artifact("../escape")
        assert traversal.value.code == "INVALID_INPUT"
        with pytest.raises(LocalPillarError) as fields:
            service.execute(
                {
                    "action": "infer",
                    "artifact_id": "bounded-model",
                    "input": [1] * 9,
                    "unknown": True,
                }
            )
        assert fields.value.code == "UNKNOWN_FIELD"

        ticks = iter((0.0, 0.01, 0.02))
        timed = BinaryCortexService(
            artifact_root=tmp_path / "secured" / "binary",
            cryptographic_skin=skin,
            monotonic=lambda: next(ticks),
        )
        with pytest.raises(LocalPillarError) as timeout:
            timed.infer("bounded-model", [1] * 9, timeout_seconds=0.001)
        assert timeout.value.code == "EXECUTION_TIMEOUT"
    finally:
        _close(anchor, skin)


def test_p029_concurrent_inference_is_exact_and_receipts_are_unique(tmp_path: Path) -> None:
    weights = _weights(8, 257)
    vector = [1 if index % 11 else -1 for index in range(257)]
    expected = _dense(weights, vector)
    anchor, skin, service = _components(tmp_path)
    try:
        service.install_artifact("concurrent-model", weights)
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(
                pool.map(
                    lambda _: service.infer("concurrent-model", vector),
                    range(16),
                )
            )
    finally:
        _close(anchor, skin)
    assert all(result.data["outputs"] == expected for result in results)
    assert len({result.data["receipt_id"] for result in results}) == 16


def test_p029_canonical_runtime_installs_and_executes_authenticated_artifact(
    tmp_path: Path,
) -> None:
    weights = _weights(4, 33)
    vector = [1 if index % 3 else -1 for index in range(33)]
    anchor, skin, _ = _components(tmp_path)
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "runtime.db",
        local_pillar_data_dir=tmp_path / "runtime-pillars",
        identity_anchor=anchor,
        cryptographic_skin=skin,
    )
    try:
        installed = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {"action": "install", "artifact_id": "runtime-model", "weights": weights},
        )
        inferred = runtime.execute_local_pillar(
            BINARY_DOT_CAPABILITY_ID,
            {"action": "infer", "artifact_id": "runtime-model", "input": vector},
        )
        manifest = runtime.capability_registry.lookup(BINARY_DOT_CAPABILITY_ID)
    finally:
        runtime.close()
    assert installed.code == "BINARY_ARTIFACT_INSTALLED"
    assert inferred.data["outputs"] == _dense(weights, vector)
    assert manifest is not None
    assert manifest.provider == "authenticated_binary_cortex_service"
    assert manifest.version == "2.0"
