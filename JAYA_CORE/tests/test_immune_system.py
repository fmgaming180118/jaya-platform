"""Executable evidence gates for P12 Immune System."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from scripts.run_jaya_core_server import _build_runtime
from src.brain_v2.protection.dna_anchor import (
    DNAAnchor,
    DNAAnchorError,
    EncryptedFileKeyStore,
)
from src.cognitive.runtime import JayaCoreRuntime
from src.core_config import ConfigurationError, CoreConfig
from src.security.cryptographic_skin import CryptographicSkin
from src.security.immune_system import (
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


def _components(root: Path, *, limit: int = 1024 * 1024) -> tuple[
    DNAAnchor, CryptographicSkin, ImmuneSystem
]:
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
        CoreConfig.from_env(
            {"JAYA_REQUIRE_IMMUNE_SYSTEM": "true"}, core_dir=tmp_path
        )
    assert (
        "invalid:JAYA_REQUIRE_IMMUNE_SYSTEM_REQUIRES_ZERO_TRUST"
        in missing.value.issues
    )
    assert (
        "invalid:JAYA_REQUIRE_IMMUNE_SYSTEM_REQUIRES_CRYPTOGRAPHIC_SKIN"
        in missing.value.issues
    )

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
