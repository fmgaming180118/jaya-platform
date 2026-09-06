"""Unit and integration tests for Pillar 09 Neural Regeneration."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.maintenance_capabilities import (
    REGENERATION_CAPABILITY_ID,
    NeuralRegenerationCapability,
)

SIGNING_KEY = bytes(range(32))


@pytest.fixture
def test_env():
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_test_regen_"))
    maint_root = temp_dir / "maintenance"
    maint_root.mkdir(parents=True, exist_ok=True)
    db_path = maint_root / "recovery.sqlite3"
    service = NeuralRegenerationCapability(maint_root, db_path, SIGNING_KEY)
    yield maint_root, db_path, service
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_backup_and_restore_json(test_env):
    root, db_path, service = test_env
    src_file = root / "weights.json"
    content = {"model": "cortex", "weights": [0.1, 0.2, 0.3]}
    src_file.write_text(json.dumps(content), encoding="utf-8")

    # Backup
    backup_res = service.backup({
        "action": "backup",
        "artifact_id": "cortex_json",
        "version": 1,
        "source_path": "weights.json",
        "content_type": "JSON",
    })
    assert backup_res.code == "ENCRYPTED_RECOVERY_POINT_CREATED"
    assert backup_res.data["artifact_id"] == "cortex_json"
    assert backup_res.data["version"] == 1

    # Corrupt
    dest_file = root / "restored.json"
    dest_file.write_text('{"corrupt": true}', encoding="utf-8")

    # Restore
    restore_res = service.restore({
        "action": "restore",
        "artifact_id": "cortex_json",
        "version": 1,
        "destination_path": "restored.json",
        "corruption_signal": "CHECKSUM_MISMATCH",
    })
    assert restore_res.code == "STATE_REGENERATED"
    assert restore_res.data["canary"] == "PASSED"
    assert json.loads(dest_file.read_text(encoding="utf-8")) == content


def test_backup_and_restore_sqlite(test_env):
    root, db_path, service = test_env
    src_db = root / "weights.sqlite3"
    with sqlite3.connect(src_db) as conn:
        conn.execute("CREATE TABLE weights (k TEXT, v REAL)")
        conn.execute("INSERT INTO weights VALUES ('alpha', 0.999)")
        conn.commit()

    service.backup({
        "action": "backup",
        "artifact_id": "cortex_db",
        "version": 1,
        "source_path": "weights.sqlite3",
        "content_type": "SQLITE",
    })

    dest_db = root / "weights_live.sqlite3"
    dest_db.write_bytes(b"CORRUPTED_BYTES" * 10)

    restore_res = service.restore({
        "action": "restore",
        "artifact_id": "cortex_db",
        "version": 1,
        "destination_path": "weights_live.sqlite3",
        "corruption_signal": "CONSISTENCY_FAILURE",
    })
    assert restore_res.code == "STATE_REGENERATED"
    with sqlite3.connect(dest_db) as conn:
        row = conn.execute("SELECT v FROM weights WHERE k='alpha'").fetchone()
        assert row[0] == 0.999
        quick_check = conn.execute("PRAGMA quick_check").fetchone()[0]
        assert quick_check == "ok"


def test_damage_diagnosis_all_states(test_env):
    root, db_path, service = test_env
    file_path = root / "test_artifact.json"
    file_path.write_text('{"healthy": true}', encoding="utf-8")

    service.backup({
        "action": "backup",
        "artifact_id": "diag_test",
        "version": 1,
        "source_path": "test_artifact.json",
        "content_type": "JSON",
    })

    # Healthy
    diag_h = service.diagnose({
        "action": "diagnose",
        "artifact_id": "diag_test",
        "target_path": "test_artifact.json",
    })
    assert diag_h.data["diagnosis"] == "HEALTHY"
    assert diag_h.data["damaged"] is False

    # Checksum Mismatch
    file_path.write_text('{"tampered": true}', encoding="utf-8")
    diag_c = service.diagnose({
        "action": "diagnose",
        "artifact_id": "diag_test",
        "target_path": "test_artifact.json",
    })
    assert diag_c.data["diagnosis"] == "CHECKSUM_MISMATCH"
    assert diag_c.data["damaged"] is True

    # Missing
    file_path.unlink()
    diag_m = service.diagnose({
        "action": "diagnose",
        "artifact_id": "diag_test",
        "target_path": "test_artifact.json",
    })
    assert diag_m.data["diagnosis"] == "FILE_MISSING"
    assert diag_m.data["damaged"] is True


def test_quarantine_preserves_damaged_file_and_rollback(test_env):
    root, db_path, service = test_env
    artifact = root / "quarantine_target.json"
    artifact.write_text('{"version": "initial"}', encoding="utf-8")

    service.backup({
        "action": "backup",
        "artifact_id": "quarantine_test",
        "version": 1,
        "source_path": "quarantine_target.json",
        "content_type": "JSON",
    })

    # Damage live file
    artifact.write_text('{"version": "damaged_live"}', encoding="utf-8")

    restore_res = service.restore({
        "action": "restore",
        "artifact_id": "quarantine_test",
        "version": 1,
        "destination_path": "quarantine_target.json",
        "corruption_signal": "CHECKSUM_MISMATCH",
    })
    assert restore_res.data["previous_state_quarantined"] is True
    rec_id = restore_res.data["recovery_id"]

    quarantine_files = list((root / "quarantine").glob(f"quarantine_target.json-{rec_id}.previous"))
    assert len(quarantine_files) == 1
    assert json.loads(quarantine_files[0].read_text(encoding="utf-8")) == {"version": "damaged_live"}

    # Rollback quarantine
    rb_res = service.rollback_quarantine({
        "action": "rollback_quarantine",
        "destination_path": "quarantine_target.json",
        "recovery_id": rec_id,
    })
    assert rb_res.code == "QUARANTINE_RESTORED"
    assert json.loads(artifact.read_text(encoding="utf-8")) == {"version": "damaged_live"}


def test_tampered_envelope_fails_closed(test_env):
    root, db_path, service = test_env
    artifact = root / "tamper_source.json"
    artifact.write_text('{"clean": true}', encoding="utf-8")

    service.backup({
        "action": "backup",
        "artifact_id": "tamper_art",
        "version": 1,
        "source_path": "tamper_source.json",
        "content_type": "JSON",
    })

    envelope_path = root / "recovery-points" / "tamper_art-1.recovery.json"
    envelope_data = json.loads(envelope_path.read_text(encoding="utf-8"))
    envelope_data["envelope"]["ciphertext"] = "ZGFtYWdlZA=="
    envelope_path.write_text(json.dumps(envelope_data), encoding="utf-8")

    with pytest.raises(LocalPillarError) as exc_info:
        service.restore({
            "action": "restore",
            "artifact_id": "tamper_art",
            "version": 1,
            "destination_path": "tamper_dest.json",
            "corruption_signal": "CHECKSUM_MISMATCH",
        })
    assert exc_info.value.code in {"ARTIFACT_DECRYPTION_FAILED", "RECOVERY_POINT_CORRUPT"}


def test_concurrent_lock_enforcement(test_env):
    root, db_path, service = test_env
    artifact = root / "lock_source.json"
    artifact.write_text('{"lock": true}', encoding="utf-8")

    service.backup({
        "action": "backup",
        "artifact_id": "lock_art",
        "version": 1,
        "source_path": "lock_source.json",
        "content_type": "JSON",
    })

    # Simulate active lock
    with sqlite3.connect(db_path) as conn:
        conn.execute("INSERT INTO recovery_locks VALUES (?, ?)", ("lock_art", time.time()))
        conn.commit()

    with pytest.raises(LocalPillarError) as exc_info:
        service.restore({
            "action": "restore",
            "artifact_id": "lock_art",
            "version": 1,
            "destination_path": "lock_dest.json",
            "corruption_signal": "CHECKSUM_MISMATCH",
        })
    assert exc_info.value.code == "RECOVERY_LOCKED"


def test_path_confinement(test_env):
    root, db_path, service = test_env
    with pytest.raises(LocalPillarError) as exc_info:
        service.backup({
            "action": "backup",
            "artifact_id": "escape",
            "version": 1,
            "source_path": "../../escape.json",
            "content_type": "JSON",
        })
    assert exc_info.value.code == "PERMISSION_DENIED"


def test_metrics_and_dispatch_via_core_runtime(test_env):
    root, db_path, service = test_env
    runtime_dir = root / "runtime_dir"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    runtime = JayaCoreRuntime(
        db_path=runtime_dir / "core.sqlite3",
        local_pillar_data_dir=runtime_dir / "local-pillars",
        lineage_signing_key=SIGNING_KEY,
    )
    try:
        maint_root = runtime_dir / "local-pillars" / "maintenance" / "recovery"
        maint_root.mkdir(parents=True, exist_ok=True)
        sample = maint_root / "sample_model.json"
        sample.write_text('{"weights": [1.0, 2.0, 3.0]}', encoding="utf-8")

        res_b = runtime.execute_local_pillar(
            REGENERATION_CAPABILITY_ID,
            {
                "action": "backup",
                "artifact_id": "sample_model",
                "version": 1,
                "source_path": "sample_model.json",
                "content_type": "JSON",
            },
        )
        assert res_b.code == "ENCRYPTED_RECOVERY_POINT_CREATED"

        res_d = runtime.execute_local_pillar(
            REGENERATION_CAPABILITY_ID,
            {
                "action": "diagnose",
                "artifact_id": "sample_model",
                "target_path": "sample_model.json",
            },
        )
        assert res_d.data["diagnosis"] == "HEALTHY"

        res_m = runtime.execute_local_pillar(
            REGENERATION_CAPABILITY_ID,
            {"action": "metrics"},
        )
        assert res_m.code == "RECOVERY_METRICS_COMPUTED"
    finally:
        runtime.close()


def test_restart_durability(test_env):
    root, db_path, service = test_env
    artifact = root / "durable.json"
    artifact.write_text('{"durable": true}', encoding="utf-8")

    service.backup({
        "action": "backup",
        "artifact_id": "durable_art",
        "version": 1,
        "source_path": "durable.json",
        "content_type": "JSON",
    })

    # Create brand new capability instance pointing to same storage
    restarted = NeuralRegenerationCapability(root, db_path, SIGNING_KEY)
    assert restarted.health_check() is True
    points = restarted.list_recovery_points({}).data
    assert points["count"] >= 1
    inspect = restarted.inspect_recovery_point({
        "action": "inspect",
        "artifact_id": "durable_art",
        "version": 1,
    })
    assert inspect.data["signature_valid"] is True
