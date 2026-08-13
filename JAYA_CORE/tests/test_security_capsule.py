"""P13/P16 one-file capsule and secure backup integration tests."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from src.brain_v2.protection.dna_anchor import DNAAnchor, EncryptedFileKeyStore
from src.brain_v2.protection.pqc import QuantumPolicy, QuantumSuite
from src.capabilities.puzzle import CapabilityPuzzleRegistry
from src.memory.backup import SQLiteBackupEngine
from src.mesh.sync_engine import MeshSyncEngine
from src.security.capsule import CapsuleError, CapsuleKind, JayaCapsuleCodec
from src.security.cryptographic_skin import CryptographicSkin
from src.security.quantum_lifecycle import PersistentQuantumAuthority
from src.sync.event_log import AppendOnlyEventLog


def _stack(root: Path):
    identity_root = root / "identity"
    anchor = DNAAnchor(
        identity_root,
        EncryptedFileKeyStore(
            identity_root / "keystore", "capsule-identity-" + ("i" * 40)
        ),
    )
    anchor.enroll()
    database = root / "security.db"
    skin = CryptographicSkin(
        database,
        "capsule-skin-" + ("s" * 40),
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    quantum = PersistentQuantumAuthority(
        database,
        skin,
        QuantumPolicy(
            policy_version=1,
            minimum_suite=QuantumSuite.HYBRID_ED25519_ML_DSA_65,
            asset_lifetime_days=3650,
            threat_horizon_year=2035,
            allow_classical_until_year=2028,
        ),
        current_year=2026,
    )
    return anchor, skin, quantum, JayaCapsuleCodec(
        skin, quantum_authority=quantum, quantum_required=True
    )


@pytest.mark.parametrize("kind", tuple(CapsuleKind))
def test_one_file_capsule_covers_all_core_boundaries(
    tmp_path: Path, kind: CapsuleKind
) -> None:
    anchor, skin, quantum, codec = _stack(tmp_path / kind.value)
    payload = f"private-{kind.value}-payload".encode()
    capsule = codec.seal(payload, kind=kind, subject=f"subject:{kind.value}")
    assert capsule.startswith(b"JAYA-CAPSULE\x00\x01\n")
    assert payload not in capsule
    assert codec.open(
        capsule,
        expected_kind=kind,
        expected_subject=f"subject:{kind.value}",
    ) == payload
    with pytest.raises(CapsuleError):
        codec.open(
            capsule,
            expected_kind=CapsuleKind.BRAIN,
            expected_subject="wrong",
        )
    quantum.close()
    skin.close()
    anchor.close()


def test_secure_sqlite_backup_capsule_restores_real_database(tmp_path: Path) -> None:
    root = tmp_path / "backup"
    root.mkdir()
    anchor, skin, quantum, codec = _stack(root)
    source = root / "memory.db"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE memory(value TEXT NOT NULL)")
        connection.execute("INSERT INTO memory VALUES ('persistent-memory')")
    capsule = root / "memory-backup.jayac"
    restored = root / "restored.db"
    engine = SQLiteBackupEngine()
    engine.create_secure_backup(source, capsule, codec, subject="memory:primary")
    assert b"persistent-memory" not in capsule.read_bytes()
    engine.restore_secure_backup(
        capsule, restored, codec, subject="memory:primary"
    )
    with sqlite3.connect(restored) as connection:
        assert connection.execute("SELECT value FROM memory").fetchone()[0] == (
            "persistent-memory"
        )
    quantum.close()
    skin.close()
    anchor.close()


def test_sealed_puzzle_executes_only_after_p13_p16_verification(
    tmp_path: Path,
) -> None:
    root = tmp_path / "puzzle-security"
    root.mkdir()
    anchor, skin, quantum, codec = _stack(root)
    puzzle_dir = root / "puzzles" / "sealed.echo"
    puzzle_dir.mkdir(parents=True)
    source = b"""
class EchoPuzzle:
    def health_check(self):
        return True
    def invoke(self, payload):
        return {"echo": payload["message"]}
def create_puzzle():
    return EchoPuzzle()
"""
    capsule = codec.seal(
        source,
        kind=CapsuleKind.PUZZLE,
        subject="puzzle:sealed.echo:1.0.0",
    )
    artifact = puzzle_dir / "puzzle.jayac"
    artifact.write_bytes(capsule)
    (puzzle_dir / "puzzle.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "puzzle_id": "sealed.echo",
                "capability_id": "sealed.echo",
                "version": "1.0.0",
                "artifact": artifact.name,
                "artifact_sha256": hashlib.sha256(capsule).hexdigest(),
                "artifact_format": "jayac",
                "risk_class": "READ_ONLY",
            }
        ),
        encoding="utf-8",
    )
    registry = CapabilityPuzzleRegistry((root / "puzzles",), capsule_codec=codec)
    assert set(registry.refresh().values()) == {"CONNECTED"}
    result = registry.invoke("sealed.echo", {"message": "verified"})
    assert result.result == {"echo": "verified"}
    registry.close()
    quantum.close()
    skin.close()
    anchor.close()


def test_mesh_sync_uses_authenticated_encrypted_capsule(tmp_path: Path) -> None:
    root = tmp_path / "mesh-security"
    root.mkdir()
    anchor, skin, quantum, codec = _stack(root)
    source_log = AppendOnlyEventLog(node_id="node-a")
    target_log = AppendOnlyEventLog(node_id="node-b")
    source_log.append("MEMORY_UPDATE", {"private": "mesh-secret"})
    source = MeshSyncEngine("node-a", source_log, capsule_codec=codec)
    target = MeshSyncEngine("node-b", target_log, capsule_codec=codec)
    capsule = source.create_secure_sync_capsule("node-b")
    assert b"mesh-secret" not in capsule
    assert target.receive_secure_sync_capsule("node-a", capsule) == (1, 0)
    assert target.receive_secure_sync_capsule("node-a", capsule) == (0, 1)
    quantum.close()
    skin.close()
    anchor.close()
