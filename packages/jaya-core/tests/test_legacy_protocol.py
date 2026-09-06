"""Unit and integration tests for Pillar 19 Legacy Protocol."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import tempfile
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.maintenance_capabilities import (
    LEGACY_CAPABILITY_ID,
    LegacyProtocolCapability,
)

SIGNING_KEY = bytes(range(32))


def _sign(key: bytes, material: bytes) -> str:
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _digest_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


@pytest.fixture
def test_env():
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_test_legacy_"))
    legacy_root = temp_dir / "legacy_store"
    legacy_root.mkdir(parents=True, exist_ok=True)
    db_path = legacy_root / "migration.sqlite3"

    service = LegacyProtocolCapability(legacy_root, db_path, SIGNING_KEY)
    yield legacy_root, db_path, service
    shutil.rmtree(temp_dir, ignore_errors=True)


def _make_legacy_fixture(brain_id: str = "brain-test-01", memory_items: int = 2) -> tuple[dict, bytes]:
    payload = {
        "schema_version": 1,
        "brain_id": brain_id,
        "identity": {"owner_id": "test-owner", "system": "alpha"},
        "memory": [{"item": f"mem_{i}", "val": i * 10} for i in range(memory_items)],
        "policy": {"strict": True, "level": 1},
    }
    raw = LegacyProtocolCapability.LEGACY_MAGIC + json.dumps(payload).encode("utf-8")
    return payload, raw


def test_legacy_full_lifecycle(test_env):
    root, db_path, service = test_env
    payload, raw = _make_legacy_fixture("brain-lifecycle-01", 3)
    (root / "source.bin").write_bytes(raw)
    src_digest = _digest_bytes(raw)

    # 1. Check compatibility
    compat = service.check_compatibility({"action": "check_compatibility", "source_path": "source.bin"})
    assert compat.code == "LEGACY_COMPATIBILITY_CHECKED"
    assert compat.data["compatible"] is True
    assert compat.data["already_migrated"] is False
    assert compat.data["brain_id"] == "brain-lifecycle-01"
    assert compat.data["memory_items_count"] == 3

    # 2. Migrate
    mat = f"migrate|{src_digest}|output.jaya|app-1|test-owner".encode()
    migrated = service.migrate({
        "action": "migrate",
        "source_path": "source.bin",
        "output_path": "output.jaya",
        "owner_id": "test-owner",
        "approval_id": "app-1",
        "signature": _sign(SIGNING_KEY, mat),
    })
    assert migrated.code == "LEGACY_CAPSULE_MIGRATED"
    migration_id = migrated.data["migration_id"]
    output_digest = migrated.data["output_digest"]

    # Verify backup exists and decrypts to original bytes
    backup_file = root / migrated.data["backup_path"]
    assert backup_file.is_file()
    backup_wrapper = json.loads(backup_file.read_bytes())
    decrypted_backup = service.decrypt(backup_wrapper, f"legacy-backup|{migration_id}".encode())
    assert decrypted_backup == raw

    # 3. Inspect capsule
    inspected = service.inspect({"action": "inspect", "path": "output.jaya"})
    assert inspected.code == "CURRENT_CAPSULE_VERIFIED"
    assert inspected.data["brain_id"] == "brain-lifecycle-01"
    assert inspected.data["migration_id"] == migration_id

    # 4. Check compatibility now shows already migrated
    compat2 = service.check_compatibility({"action": "check_compatibility", "source_path": "source.bin"})
    assert compat2.data["compatible"] is False
    assert compat2.data["already_migrated"] is True
    assert compat2.data["migration_id"] == migration_id

    # 5. List and inspect migration record
    listed = service.list_migrations()
    assert listed.data["count"] == 1
    rec = service.inspect_migration({"action": "inspect_migration", "migration_id": migration_id})
    assert rec.data["record"]["status"] == "MIGRATED"
    assert rec.data["output_exists"] is True

    # 6. Rollback
    rb_mat = f"rollback_migration|{migration_id}|{output_digest}|rb-1|test-owner".encode()
    rolled_back = service.rollback({
        "action": "rollback",
        "migration_id": migration_id,
        "rollback_id": "rb-1",
        "owner_id": "test-owner",
        "signature": _sign(SIGNING_KEY, rb_mat),
    })
    assert rolled_back.code == "LEGACY_MIGRATION_ROLLED_BACK"

    # Destination file moved to quarantine
    assert not (root / "output.jaya").exists()
    quarantine_files = list((root / "migration-quarantine").glob(f"{migration_id}-*.jaya"))
    assert len(quarantine_files) == 1

    # Subsequent inspect fails
    with pytest.raises(LocalPillarError):
        service.inspect({"action": "inspect", "path": "output.jaya"})


def test_reject_unsupported_version_and_magic(test_env):
    root, db_path, service = test_env

    # Wrong magic
    (root / "bad_magic.bin").write_bytes(b"JAYA_V0\n{}")
    with pytest.raises(LocalPillarError) as exc_info:
        service.check_compatibility({"action": "check_compatibility", "source_path": "bad_magic.bin"})
    assert exc_info.value.code == "LEGACY_VERSION_UNSUPPORTED"

    # Wrong schema version
    payload, _ = _make_legacy_fixture()
    payload["schema_version"] = 2
    (root / "bad_version.bin").write_bytes(LegacyProtocolCapability.LEGACY_MAGIC + json.dumps(payload).encode())
    with pytest.raises(LocalPillarError) as exc_info:
        service.check_compatibility({"action": "check_compatibility", "source_path": "bad_version.bin"})
    assert exc_info.value.code == "LEGACY_LAYOUT_UNSUPPORTED"


def test_reject_truncated_and_malformed_json(test_env):
    root, db_path, service = test_env
    (root / "trunc.bin").write_bytes(LegacyProtocolCapability.LEGACY_MAGIC + b'{"schema_version": 1, "brain_id"')
    with pytest.raises(LocalPillarError) as exc_info:
        service.check_compatibility({"action": "check_compatibility", "source_path": "trunc.bin"})
    assert exc_info.value.code == "LEGACY_TRUNCATED"


def test_reject_oversized_payload(test_env):
    root, db_path, service = test_env
    (root / "huge.bin").write_bytes(LegacyProtocolCapability.LEGACY_MAGIC + b"X" * (10 * 1024 * 1024 + 1))
    with pytest.raises(LocalPillarError) as exc_info:
        service.check_compatibility({"action": "check_compatibility", "source_path": "huge.bin"})
    assert exc_info.value.code == "INPUT_TOO_LARGE"

    with pytest.raises(LocalPillarError) as exc_info2:
        service.migrate({
            "action": "migrate",
            "source_path": "huge.bin",
            "output_path": "out.jaya",
            "owner_id": "owner",
            "approval_id": "app",
            "signature": "0" * 64,
        })
    assert exc_info2.value.code == "INPUT_TOO_LARGE"


def test_reject_tampered_signature(test_env):
    root, db_path, service = test_env
    _, raw = _make_legacy_fixture()
    (root / "src.bin").write_bytes(raw)

    with pytest.raises(LocalPillarError) as exc_info:
        service.migrate({
            "action": "migrate",
            "source_path": "src.bin",
            "output_path": "out.jaya",
            "owner_id": "test-owner",
            "approval_id": "app-1",
            "signature": "0" * 64,
        })
    assert exc_info.value.code == "SIGNATURE_INVALID"


def test_reject_destination_exists(test_env):
    root, db_path, service = test_env
    _, raw = _make_legacy_fixture()
    (root / "src.bin").write_bytes(raw)
    (root / "existing.jaya").write_text("exists")

    with pytest.raises(LocalPillarError) as exc_info:
        service.migrate({
            "action": "migrate",
            "source_path": "src.bin",
            "output_path": "existing.jaya",
            "owner_id": "test-owner",
            "approval_id": "app-1",
            "signature": "0" * 64,
        })
    assert exc_info.value.code == "DESTINATION_EXISTS"


def test_reject_duplicate_migration(test_env):
    root, db_path, service = test_env
    _, raw = _make_legacy_fixture()
    (root / "src.bin").write_bytes(raw)
    src_digest = _digest_bytes(raw)

    service.migrate({
        "action": "migrate",
        "source_path": "src.bin",
        "output_path": "out1.jaya",
        "owner_id": "test-owner",
        "approval_id": "app-1",
        "signature": _sign(SIGNING_KEY, f"migrate|{src_digest}|out1.jaya|app-1|test-owner".encode()),
    })

    with pytest.raises(LocalPillarError) as exc_info:
        service.migrate({
            "action": "migrate",
            "source_path": "src.bin",
            "output_path": "out2.jaya",
            "owner_id": "test-owner",
            "approval_id": "app-2",
            "signature": _sign(SIGNING_KEY, f"migrate|{src_digest}|out2.jaya|app-2|test-owner".encode()),
        })
    assert exc_info.value.code == "MIGRATION_DUPLICATE"


def test_reject_unauthorized_rollback(test_env):
    root, db_path, service = test_env
    _, raw = _make_legacy_fixture()
    (root / "src.bin").write_bytes(raw)
    src_digest = _digest_bytes(raw)

    mig = service.migrate({
        "action": "migrate",
        "source_path": "src.bin",
        "output_path": "out.jaya",
        "owner_id": "legit-owner",
        "approval_id": "app-1",
        "signature": _sign(SIGNING_KEY, f"migrate|{src_digest}|out.jaya|app-1|legit-owner".encode()),
    })

    # Wrong owner
    with pytest.raises(LocalPillarError) as exc_info:
        service.rollback({
            "action": "rollback",
            "migration_id": mig.data["migration_id"],
            "rollback_id": "rb-1",
            "owner_id": "impostor",
            "signature": "0" * 64,
        })
    assert exc_info.value.code == "APPROVAL_DENIED"

    # Wrong signature
    with pytest.raises(LocalPillarError) as exc_info2:
        service.rollback({
            "action": "rollback",
            "migration_id": mig.data["migration_id"],
            "rollback_id": "rb-1",
            "owner_id": "legit-owner",
            "signature": "0" * 64,
        })
    assert exc_info2.value.code == "SIGNATURE_INVALID"


def test_restart_durability(test_env):
    root, db_path, service = test_env
    _, raw = _make_legacy_fixture()
    (root / "src.bin").write_bytes(raw)
    src_digest = _digest_bytes(raw)

    mig = service.migrate({
        "action": "migrate",
        "source_path": "src.bin",
        "output_path": "durable.jaya",
        "owner_id": "owner",
        "approval_id": "app",
        "signature": _sign(SIGNING_KEY, f"migrate|{src_digest}|durable.jaya|app|owner".encode()),
    })

    # Restart
    restarted = LegacyProtocolCapability(root, db_path, SIGNING_KEY)
    assert restarted.health_check() is True
    rec = restarted.inspect_migration({"action": "inspect_migration", "migration_id": mig.data["migration_id"]})
    assert rec.data["record"]["status"] == "MIGRATED"
    assert rec.data["output_exists"] is True


def test_core_runtime_dispatch(test_env):
    root, db_path, service = test_env
    runtime_dir = root / "runtime_store"
    runtime_dir.mkdir(parents=True, exist_ok=True)

    runtime = JayaCoreRuntime(
        db_path=runtime_dir / "core.sqlite3",
        local_pillar_data_dir=runtime_dir / "pillars",
        lineage_signing_key=SIGNING_KEY,
    )
    try:
        legacy_dir = runtime_dir / "pillars" / "maintenance" / "migration"
        legacy_dir.mkdir(parents=True, exist_ok=True)
        _, raw = _make_legacy_fixture("brain-runtime-01")
        (legacy_dir / "runtime_src.bin").write_bytes(raw)
        src_digest = _digest_bytes(raw)

        # Check compat via runtime
        compat = runtime.execute_local_pillar(
            LEGACY_CAPABILITY_ID,
            {"action": "check_compatibility", "source_path": "runtime_src.bin"},
        )
        assert compat.code == "LEGACY_COMPATIBILITY_CHECKED"

        # Migrate via runtime
        mat = f"migrate|{src_digest}|runtime_out.jaya|rt-app|rt-owner".encode()
        mig = runtime.execute_local_pillar(
            LEGACY_CAPABILITY_ID,
            {
                "action": "migrate",
                "source_path": "runtime_src.bin",
                "output_path": "runtime_out.jaya",
                "owner_id": "rt-owner",
                "approval_id": "rt-app",
                "signature": _sign(SIGNING_KEY, mat),
            },
        )
        assert mig.code == "LEGACY_CAPSULE_MIGRATED"

        # Inspect via runtime
        insp = runtime.execute_local_pillar(
            LEGACY_CAPABILITY_ID,
            {"action": "inspect", "path": "runtime_out.jaya"},
        )
        assert insp.code == "CURRENT_CAPSULE_VERIFIED"
        assert insp.data["brain_id"] == "brain-runtime-01"
    finally:
        runtime.close()
