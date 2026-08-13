"""Executable evidence gates for P13 Cryptographic Skin."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from scripts.run_jaya_core_server import _build_runtime
from src.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from src.cognitive.runtime import JayaCoreRuntime
from src.core_config import ConfigurationError, CoreConfig
from src.security.cryptographic_skin import (
    CryptographicSkin,
    CryptographicSkinError,
    CryptographicSkinFailureCode,
)

_IDENTITY_SECRET = "p13-identity-secret-" + ("i" * 40)
_SKIN_SECRET = "p13-cryptographic-skin-secret-" + ("s" * 40)


def _anchor(root: Path) -> DNAAnchor:
    return DNAAnchor(
        root,
        EncryptedFileKeyStore(root / "keystore", _IDENTITY_SECRET),
    )


def _skin(
    database: Path,
    anchor: DNAAnchor,
    *,
    secret: str = _SKIN_SECRET,
    clock: object | None = None,
    nonce_factory: object | None = None,
    max_payload_bytes: int = 16 * 1024 * 1024,
) -> CryptographicSkin:
    options: dict[str, object] = {
        "attestation_signer": (
            lambda purpose, digest: anchor.sign_attestation(purpose, digest).to_dict()
        ),
        "attestation_verifier": anchor.verify_attestation,
        "max_payload_bytes": max_payload_bytes,
    }
    if clock is not None:
        options["clock"] = clock
    if nonce_factory is not None:
        options["nonce_factory"] = nonce_factory
    return CryptographicSkin(database, secret, **options)  # type: ignore[arg-type]


def test_p13_aead_dna_envelope_roundtrip_and_plaintext_absence(
    tmp_path: Path,
) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    database = tmp_path / "core.db"
    payload = b"SYNTHETIC-P13-PRIVATE-ARTIFACT"
    skin = _skin(database, identity)
    try:
        envelope = skin.seal(
            payload,
            purpose="core.artifact",
            subject="artifact:p13-roundtrip",
            content_type="application/jaya-artifact",
            ttl_seconds=600,
        )
        restored = skin.open(envelope)
        status = skin.status()
    finally:
        skin.close()
        identity.close()

    assert restored == payload
    assert envelope.algorithm_suite == "AES-256-GCM+ED25519"
    assert envelope.attestation["payload_sha256"] == envelope.digest()
    assert status["ready"] is True
    assert status["audit_chain_valid"] is True
    assert payload not in database.read_bytes()
    rendered = json.dumps(envelope.to_dict(), sort_keys=True)
    assert "SYNTHETIC-P13-PRIVATE-ARTIFACT" not in rendered


@pytest.mark.parametrize(
    ("field", "replacement", "expected"),
    (
        (
            "purpose",
            "core.backup",
            CryptographicSkinFailureCode.SIGNATURE_INVALID,
        ),
        (
            "ciphertext",
            "AAAA",
            CryptographicSkinFailureCode.SIGNATURE_INVALID,
        ),
        (
            "nonce",
            "AAAA",
            CryptographicSkinFailureCode.SIGNATURE_INVALID,
        ),
        (
            "algorithm_suite",
            "BASE64",
            CryptographicSkinFailureCode.CORRUPT_ENVELOPE,
        ),
    ),
)
def test_p13_metadata_ciphertext_nonce_and_suite_tamper_fail_closed(
    tmp_path: Path,
    field: str,
    replacement: str,
    expected: CryptographicSkinFailureCode,
) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    skin = _skin(tmp_path / "core.db", identity)
    try:
        envelope = skin.seal(
            b"tamper-target",
            purpose="core.artifact",
            subject="artifact:tamper",
        )
        changed = replace(envelope, **{field: replacement})
        with pytest.raises(CryptographicSkinError) as captured:
            skin.open(changed)
    finally:
        skin.close()
        identity.close()

    assert captured.value.code is expected


def test_p13_wrong_secret_signature_and_unknown_field_fail_closed(
    tmp_path: Path,
) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    database = tmp_path / "core.db"
    skin = _skin(database, identity)
    envelope = skin.seal(
        b"wrong-key-target",
        purpose="core.artifact",
        subject="artifact:wrong-key",
    )
    skin.close()

    wrong = _skin(
        database,
        identity,
        secret="p13-different-secret-" + ("x" * 40),
    )
    try:
        with pytest.raises(CryptographicSkinError) as wrong_key:
            wrong.open(envelope)
        forged = replace(
            envelope,
            attestation={**envelope.attestation, "signature": "AAAA"},
        )
        with pytest.raises(CryptographicSkinError) as signature:
            wrong.open(forged)
        unknown = {**envelope.to_dict(), "unexpected": True}
        with pytest.raises(CryptographicSkinError) as schema:
            wrong.open(unknown)
    finally:
        wrong.close()
        identity.close()

    assert wrong_key.value.code is CryptographicSkinFailureCode.DECRYPTION_FAILED
    assert signature.value.code is CryptographicSkinFailureCode.SIGNATURE_INVALID
    assert schema.value.code is CryptographicSkinFailureCode.CORRUPT_ENVELOPE


def test_p13_restart_rotation_continuity_and_revocation(tmp_path: Path) -> None:
    identity_root = tmp_path / "identity"
    identity = _anchor(identity_root)
    identity.enroll()
    database = tmp_path / "core.db"
    skin = _skin(database, identity)
    old = skin.seal(
        b"before-rotation",
        purpose="core.artifact",
        subject="artifact:before-rotation",
    )
    old_key = old.key_id
    new_key = skin.rotate_key()
    new = skin.seal(
        b"after-rotation",
        purpose="core.artifact",
        subject="artifact:after-rotation",
    )
    assert new.key_id == new_key
    assert skin.open(old) == b"before-rotation"
    skin.close()
    identity.close()

    restarted_identity = _anchor(identity_root)
    restarted = _skin(database, restarted_identity)
    try:
        assert restarted.open(old) == b"before-rotation"
        assert restarted.open(new) == b"after-rotation"
        with pytest.raises(CryptographicSkinError) as active:
            restarted.revoke_key(new_key)
        assert active.value.code is CryptographicSkinFailureCode.KEY_STATE_INVALID
        restarted.revoke_key(old_key)
        with pytest.raises(CryptographicSkinError) as revoked:
            restarted.open(old)
        assert revoked.value.code is CryptographicSkinFailureCode.KEY_REVOKED
        assert restarted.open(new) == b"after-rotation"
        assert restarted.audit_chain_valid() is True
    finally:
        restarted.close()
        restarted_identity.close()


def test_p13_expiry_payload_bound_and_invalid_clock_fail_closed(
    tmp_path: Path,
) -> None:
    current = [datetime(2026, 8, 14, 10, 0, tzinfo=timezone.utc)]
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    skin = _skin(
        tmp_path / "core.db",
        identity,
        clock=lambda: current[0],
        max_payload_bytes=8,
    )
    try:
        envelope = skin.seal(
            b"12345678",
            purpose="core.artifact",
            subject="artifact:expiry",
            ttl_seconds=10,
        )
        with pytest.raises(CryptographicSkinError) as oversized:
            skin.seal(
                b"123456789",
                purpose="core.artifact",
                subject="artifact:oversized",
            )
        current[0] += timedelta(seconds=10)
        with pytest.raises(CryptographicSkinError) as expired:
            skin.open(envelope)
    finally:
        skin.close()
        identity.close()

    assert oversized.value.code is CryptographicSkinFailureCode.PAYLOAD_TOO_LARGE
    assert expired.value.code is CryptographicSkinFailureCode.ENVELOPE_EXPIRED


def test_p13_persistent_nonce_registry_rejects_reuse(tmp_path: Path) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    fixed_nonce = b"n" * 12
    skin = _skin(
        tmp_path / "core.db",
        identity,
        nonce_factory=lambda _: fixed_nonce,
    )
    try:
        skin.seal(
            b"first",
            purpose="core.artifact",
            subject="artifact:nonce-1",
        )
        with pytest.raises(CryptographicSkinError) as collision:
            skin.seal(
                b"second",
                purpose="core.artifact",
                subject="artifact:nonce-2",
            )
    finally:
        skin.close()
        identity.close()

    assert collision.value.code is CryptographicSkinFailureCode.NONCE_COLLISION


def test_p13_corrupt_audit_blocks_restart(tmp_path: Path) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    database = tmp_path / "core.db"
    skin = _skin(database, identity)
    skin.seal(
        b"audit-target",
        purpose="core.artifact",
        subject="artifact:audit",
    )
    skin.close()

    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE crypto_skin_audit SET payload_json = '{}' WHERE event_id = 1"
        )

    try:
        with pytest.raises(CryptographicSkinError) as corrupt:
            _skin(database, identity)
    finally:
        identity.close()

    assert corrupt.value.code is CryptographicSkinFailureCode.AUDIT_CORRUPT


def test_p13_envelope_latency_and_size_are_measured(tmp_path: Path) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    skin = _skin(tmp_path / "core.db", identity)
    payload = b"p" * 4_096
    durations_ms: list[float] = []
    sizes: list[int] = []
    try:
        for index in range(20):
            started = time.perf_counter()
            envelope = skin.seal(
                payload,
                purpose="core.benchmark",
                subject=f"artifact:benchmark-{index}",
            )
            assert skin.open(envelope) == payload
            durations_ms.append((time.perf_counter() - started) * 1_000)
            sizes.append(len(json.dumps(envelope.to_dict()).encode("utf-8")))
    finally:
        skin.close()
        identity.close()

    assert max(durations_ms) < 500
    assert max(sizes) < len(payload) * 2


def test_p13_runtime_vertical_slice_and_unconfigured_failure(tmp_path: Path) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    skin = _skin(tmp_path / "runtime.db", identity)
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "runtime.db",
        identity_anchor=identity,
        identity_required=True,
        cryptographic_skin=skin,
        cryptographic_skin_required=True,
    )
    try:
        envelope = runtime.seal_artifact(
            b"runtime-artifact",
            purpose="core.artifact",
            subject="artifact:runtime",
            content_type="application/jaya-artifact",
        )
        assert runtime.open_artifact(envelope.to_dict()) == b"runtime-artifact"
        assert runtime.operational_snapshot()["cryptographic_skin"]["ready"] is True
    finally:
        runtime.close()

    unconfigured = JayaCoreRuntime(db_path=tmp_path / "unconfigured.db")
    try:
        with pytest.raises(CryptographicSkinError) as missing:
            unconfigured.seal_artifact(
                b"blocked",
                purpose="core.artifact",
                subject="artifact:blocked",
            )
    finally:
        unconfigured.close()
    assert missing.value.code is CryptographicSkinFailureCode.NOT_CONFIGURED


def test_p13_canonical_launcher_wires_validated_secret_and_identity(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    identity_dir = data_dir / "identity"
    data_dir.mkdir()
    enrollment = _anchor(identity_dir)
    enrollment.enroll()
    enrollment.close()
    environment = {
        "JAYA_ENVIRONMENT": "test",
        "JAYA_SOUL_PASSWORD": "p13-soul-" + ("o" * 40),
        "JAYA_CORE_API_KEY": "p13-api-" + ("a" * 40),
        "JAYA_CORE_DATA_DIR": str(data_dir),
        "JAYA_REQUIRE_IDENTITY": "true",
        "JAYA_IDENTITY_DIR": str(identity_dir),
        "JAYA_IDENTITY_KEY_SECRET": _IDENTITY_SECRET,
        "JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN": "true",
        "JAYA_CRYPTOGRAPHIC_SKIN_SECRET": _SKIN_SECRET,
    }
    config = CoreConfig.from_env(environment, core_dir=tmp_path)
    runtime = _build_runtime(config)
    try:
        envelope = runtime.seal_artifact(
            b"launcher-artifact",
            purpose="core.artifact",
            subject="artifact:launcher",
        )
        assert runtime.open_artifact(envelope) == b"launcher-artifact"
        assert config.to_safe_dict()["cryptographic_skin_secret_configured"] is True
        assert _SKIN_SECRET not in json.dumps(config.to_safe_dict())
    finally:
        runtime.close()

    invalid_environment = dict(environment)
    invalid_environment["JAYA_REQUIRE_IDENTITY"] = "false"
    with pytest.raises(ConfigurationError) as dependency:
        CoreConfig.from_env(invalid_environment, core_dir=tmp_path)
    assert (
        "invalid:JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN_REQUIRES_IDENTITY"
        in dependency.value.issues
    )
