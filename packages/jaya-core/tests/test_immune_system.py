"""Executable evidence gates for P12 Immune System."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from scripts.run_jaya_core_server import _build_runtime

from jaya_core.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    EncryptedFileKeyStore,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.core_config import ConfigurationError, CoreConfig
from jaya_core.security.cryptographic_skin import CryptographicSkin
from jaya_core.security.immune_system import (
    ImmuneFailureCode,
    ImmuneSystem,
    ImmuneSystemError,
    IncidentState,
)

_IDENTITY_SECRET = "p12-identity-secret-" + ("i" * 40)
_SKIN_SECRET = "p12-skin-secret-" + ("s" * 40)


def _anchor(root: Path) -> DNAAnchor:
    return DNAAnchor(
        root,
        EncryptedFileKeyStore(root / "keystore", _IDENTITY_SECRET),
    )


def _components(
    root: Path, *, limit: int = 1024 * 1024
) -> tuple[DNAAnchor, CryptographicSkin, ImmuneSystem]:
    anchor = _anchor(root / "identity")
    try:
        anchor.load_identity()
    except DNAAnchorError:
        anchor.enroll()
    database = root / "core.db"
    skin = CryptographicSkin(
        database,
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    immune = ImmuneSystem(
        database,
        root,
        skin,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
        max_artifact_bytes=limit,
    )
    return anchor, skin, immune


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_p12_integrity_quarantine_restart_and_verified_recovery(
    tmp_path: Path,
) -> None:
    approved = b"approved-core-artifact-v1"
    target = tmp_path / "core.jaya"
    target.write_bytes(approved)
    anchor, skin, immune = _components(tmp_path)
    immune.register_target("core-artifact", target, _digest(target), critical=True)
    assert immune.scan("core-artifact") is None

    unsafe = b"unsafe-modified-core-artifact"
    target.write_bytes(unsafe)
    incident = immune.scan("core-artifact")
    assert incident is not None
    assert incident.state is IncidentState.OPEN
    assert incident.quarantine_path is not None
    quarantine = tmp_path / incident.quarantine_path
    assert not target.exists()
    assert quarantine.is_file()
    assert unsafe not in quarantine.read_bytes()
    assert immune.safe_stop() is True
    immune.close()
    skin.close()
    anchor.close()

    anchor, skin, immune = _components(tmp_path)
    assert immune.safe_stop() is True
    target.write_bytes(b"wrong-replacement")
    with pytest.raises(ImmuneSystemError) as rejected:
        immune.recover_target("core-artifact")
    assert rejected.value.code is ImmuneFailureCode.RECOVERY_REJECTED
    target.write_bytes(approved)
    resolved = immune.recover_target("core-artifact")
    assert resolved.state is IncidentState.RESOLVED
    assert immune.status()["ready"] is True
    assert immune.audit_chain_valid() is True
    immune.close()
    skin.close()
    anchor.close()


def test_p12_quarantine_limit_still_enters_persistent_safe_stop(
    tmp_path: Path,
) -> None:
    target = tmp_path / "bounded.bin"
    target.write_bytes(b"ok")
    anchor, skin, immune = _components(tmp_path, limit=4)
    immune.register_target("bounded", target, _digest(target), critical=False)
    target.write_bytes(b"payload-over-limit")
    with pytest.raises(ImmuneSystemError) as captured:
        immune.scan("bounded")
    assert captured.value.code is ImmuneFailureCode.ARTIFACT_TOO_LARGE
    assert immune.safe_stop() is True
    assert target.exists()
    immune.close()
    skin.close()
    anchor.close()


def test_p12_dependency_circuit_breaker_persists_and_requires_health_probe(
    tmp_path: Path,
) -> None:
    anchor, skin, immune = _components(tmp_path)
    assert immune.can_execute("remote-model") is True
    assert immune.record_dependency_failure("remote-model", "TIMEOUT") == 1
    assert immune.record_dependency_failure("remote-model", "TIMEOUT") == 2
    assert immune.record_dependency_failure("remote-model", "INVALID_RESPONSE") == 3
    assert immune.can_execute("remote-model") is False
    assert immune.safe_stop() is True
    metrics = immune.security_metrics()
    assert metrics["circuits"] == {"OPEN": 1}
    assert metrics["incidents"]["DEPENDENCY_ABUSE:HIGH:OPEN"] == 1
    immune.close()
    skin.close()
    anchor.close()

    anchor, skin, immune = _components(tmp_path)
    assert immune.can_execute("remote-model") is False
    with pytest.raises(ImmuneSystemError) as captured:
        immune.recover_dependency("remote-model", lambda: False)
    assert captured.value.code is ImmuneFailureCode.RECOVERY_REJECTED
    resolved = immune.recover_dependency("remote-model", lambda: True)
    assert resolved.state is IncidentState.RESOLVED
    assert immune.can_execute("remote-model") is True
    assert immune.safe_stop() is False
    immune.close()
    skin.close()
    anchor.close()


def test_p12_path_escape_and_audit_tamper_fail_closed(tmp_path: Path) -> None:
    anchor, skin, immune = _components(tmp_path)
    outside = tmp_path.parent / "outside-p12.bin"
    outside.write_bytes(b"outside")
    with pytest.raises(ImmuneSystemError) as captured:
        immune.register_target("escape", outside, _digest(outside), critical=True)
    assert captured.value.code is ImmuneFailureCode.PATH_OUTSIDE_ROOT
    local = tmp_path / "inside.bin"
    local.write_bytes(b"inside")
    immune.register_target("inside", local, _digest(local), critical=True)
    immune.close()
    skin.close()
    anchor.close()

    with sqlite3.connect(tmp_path / "core.db") as connection:
        connection.execute(
            "UPDATE immune_audit SET payload_json = ? WHERE event_id = 1",
            ('{"tampered":true}',),
        )
    anchor = _anchor(tmp_path / "identity")
    skin = CryptographicSkin(
        tmp_path / "core.db",
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    with pytest.raises(ImmuneSystemError) as corrupt:
        ImmuneSystem(
            tmp_path / "core.db",
            tmp_path,
            skin,
            attestation_signer=lambda purpose, digest: anchor.sign_attestation(
                purpose, digest
            ).to_dict(),
            attestation_verifier=anchor.verify_attestation,
        )
    assert corrupt.value.code is ImmuneFailureCode.AUDIT_CORRUPT
    skin.close()
    anchor.close()
    outside.unlink(missing_ok=True)


def test_p12_runtime_readiness_tracks_persistent_incident(tmp_path: Path) -> None:
    target = tmp_path / "runtime-owned.bin"
    target.write_bytes(b"runtime-safe")
    anchor, skin, immune = _components(tmp_path)
    immune.register_target("runtime-owned", target, _digest(target), critical=True)
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "runtime.db",
        identity_anchor=anchor,
        identity_required=True,
        cryptographic_skin=skin,
        cryptographic_skin_required=True,
        immune_system=immune,
        immune_system_required=True,
    )
    assert runtime.is_ready() is True
    target.write_bytes(b"runtime-unsafe")
    immune.scan("runtime-owned")
    assert runtime.is_ready() is False
    assert runtime.operational_snapshot()["immune_system"]["safe_stop"] is True
    runtime.close()


def test_p12_config_and_canonical_launcher_wiring(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError) as missing:
        CoreConfig.from_env({"JAYA_REQUIRE_IMMUNE_SYSTEM": "true"}, core_dir=tmp_path)
    assert "invalid:JAYA_REQUIRE_IMMUNE_SYSTEM_REQUIRES_ZERO_TRUST" in missing.value.issues
    assert "invalid:JAYA_REQUIRE_IMMUNE_SYSTEM_REQUIRES_CRYPTOGRAPHIC_SKIN" in missing.value.issues

    data_root = tmp_path / "data"
    data_root.mkdir()
    identity_root = data_root / "identity"
    anchor = _anchor(identity_root)
    anchor.enroll()
    anchor.close()
    environment = {
        "JAYA_CORE_DATA_DIR": str(data_root),
        "JAYA_IDENTITY_DIR": str(identity_root),
        "JAYA_NODE_ID": "p12-launcher-node",
        "JAYA_REQUIRE_IDENTITY": "true",
        "JAYA_IDENTITY_KEY_SECRET": _IDENTITY_SECRET,
        "JAYA_REQUIRE_PRIVACY": "true",
        "JAYA_PRIVACY_KEY_SECRET": "p12-privacy-secret-" + ("p" * 40),
        "JAYA_REQUIRE_ZERO_TRUST": "true",
        "JAYA_REQUIRE_CRYPTOGRAPHIC_SKIN": "true",
        "JAYA_CRYPTOGRAPHIC_SKIN_SECRET": _SKIN_SECRET,
        "JAYA_REQUIRE_IMMUNE_SYSTEM": "true",
    }
    config = CoreConfig.from_env(environment, core_dir=tmp_path)
    runtime = _build_runtime(config)
    try:
        snapshot = runtime.operational_snapshot()
        assert snapshot["immune_system"]["ready"] is True
        assert runtime.is_ready() is True
    finally:
        runtime.close()


def test_p12_signed_audit_rejects_recomputed_public_hash_chain(tmp_path: Path) -> None:
    target = tmp_path / "signed-audit.bin"
    target.write_bytes(b"approved")
    anchor, skin, immune = _components(tmp_path)
    immune.register_target("signed-audit", target, _digest(target), critical=True)
    immune.close()
    skin.close()
    anchor.close()

    with sqlite3.connect(tmp_path / "core.db") as connection:
        row = connection.execute(
            """
            SELECT event_id, occurred_at, event, previous_sha256
            FROM immune_audit ORDER BY event_id LIMIT 1
            """
        ).fetchone()
        forged_payload = {"target_id": "attacker-controlled"}
        content = {
            "occurred_at": row[1],
            "event": row[2],
            "payload": forged_payload,
            "previous_sha256": row[3],
        }
        forged_digest = hashlib.sha256(
            json.dumps(
                content,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        ).hexdigest()
        connection.execute(
            """
            UPDATE immune_audit SET payload_json = ?, event_sha256 = ?
            WHERE event_id = ?
            """,
            (
                json.dumps(forged_payload, sort_keys=True, separators=(",", ":")),
                forged_digest,
                row[0],
            ),
        )

    anchor = _anchor(tmp_path / "identity")
    skin = CryptographicSkin(
        tmp_path / "core.db",
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    with pytest.raises(ImmuneSystemError) as forged:
        ImmuneSystem(
            tmp_path / "core.db",
            tmp_path,
            skin,
            attestation_signer=lambda purpose, digest: anchor.sign_attestation(
                purpose, digest
            ).to_dict(),
            attestation_verifier=anchor.verify_attestation,
        )
    skin.close()
    anchor.close()
    assert forged.value.code is ImmuneFailureCode.AUDIT_CORRUPT


def test_p12_signed_incident_and_circuit_state_reject_recomputed_rows(
    tmp_path: Path,
) -> None:
    target = tmp_path / "state.bin"
    target.write_bytes(b"approved")
    anchor, skin, immune = _components(tmp_path)
    immune.register_target("signed-state", target, _digest(target), critical=True)
    target.write_bytes(b"unsafe")
    immune.scan("signed-state")
    for _ in range(3):
        immune.record_dependency_failure("signed-dependency", "TIMEOUT")
    immune.close()
    skin.close()
    anchor.close()

    with sqlite3.connect(tmp_path / "core.db") as connection:
        row = connection.execute(
            "SELECT incident_id, record_json FROM immune_incidents LIMIT 1"
        ).fetchone()
        record = json.loads(row[1])
        record["source_id"] = "forged-source"
        serialized = json.dumps(
            record,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        connection.execute(
            """
            UPDATE immune_incidents SET record_json = ?, source_id = ?, row_digest = ?
            WHERE incident_id = ?
            """,
            (
                serialized,
                "forged-source",
                hashlib.sha256(serialized.encode()).hexdigest(),
                row[0],
            ),
        )
        connection.execute(
            """
            UPDATE immune_circuit_breakers
            SET failures = 0, state = 'CLOSED'
            WHERE dependency_id = 'signed-dependency'
            """
        )

    anchor = _anchor(tmp_path / "identity")
    skin = CryptographicSkin(
        tmp_path / "core.db",
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )
    with pytest.raises(ImmuneSystemError) as forged:
        ImmuneSystem(
            tmp_path / "core.db",
            tmp_path,
            skin,
            attestation_signer=lambda purpose, digest: anchor.sign_attestation(
                purpose, digest
            ).to_dict(),
            attestation_verifier=anchor.verify_attestation,
        )
    skin.close()
    anchor.close()
    assert forged.value.code is ImmuneFailureCode.AUDIT_CORRUPT


def test_p12_quarantine_authenticated_open_and_tamper_rejection(tmp_path: Path) -> None:
    target = tmp_path / "quarantine.bin"
    target.write_bytes(b"approved")
    anchor, skin, immune = _components(tmp_path)
    immune.register_target("quarantine-open", target, _digest(target), critical=True)
    unsafe = b"unsafe-quarantine-payload"
    target.write_bytes(unsafe)
    incident = immune.scan("quarantine-open")
    assert incident is not None
    assert immune.open_quarantine(incident.incident_id) == unsafe
    quarantine = tmp_path / str(incident.quarantine_path)
    envelope = json.loads(quarantine.read_text(encoding="utf-8"))
    envelope["subject"] = "target:forged"
    quarantine.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ImmuneSystemError) as tampered:
        immune.open_quarantine(incident.incident_id)
    immune.close()
    skin.close()
    anchor.close()
    assert tampered.value.code is ImmuneFailureCode.QUARANTINE_CORRUPT


def test_p12_dependency_probe_timeout_and_exception_fail_closed(tmp_path: Path) -> None:
    anchor, skin, immune = _components(tmp_path)
    immune.dependency_probe_timeout_seconds = 0.05
    for _ in range(3):
        immune.record_dependency_failure("bounded-probe", "TIMEOUT")
    blocker = threading.Event()
    started = time.perf_counter()
    with pytest.raises(ImmuneSystemError) as timeout:
        immune.recover_dependency("bounded-probe", lambda: blocker.wait(2.0))
    elapsed = time.perf_counter() - started

    def failed_probe() -> bool:
        raise ValueError("provider unavailable")

    with pytest.raises(ImmuneSystemError) as failed:
        immune.recover_dependency("bounded-probe", failed_probe)
    assert immune.can_execute("bounded-probe") is False
    immune.close()
    skin.close()
    anchor.close()

    assert timeout.value.code is ImmuneFailureCode.PROBE_TIMEOUT
    assert elapsed < 0.5
    assert failed.value.code is ImmuneFailureCode.PROBE_FAILED


def test_p12_atomic_signer_failure_rolls_back_circuit_and_audit(
    tmp_path: Path,
) -> None:
    anchor = _anchor(tmp_path / "identity")
    anchor.enroll()
    skin = CryptographicSkin(
        tmp_path / "core.db",
        _SKIN_SECRET,
        attestation_signer=lambda purpose, digest: anchor.sign_attestation(
            purpose, digest
        ).to_dict(),
        attestation_verifier=anchor.verify_attestation,
    )

    def fail_audit_signing(purpose: str, digest: str) -> dict[str, object]:
        if purpose == "immune-audit-v1":
            raise RuntimeError("injected immune audit signer failure")
        return anchor.sign_attestation(purpose, digest).to_dict()

    immune = ImmuneSystem(
        tmp_path / "core.db",
        tmp_path,
        skin,
        attestation_signer=fail_audit_signing,
        attestation_verifier=anchor.verify_attestation,
    )
    with pytest.raises(RuntimeError, match="injected immune audit signer failure"):
        immune.record_dependency_failure("atomic-dependency", "TIMEOUT")
    circuits = immune._connection.execute(
        "SELECT COUNT(*) FROM immune_circuit_breakers"
    ).fetchone()[0]
    audits = immune._connection.execute("SELECT COUNT(*) FROM immune_audit").fetchone()[0]
    immune.close()
    skin.close()
    anchor.close()

    assert circuits == 0
    assert audits == 0


def test_p12_concurrent_scan_creates_single_incident_and_quarantine(
    tmp_path: Path,
) -> None:
    target = tmp_path / "concurrent.bin"
    target.write_bytes(b"approved")
    anchor, skin, immune = _components(tmp_path)
    immune.register_target("concurrent-target", target, _digest(target), critical=True)
    target.write_bytes(b"concurrent-unsafe")
    with ThreadPoolExecutor(max_workers=4) as pool:
        incidents = list(pool.map(lambda _: immune.scan("concurrent-target"), range(8)))
    incident_ids = {incident.incident_id for incident in incidents if incident is not None}
    quarantine_paths = {incident.quarantine_path for incident in incidents if incident is not None}
    status = immune.status()
    immune.close()
    skin.close()
    anchor.close()

    assert len(incident_ids) == 1
    assert len(quarantine_paths) == 1
    assert status["open_incidents"] == 1
    assert status["quarantined_artifacts"] == 1
    assert status["state_authenticated"] is True


def test_p12_legacy_public_hash_state_upgrades_to_dna_attestations(
    tmp_path: Path,
) -> None:
    target = tmp_path / "legacy.bin"
    target.write_bytes(b"approved")
    anchor, skin, immune = _components(tmp_path)
    immune.register_target("legacy-target", target, _digest(target), critical=True)
    target.write_bytes(b"unsafe")
    immune.scan("legacy-target")
    immune.record_dependency_failure("legacy-dependency", "TIMEOUT")
    immune.close()
    skin.close()
    anchor.close()
    with sqlite3.connect(tmp_path / "core.db") as connection:
        connection.execute("UPDATE immune_incidents SET attestation_json = NULL")
        connection.execute("UPDATE immune_circuit_breakers SET attestation_json = NULL")
        connection.execute("UPDATE immune_audit SET attestation_json = NULL")

    anchor, skin, immune = _components(tmp_path)
    status = immune.status()
    missing = sum(
        immune._connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE attestation_json IS NULL"
        ).fetchone()[0]
        for table in (
            "immune_incidents",
            "immune_circuit_breakers",
            "immune_audit",
        )
    )
    immune.close()
    skin.close()
    anchor.close()

    assert missing == 0
    assert status["storage_schema_version"] == 2
    assert status["state_authenticated"] is True
