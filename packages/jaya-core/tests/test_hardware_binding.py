"""Executable evidence gates for P14 Hardware Locked."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from scripts.run_jaya_core_server import _build_runtime

from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.brain_v2.protection.hardware import (
    HardwareBindingError,
    HardwareBindingFailureCode,
    NodeBindingAuthority,
    WindowsDPAPIMachineProvider,
)
from jaya_core.core_config import CoreConfig
from jaya_core.security.cryptographic_skin import (
    CryptographicSkin,
    CryptographicSkinError,
    CryptographicSkinFailureCode,
)

_IDENTITY_SECRET = "p14-identity-secret-" + ("i" * 40)


class _TestRootProvider:
    hardware_backed = True

    def __init__(self, provider_id: str, key: bytes | None = None) -> None:
        self.provider_id = provider_id
        self._key = key or AESGCM.generate_key(bit_length=256)

    def available(self) -> bool:
        return True

    def wrap(self, plaintext: bytes, associated_data: bytes) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(self._key).encrypt(nonce, plaintext, associated_data)

    def unwrap(self, wrapped: bytes, associated_data: bytes) -> bytes:
        try:
            return AESGCM(self._key).decrypt(wrapped[:12], wrapped[12:], associated_data)
        except (InvalidTag, ValueError) as exc:
            raise HardwareBindingError(
                HardwareBindingFailureCode.UNWRAP_FAILED,
                "test hardware root rejected wrapped data",
            ) from exc


class _UnavailableProvider(_TestRootProvider):
    def available(self) -> bool:
        return False


def _anchor(root: Path) -> DNAAnchor:
    return DNAAnchor(
        root,
        EncryptedFileKeyStore(root / "keystore", _IDENTITY_SECRET),
    )


def _authority(
    database: Path,
    anchor: DNAAnchor,
    provider: object,
) -> NodeBindingAuthority:
    return NodeBindingAuthority(
        database,
        provider,  # type: ignore[arg-type]
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )


def test_p14_brain_node_instance_are_separate_and_restart_authorizes(
    tmp_path: Path,
) -> None:
    identity_root = tmp_path / "identity"
    anchor = _anchor(identity_root)
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    provider = _TestRootProvider("test-root-node-a")
    authority = _authority(database, anchor, provider)
    binding = authority.enroll(identity.brain_id, "node-a")
    first = authority.authorize_boot(identity.brain_id, "node-a", b"a" * 32)
    authority.close()
    anchor.close()

    restarted_anchor = _anchor(identity_root)
    restarted = _authority(database, restarted_anchor, provider)
    try:
        second = restarted.authorize_boot(identity.brain_id, "node-a", b"b" * 32)
        status = restarted.status(identity.brain_id)
    finally:
        restarted.close()
        restarted_anchor.close()

    assert binding.brain_id == identity.brain_id
    assert binding.node_id == "node-a"
    assert first.instance_id != second.instance_id
    assert second.brain_id == first.brain_id
    assert second.node_id == first.node_id
    assert first.challenge_sha256 != second.challenge_sha256
    assert status["ready"] is True


def test_p14_cloned_database_wrong_node_and_wrong_root_fail_closed(
    tmp_path: Path,
) -> None:
    anchor = _anchor(tmp_path / "identity")
    identity, _ = anchor.enroll()
    database = tmp_path / "source.db"
    provider = _TestRootProvider("test-root-node-a")
    source = _authority(database, anchor, provider)
    source.enroll(identity.brain_id, "node-a")
    source.close()
    clone_database = tmp_path / "clone.db"
    shutil.copy2(database, clone_database)

    wrong_node = _authority(clone_database, anchor, provider)
    try:
        with pytest.raises(HardwareBindingError) as node:
            wrong_node.authorize_boot(identity.brain_id, "node-b", b"c" * 32)
    finally:
        wrong_node.close()
    wrong_root = _authority(
        clone_database,
        anchor,
        _TestRootProvider("test-root-node-a"),
    )
    try:
        with pytest.raises(HardwareBindingError) as root:
            wrong_root.authorize_boot(identity.brain_id, "node-a", b"d" * 32)
    finally:
        wrong_root.close()
        anchor.close()

    assert node.value.code is HardwareBindingFailureCode.NODE_MISMATCH
    assert root.value.code is HardwareBindingFailureCode.UNWRAP_FAILED


def test_p14_owner_authorized_migration_preserves_brain_and_revokes_source(
    tmp_path: Path,
) -> None:
    identity_root = tmp_path / "identity"
    anchor = _anchor(identity_root)
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    source_provider = _TestRootProvider("test-root-node-a")
    target_provider = _TestRootProvider("test-root-node-b")
    source = _authority(database, anchor, source_provider)
    original = source.enroll(identity.brain_id, "node-a")
    source_context = source.binding_key_context(identity.brain_id, "node-a")
    migrated = source.migrate(identity.brain_id, "node-b", target_provider)
    source.close()

    target = _authority(database, anchor, target_provider)
    try:
        receipt = target.authorize_boot(identity.brain_id, "node-b", b"e" * 32)
        target_context = target.binding_key_context(identity.brain_id, "node-b")
        target.revoke(identity.brain_id)
        with pytest.raises(HardwareBindingError) as revoked:
            target.authorize_boot(identity.brain_id, "node-b", b"f" * 32)
    finally:
        target.close()
        anchor.close()

    assert migrated.previous_binding_id == original.binding_id
    assert migrated.brain_id == original.brain_id == receipt.brain_id
    assert migrated.node_id == "node-b"
    assert source_context == target_context
    assert revoked.value.code is HardwareBindingFailureCode.BINDING_NOT_FOUND


def test_p14_tamper_and_audit_corruption_fail_closed(tmp_path: Path) -> None:
    anchor = _anchor(tmp_path / "identity")
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    provider = _TestRootProvider("test-root-node-a")
    authority = _authority(database, anchor, provider)
    authority.enroll(identity.brain_id, "node-a")
    authority.close()

    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE hardware_bindings SET wrapped_secret = 'AAAA'")
    corrupted = _authority(database, anchor, provider)
    try:
        with pytest.raises(HardwareBindingError) as binding:
            corrupted.authorize_boot(identity.brain_id, "node-a", b"g" * 32)
    finally:
        corrupted.close()
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE hardware_binding_audit SET payload_json = '{}' WHERE event_id = 1"
        )
    try:
        with pytest.raises(HardwareBindingError) as audit:
            _authority(database, anchor, provider)
    finally:
        anchor.close()

    assert binding.value.code is HardwareBindingFailureCode.CORRUPT_BINDING
    assert audit.value.code is HardwareBindingFailureCode.AUDIT_CORRUPT


def test_p14_signed_audit_rejects_attacker_recomputed_hash_chain(
    tmp_path: Path,
) -> None:
    anchor = _anchor(tmp_path / "identity")
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    provider = _TestRootProvider("test-root-node-a")
    authority = _authority(database, anchor, provider)
    authority.enroll(identity.brain_id, "node-a")
    authority.close()

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT event_id, occurred_at, event, previous_sha256
            FROM hardware_binding_audit ORDER BY event_id LIMIT 1
            """
        ).fetchone()
        forged_payload = {"brain_id": identity.brain_id, "node_id": "attacker-node"}
        forged_content = {
            "occurred_at": row[1],
            "event": row[2],
            "payload": forged_payload,
            "previous_sha256": row[3],
        }
        forged_digest = hashlib.sha256(
            json.dumps(
                forged_content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        connection.execute(
            """
            UPDATE hardware_binding_audit
            SET payload_json = ?, event_sha256 = ? WHERE event_id = ?
            """,
            (
                json.dumps(
                    forged_payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                forged_digest,
                row[0],
            ),
        )
    try:
        with pytest.raises(HardwareBindingError) as forged:
            _authority(database, anchor, provider)
    finally:
        anchor.close()
    assert forged.value.code is HardwareBindingFailureCode.AUDIT_CORRUPT


def test_p14_legacy_hash_chain_is_upgraded_to_signed_audit(tmp_path: Path) -> None:
    identity_root = tmp_path / "identity"
    anchor = _anchor(identity_root)
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    provider = _TestRootProvider("test-root-node-a")
    authority = _authority(database, anchor, provider)
    authority.enroll(identity.brain_id, "node-a")
    authority.close()
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE hardware_binding_audit SET attestation_json = NULL")
    anchor.close()

    restarted_anchor = _anchor(identity_root)
    restarted = _authority(database, restarted_anchor, provider)
    try:
        status = restarted.status(identity.brain_id)
        attestation_json = restarted._connection.execute(
            "SELECT attestation_json FROM hardware_binding_audit LIMIT 1"
        ).fetchone()[0]
    finally:
        restarted.close()
        restarted_anchor.close()

    assert status["storage_schema_version"] == 2
    assert status["audit_attestations_verified"] is True
    assert json.loads(attestation_json)["purpose"] == "hardware-binding-audit-v1"


def test_p14_failed_migration_rolls_back_state_and_audit_atomically(
    tmp_path: Path,
) -> None:
    anchor = _anchor(tmp_path / "identity")
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    source_provider = _TestRootProvider("test-root-node-a")
    target_provider = _TestRootProvider("test-root-node-b")
    authority = _authority(database, anchor, source_provider)
    authority.enroll(identity.brain_id, "node-a")
    with authority._connection:
        authority._connection.execute(
            """
            CREATE TRIGGER reject_p14_migration_audit
            BEFORE INSERT ON hardware_binding_audit
            WHEN NEW.event = 'NODE_MIGRATED'
            BEGIN
                SELECT RAISE(ABORT, 'injected migration audit failure');
            END
            """
        )
    with pytest.raises(HardwareBindingError) as interrupted:
        authority.migrate(identity.brain_id, "node-b", target_provider)
    with authority._connection:
        authority._connection.execute("DROP TRIGGER reject_p14_migration_audit")
    try:
        receipt = authority.authorize_boot(identity.brain_id, "node-a", b"r" * 32)
        rows = authority._connection.execute(
            "SELECT node_id, state FROM hardware_bindings ORDER BY created_at"
        ).fetchall()
    finally:
        authority.close()
        anchor.close()

    assert interrupted.value.code is HardwareBindingFailureCode.STORAGE_ERROR
    assert receipt.node_id == "node-a"
    assert [tuple(row) for row in rows] == [("node-a", "ACTIVE")]


def test_p14_signer_failure_rolls_back_migration_atomically(tmp_path: Path) -> None:
    anchor = _anchor(tmp_path / "identity")
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    source_provider = _TestRootProvider("test-root-node-a")
    target_provider = _TestRootProvider("test-root-node-b")
    enrolled = _authority(database, anchor, source_provider)
    enrolled.enroll(identity.brain_id, "node-a")
    enrolled.close()

    def fail_audit_signing(purpose: str, digest: str) -> dict[str, object]:
        if purpose == "hardware-binding-audit-v1":
            raise RuntimeError("injected DNA signer failure")
        return anchor.sign_attestation(purpose, digest).to_dict()

    failing = NodeBindingAuthority(
        database,
        source_provider,
        attestation_signer=fail_audit_signing,
        attestation_verifier=anchor.verify_attestation,
    )
    with pytest.raises(RuntimeError, match="injected DNA signer failure"):
        failing.migrate(identity.brain_id, "node-b", target_provider)
    rows = failing._connection.execute(
        "SELECT node_id, state FROM hardware_bindings ORDER BY created_at"
    ).fetchall()
    audit_valid = failing.audit_chain_valid()
    failing.close()

    recovered = _authority(database, anchor, source_provider)
    try:
        receipt = recovered.authorize_boot(identity.brain_id, "node-a", b"s" * 32)
    finally:
        recovered.close()
        anchor.close()

    assert [tuple(row) for row in rows] == [("node-a", "ACTIVE")]
    assert audit_valid is True
    assert receipt.node_id == "node-a"


def test_p14_migration_preserves_existing_p13_encrypted_brain(tmp_path: Path) -> None:
    anchor = _anchor(tmp_path / "identity")
    identity, _ = anchor.enroll()
    database = tmp_path / "core.db"
    source_provider = _TestRootProvider("test-root-node-a")
    target_provider = _TestRootProvider("test-root-node-b")
    source = _authority(database, anchor, source_provider)
    source.enroll(identity.brain_id, "node-a")
    source_context = source.binding_key_context(identity.brain_id, "node-a")
    secret = "p14-portable-skin-secret-" + ("s" * 40)
    skin = CryptographicSkin(
        database,
        secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        key_binding_context=source_context,
    )
    envelope = skin.seal(
        b"portable-encrypted-brain",
        purpose="core.brain-capsule",
        subject="brain:portable-p14",
    )
    skin.close()
    source.migrate(identity.brain_id, "node-b", target_provider)
    source.close()

    target = _authority(database, anchor, target_provider)
    target_context = target.binding_key_context(identity.brain_id, "node-b")
    migrated_skin = CryptographicSkin(
        database,
        secret,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        key_binding_context=target_context,
    )
    try:
        restored = migrated_skin.open(envelope)
    finally:
        migrated_skin.close()
        target.close()
        anchor.close()

    assert target_context == source_context
    assert restored == b"portable-encrypted-brain"


def test_p14_unavailable_provider_is_explicit(tmp_path: Path) -> None:
    anchor = _anchor(tmp_path / "identity")
    anchor.enroll()
    try:
        with pytest.raises(HardwareBindingError) as unavailable:
            _authority(
                tmp_path / "core.db",
                anchor,
                _UnavailableProvider("unavailable-root"),
            )
    finally:
        anchor.close()
    assert unavailable.value.code is HardwareBindingFailureCode.PROVIDER_UNAVAILABLE


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is host-specific")
def test_p14_windows_dpapi_production_provider_roundtrip(tmp_path: Path) -> None:
    provider = WindowsDPAPIMachineProvider()
    assert provider.available() is True
    plaintext = os.urandom(32)
    associated_data = hashlib.sha256(b"p14-production-provider").digest()
    wrapped = provider.wrap(plaintext, associated_data)

    assert wrapped != plaintext
    assert provider.unwrap(wrapped, associated_data) == plaintext
    assert provider.provider_id == "windows-dpapi-machine-v1"
    assert provider.hardware_backed is False
    assert provider.health()["protection_scope"] == "LOCAL_MACHINE"
    assert provider.health()["hardware_attestation"] == "BLOCKED_EXTERNAL"
    with pytest.raises(HardwareBindingError) as wrong_context:
        provider.unwrap(wrapped, b"wrong-context")
    assert wrong_context.value.code is HardwareBindingFailureCode.UNWRAP_FAILED


def test_p14_hardware_context_binds_p13_data_key(tmp_path: Path) -> None:
    anchor = _anchor(tmp_path / "identity")
    identity, _ = anchor.enroll()
    provider = _TestRootProvider("test-root-node-a")
    binding = _authority(tmp_path / "core.db", anchor, provider)
    binding.enroll(identity.brain_id, "node-a")
    context = binding.binding_key_context(identity.brain_id, "node-a")
    skin = CryptographicSkin(
        tmp_path / "core.db",
        "p14-skin-secret-" + ("s" * 40),
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        key_binding_context=context,
    )
    skin.seal(
        b"hardware-bound-artifact",
        purpose="core.artifact",
        subject="artifact:hardware-bound",
    )
    assert skin.status()["hardware_bound"] is True
    skin.close()

    try:
        with pytest.raises(CryptographicSkinError) as wrong_node:
            CryptographicSkin(
                tmp_path / "core.db",
                "p14-skin-secret-" + ("s" * 40),
                attestation_signer=lambda purpose, digest: anchor.sign_attestation(
                    purpose, digest
                ).to_dict(),
                attestation_verifier=anchor.verify_attestation,
                key_binding_context=b"x" * 32,
            )
    finally:
        binding.close()
        anchor.close()
    assert wrong_node.value.code is CryptographicSkinFailureCode.AUDIT_CORRUPT


@pytest.mark.skipif(os.name != "nt", reason="canonical provider is Windows DPAPI")
def test_p14_canonical_launcher_requires_enrolled_current_node(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "data"
    identity_root = data_dir / "identity"
    data_dir.mkdir()
    anchor = _anchor(identity_root)
    identity, _ = anchor.enroll()
    binding = _authority(
        data_dir / "jaya_core_runtime.db",
        anchor,
        WindowsDPAPIMachineProvider(),
    )
    binding.enroll(identity.brain_id, "node-p14")
    binding.close()
    anchor.close()
    environment = {
        "JAYA_ENVIRONMENT": "test",
        "JAYA_SOUL_PASSWORD": "p14-soul-" + ("o" * 40),
        "JAYA_CORE_API_KEY": "p14-api-" + ("a" * 40),
        "JAYA_CORE_DATA_DIR": str(data_dir),
        "JAYA_NODE_ID": "node-p14",
        "JAYA_REQUIRE_IDENTITY": "true",
        "JAYA_IDENTITY_DIR": str(identity_root),
        "JAYA_IDENTITY_KEY_SECRET": _IDENTITY_SECRET,
        "JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN": "true",
        "JAYA_CRYPTOGRAPHIC_SKIN_SECRET": "p14-skin-" + ("s" * 40),
        "JAYA_REQUIRE_HARDWARE_LOCK": "true",
    }
    config = CoreConfig.from_env(environment, core_dir=tmp_path)
    runtime = _build_runtime(config)
    try:
        envelope = runtime.seal_artifact(
            b"canonical-hardware-bound",
            purpose="core.artifact",
            subject="artifact:canonical-p14",
        )
        snapshot = runtime.operational_snapshot()
        assert runtime.open_artifact(envelope) == b"canonical-hardware-bound"
        assert snapshot["hardware_locked"]["ready"] is True
        assert snapshot["hardware_locked"]["hardware_backed"] is False
        assert snapshot["cryptographic_skin"]["hardware_bound"] is True
    finally:
        runtime.close()

    wrong_node = dict(environment, JAYA_NODE_ID="node-clone")
    wrong_config = CoreConfig.from_env(wrong_node, core_dir=tmp_path)
    with pytest.raises(HardwareBindingError) as clone:
        _build_runtime(wrong_config)
    assert clone.value.code is HardwareBindingFailureCode.NODE_MISMATCH
