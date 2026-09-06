"""P13 representative lifecycle, integrity, concurrency, and failure gates."""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jaya_core.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from jaya_core.capabilities.puzzle import CapabilityPuzzleRegistry
from jaya_core.memory.backup import SQLiteBackupEngine
from jaya_core.mesh.sync_engine import MeshSyncEngine
from jaya_core.security.capsule import CapsuleError, CapsuleKind, JayaCapsuleCodec
from jaya_core.security.cryptographic_skin import (
    CryptographicSkin,
    CryptographicSkinError,
    CryptographicSkinFailureCode,
    SealedEnvelope,
)
from jaya_core.sync.event_log import AppendOnlyEventLog

_IDENTITY_SECRET = "p13-lifecycle-identity-" + ("i" * 40)
_SKIN_SECRET = "p13-lifecycle-skin-" + ("s" * 40)


def _anchor(root: Path) -> DNAAnchor:
    return DNAAnchor(
        root,
        EncryptedFileKeyStore(root / "keystore", _IDENTITY_SECRET),
    )


def _skin(
    database: Path,
    anchor: DNAAnchor,
    **options: object,
) -> CryptographicSkin:
    return CryptographicSkin(
        database,
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        **options,  # type: ignore[arg-type]
    )


def _canonical(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()


@pytest.mark.parametrize("target", ("salt", "registry", "nonce"))
def test_p13_keyed_state_authenticator_detects_storage_tamper(
    tmp_path: Path,
    target: str,
) -> None:
    root = tmp_path / target
    database = root / "core.db"
    identity = _anchor(root / "identity")
    identity.enroll()
    skin = _skin(database, identity)
    skin.seal(
        b"state-auth-target",
        purpose="core.artifact",
        subject=f"artifact:{target}",
    )
    skin.close()

    with sqlite3.connect(database) as connection:
        if target == "salt":
            replacement = base64.urlsafe_b64encode(b"q" * 16).decode().rstrip("=")
            connection.execute(
                "UPDATE crypto_skin_metadata SET value = ? WHERE key = 'kdf_salt'",
                (replacement,),
            )
        elif target == "registry":
            row = connection.execute(
                """
                SELECT key_id, state, retired_at, previous_key_id
                FROM crypto_skin_keys WHERE state = 'ACTIVE'
                """
            ).fetchone()
            assert row is not None
            changed_created_at = "2026-08-30T00:00:00+00:00"
            digest = hashlib.sha256(
                _canonical(
                    {
                        "created_at": changed_created_at,
                        "key_id": row[0],
                        "previous_key_id": row[3],
                        "retired_at": row[2],
                        "state": row[1],
                    }
                )
            ).hexdigest()
            connection.execute(
                """
                UPDATE crypto_skin_keys SET created_at = ?, row_digest = ?
                WHERE key_id = ?
                """,
                (changed_created_at, digest, row[0]),
            )
        else:
            connection.execute(
                "UPDATE crypto_skin_nonces SET reserved_at = '2026-08-30T00:00:00+00:00'"
            )

    with pytest.raises(CryptographicSkinError) as captured:
        _skin(database, identity)
    identity.close()
    assert captured.value.code is CryptographicSkinFailureCode.AUDIT_CORRUPT


def test_p13_keyed_state_rejects_attacker_recomputed_public_audit_chain(
    tmp_path: Path,
) -> None:
    database = tmp_path / "core.db"
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    skin = _skin(database, identity)
    skin.seal(
        b"audit-auth-target",
        purpose="core.artifact",
        subject="artifact:audit-auth",
    )
    skin.close()

    with sqlite3.connect(database) as connection:
        row = connection.execute(
            """
            SELECT event_id, occurred_at, event, previous_sha256
            FROM crypto_skin_audit ORDER BY event_id DESC LIMIT 1
            """
        ).fetchone()
        assert row is not None
        forged_payload = {"envelope_id": "env-forged"}
        forged_digest = hashlib.sha256(
            _canonical(
                {
                    "occurred_at": row[1],
                    "event": row[2],
                    "payload": forged_payload,
                    "previous_sha256": row[3],
                }
            )
        ).hexdigest()
        connection.execute(
            """
            UPDATE crypto_skin_audit SET payload_json = ?, event_sha256 = ?
            WHERE event_id = ?
            """,
            (_canonical(forged_payload).decode(), forged_digest, row[0]),
        )

    with pytest.raises(CryptographicSkinError) as captured:
        _skin(database, identity)
    identity.close()
    assert captured.value.code is CryptographicSkinFailureCode.AUDIT_CORRUPT


def test_p13_clock_attestation_and_nonce_providers_fail_stably(
    tmp_path: Path,
) -> None:
    now = [datetime(2026, 8, 30, 12, 0, tzinfo=UTC)]
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    database = tmp_path / "core.db"
    skin = _skin(
        database,
        identity,
        clock=lambda: now[0],
        max_clock_skew_seconds=2,
    )
    envelope = skin.seal(
        b"clock-target",
        purpose="core.artifact",
        subject="artifact:clock",
    )
    now[0] -= timedelta(seconds=3)
    with pytest.raises(CryptographicSkinError) as skewed:
        skin.open(envelope)
    skin.close()
    assert skewed.value.code is CryptographicSkinFailureCode.CLOCK_SKEW

    def broken_clock() -> datetime:
        raise RuntimeError("provider detail must not escape")

    with pytest.raises(CryptographicSkinError) as clock:
        _skin(tmp_path / "clock.db", identity, clock=broken_clock)
    assert clock.value.code is CryptographicSkinFailureCode.CLOCK_UNAVAILABLE

    signer_failure = CryptographicSkin(
        tmp_path / "signer.db",
        _SKIN_SECRET,
        attestation_signer=lambda _purpose, _digest: (_ for _ in ()).throw(
            RuntimeError("signer detail must not escape")
        ),
        attestation_verifier=identity.verify_attestation,
    )
    with pytest.raises(CryptographicSkinError) as signer:
        signer_failure.seal(
            b"signer-target",
            purpose="core.artifact",
            subject="artifact:signer",
        )
    assert signer.value.code is CryptographicSkinFailureCode.ATTESTATION_UNAVAILABLE
    assert signer_failure.health_check()["ready"] is True
    signer_failure.close()

    verifier_failure = CryptographicSkin(
        database,
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: identity.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=lambda _value: (_ for _ in ()).throw(
            RuntimeError("verifier detail must not escape")
        ),
        clock=lambda: datetime(2026, 8, 30, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(CryptographicSkinError) as verifier:
        verifier_failure.open(envelope)
    verifier_failure.close()
    assert verifier.value.code is CryptographicSkinFailureCode.ATTESTATION_UNAVAILABLE

    nonce_failure = _skin(
        tmp_path / "nonce.db",
        identity,
        nonce_factory=lambda _size: (_ for _ in ()).throw(
            RuntimeError("nonce detail must not escape")
        ),
    )
    with pytest.raises(CryptographicSkinError) as nonce:
        nonce_failure.seal(
            b"nonce-target",
            purpose="core.artifact",
            subject="artifact:nonce",
        )
    assert nonce.value.code is CryptographicSkinFailureCode.NONCE_UNAVAILABLE
    assert nonce_failure.health_check()["ready"] is True
    nonce_failure.close()
    identity.close()


def test_p13_schema_downgrade_requires_explicit_migration_and_strict_envelope(
    tmp_path: Path,
) -> None:
    database = tmp_path / "core.db"
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    skin = _skin(database, identity)
    envelope = skin.seal(
        b"migration-target",
        purpose="core.artifact",
        subject="artifact:migration",
    )
    skin.close()

    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM crypto_skin_metadata WHERE key IN "
            "('storage_schema_version', 'state_auth_hmac_sha256')"
        )
    with pytest.raises(CryptographicSkinError) as downgrade:
        _skin(database, identity)
    assert downgrade.value.code is CryptographicSkinFailureCode.STORAGE_SCHEMA_UNSUPPORTED

    migrated = _skin(database, identity, allow_legacy_migration=True)
    assert migrated.open(envelope) == b"migration-target"
    malformed = {**envelope.to_dict(), "schema_version": "1"}
    with pytest.raises(CryptographicSkinError) as schema:
        migrated.open(malformed)
    oversized_attestation = replace(envelope, attestation={"blob": "x" * 70_000})
    with pytest.raises(CryptographicSkinError) as oversized:
        migrated.open(oversized_attestation)
    migrated.close()
    migrated.close()
    identity.close()
    assert schema.value.code is CryptographicSkinFailureCode.CORRUPT_ENVELOPE
    assert oversized.value.code is CryptographicSkinFailureCode.CORRUPT_ENVELOPE
    assert migrated.status()["mode"] == "CLOSED"


def test_p13_storage_timeout_and_concurrent_writers_are_bounded(
    tmp_path: Path,
) -> None:
    identity_root = tmp_path / "identity"
    enrollment = _anchor(identity_root)
    enrollment.enroll()
    database = tmp_path / "core.db"
    initial = _skin(database, enrollment)
    initial.close()

    with sqlite3.connect(database, timeout=0.1) as blocker:
        blocker.execute("BEGIN EXCLUSIVE")
        with pytest.raises(CryptographicSkinError) as locked:
            _skin(database, enrollment, storage_timeout_seconds=0.05)
    assert locked.value.code is CryptographicSkinFailureCode.STORAGE_ERROR
    enrollment.close()

    first_anchor = _anchor(identity_root)
    second_anchor = _anchor(identity_root)
    first = _skin(database, first_anchor)
    second = _skin(database, second_anchor)

    def exercise(skin: CryptographicSkin, prefix: str) -> list[SealedEnvelope]:
        results: list[SealedEnvelope] = []
        for index in range(10):
            payload = f"{prefix}-{index}".encode()
            envelope = skin.seal(
                payload,
                purpose="core.concurrent",
                subject=f"artifact:{prefix}-{index}",
            )
            assert skin.open(envelope) == payload
            results.append(envelope)
        return results

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = (
                executor.submit(exercise, first, "first"),
                executor.submit(exercise, second, "second"),
            )
            envelopes = [envelope for future in futures for envelope in future.result()]
        assert len({envelope.nonce for envelope in envelopes}) == 20
    finally:
        first.close()
        second.close()
        first_anchor.close()
        second_anchor.close()

    restarted_anchor = _anchor(identity_root)
    restarted = _skin(database, restarted_anchor)
    try:
        status = restarted.health_check()
        assert status["ready"] is True
        assert status["state_authenticated"] is True
        assert status["reserved_nonces"] == 20
    finally:
        restarted.close()
        restarted_anchor.close()


def test_p13_classical_capsule_covers_brain_backup_puzzle_and_mesh(
    tmp_path: Path,
) -> None:
    identity = _anchor(tmp_path / "identity")
    identity.enroll()
    skin = _skin(tmp_path / "core.db", identity)
    codec = JayaCapsuleCodec(skin)
    try:
        for kind in CapsuleKind:
            payload = f"private-{kind.value}-payload".encode()
            capsule = codec.seal(
                payload,
                kind=kind,
                subject=f"subject:{kind.value}",
            )
            assert payload not in capsule
            assert (
                codec.open(
                    capsule,
                    expected_kind=kind,
                    expected_subject=f"subject:{kind.value}",
                )
                == payload
            )
            with pytest.raises(CapsuleError):
                codec.open(
                    capsule,
                    expected_kind=CapsuleKind.BRAIN,
                    expected_subject="wrong",
                )

        source = tmp_path / "memory.db"
        with sqlite3.connect(source) as connection:
            connection.execute("CREATE TABLE memory(value TEXT NOT NULL)")
            connection.execute("INSERT INTO memory VALUES ('persistent-memory')")
        backup_capsule = tmp_path / "memory-backup.jayac"
        restored = tmp_path / "restored.db"
        backup = SQLiteBackupEngine()
        backup.create_secure_backup(
            source,
            backup_capsule,
            codec,
            subject="memory:primary",
        )
        assert b"persistent-memory" not in backup_capsule.read_bytes()
        backup.restore_secure_backup(
            backup_capsule,
            restored,
            codec,
            subject="memory:primary",
        )
        with sqlite3.connect(restored) as connection:
            assert connection.execute("SELECT value FROM memory").fetchone()[0] == (
                "persistent-memory"
            )

        puzzle_dir = tmp_path / "puzzles" / "sealed.echo"
        puzzle_dir.mkdir(parents=True)
        puzzle_source = b"""
class EchoPuzzle:
    def health_check(self):
        return True
    def invoke(self, payload):
        return {"echo": payload["message"]}
def create_puzzle():
    return EchoPuzzle()
"""
        puzzle_capsule = codec.seal(
            puzzle_source,
            kind=CapsuleKind.PUZZLE,
            subject="puzzle:sealed.echo:1.0.0",
        )
        artifact = puzzle_dir / "puzzle.jayac"
        artifact.write_bytes(puzzle_capsule)
        (puzzle_dir / "puzzle.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "puzzle_id": "sealed.echo",
                    "capability_id": "sealed.echo",
                    "version": "1.0.0",
                    "artifact": artifact.name,
                    "artifact_sha256": hashlib.sha256(puzzle_capsule).hexdigest(),
                    "artifact_format": "jayac",
                    "risk_class": "READ_ONLY",
                }
            ),
            encoding="utf-8",
        )
        registry = CapabilityPuzzleRegistry((tmp_path / "puzzles",), capsule_codec=codec)
        try:
            assert set(registry.refresh().values()) == {"CONNECTED"}
            assert registry.invoke("sealed.echo", {"message": "verified"}).result == {
                "echo": "verified"
            }
        finally:
            registry.close()

        source_log = AppendOnlyEventLog(node_id="node-a")
        target_log = AppendOnlyEventLog(node_id="node-b")
        source_log.append("MEMORY_UPDATE", {"private": "mesh-secret"})
        source_mesh = MeshSyncEngine("node-a", source_log, capsule_codec=codec)
        target_mesh = MeshSyncEngine("node-b", target_log, capsule_codec=codec)
        mesh_capsule = source_mesh.create_secure_sync_capsule("node-b")
        assert b"mesh-secret" not in mesh_capsule
        assert target_mesh.receive_secure_sync_capsule("node-a", mesh_capsule) == (1, 0)
        assert target_mesh.receive_secure_sync_capsule("node-a", mesh_capsule) == (0, 1)
    finally:
        skin.close()
        identity.close()
