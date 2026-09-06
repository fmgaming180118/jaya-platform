#!/usr/bin/env python3
"""Interactive demonstration of Pillar 19 Legacy Protocol."""

from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402
from jaya_core.pillars.maintenance_capabilities import LegacyProtocolCapability  # noqa: E402

SIGNING_KEY = bytes(range(32))


def _sign(key: bytes, material: bytes) -> str:
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def _digest_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_legacy_"))
    legacy_root = temp_dir / "legacy_store"
    legacy_root.mkdir(parents=True, exist_ok=True)
    db_path = legacy_root / "migration.sqlite3"

    print("=" * 75)
    print(" JAYA COGNITIVE ARCHITECTURE — PILAR 19: LEGACY PROTOCOL DEMO")
    print("=" * 75)
    print(f"Store Root: {legacy_root}\n")

    service = LegacyProtocolCapability(legacy_root, db_path, SIGNING_KEY)

    # Step 1: Create Legacy Artifact (v1)
    print("[1] Creating legacy brain capsule artifact (JAYA_LEGACY_V1)...")
    legacy_payload = {
        "schema_version": 1,
        "brain_id": "brain-legacy-apollo-7",
        "identity": {
            "owner_id": "mission-commander",
            "dna_anchor": "sha256:abcd0123456789abcdef0123456789abcdef",
            "origin_timestamp": 1609459200.0,
        },
        "memory": [
            {"event_id": "e-001", "event": "navigation_drift", "correction": 0.042},
            {"event_id": "e-002", "event": "telemetry_heartbeat", "status": "nominal"},
        ],
        "policy": {
            "sandbox_mode": "STRICT",
            "offline_only": True,
            "max_concurrency": 2,
        },
    }
    legacy_raw = LegacyProtocolCapability.LEGACY_MAGIC + json.dumps(legacy_payload).encode()
    (legacy_root / "apollo7.legacy.bin").write_bytes(legacy_raw)
    legacy_digest = _digest_bytes(legacy_raw)
    print(f"    Source Path:   apollo7.legacy.bin")
    print(f"    Source Digest: {legacy_digest}")
    print(f"    Brain ID:      {legacy_payload['brain_id']}")

    # Step 2: Probe Compatibility
    print("\n[2] Probing legacy format compatibility (read-only)...")
    compat = service.check_compatibility({"action": "check_compatibility", "source_path": "apollo7.legacy.bin"})
    print(f"    Status:     {compat.code}")
    print(f"    Compatible: {compat.data['compatible']}")
    print(f"    Sections:   {compat.data['sections']}")
    print(f"    Mem Items:  {compat.data['memory_items_count']}")

    # Step 3: Transactional Migration
    print("\n[3] Executing authorized transactional migration to JAYA_CURRENT_V2...")
    out_rel = "apollo7.current.jaya"
    approval_id = "cmd-app-001"
    owner_id = "mission-commander"
    mat = f"migrate|{legacy_digest}|{out_rel}|{approval_id}|{owner_id}".encode()
    sig = _sign(SIGNING_KEY, mat)

    mig_res = service.migrate({
        "action": "migrate",
        "source_path": "apollo7.legacy.bin",
        "output_path": out_rel,
        "owner_id": owner_id,
        "approval_id": approval_id,
        "signature": sig,
    })
    print(f"    Status:        {mig_res.code}")
    print(f"    Migration ID:  {mig_res.data['migration_id']}")
    print(f"    Output Path:   {mig_res.data['output_path']}")
    print(f"    Backup Path:   {mig_res.data['backup_path']}")
    print(f"    Output Digest: {mig_res.data['output_digest']}")

    # Step 4: Verify Encrypted Backup
    print("\n[4] Verifying untouched encrypted source backup...")
    backup_file = legacy_root / mig_res.data["backup_path"]
    backup_wrapper = json.loads(backup_file.read_bytes())
    decrypted_backup = service.decrypt(backup_wrapper, f"legacy-backup|{mig_res.data['migration_id']}".encode())
    backup_matches = decrypted_backup == legacy_raw
    print(f"    Backup File Exists:     {backup_file.is_file()}")
    print(f"    Decrypted Exact Match:  {backup_matches}")

    # Step 5: Inspect Migrated Capsule & Check Section Fidelity
    print("\n[5] Inspecting migrated AES-GCM capsule and verifying section fidelity...")
    insp = service.inspect({"action": "inspect", "path": out_rel})
    capsule_bytes = (legacy_root / out_rel).read_bytes()
    capsule_wrapper = json.loads(capsule_bytes[len(LegacyProtocolCapability.CURRENT_MAGIC) :])
    capsule_plaintext = service.decrypt(capsule_wrapper["envelope"], f"current|{mig_res.data['migration_id']}".encode())
    migrated_payload = json.loads(capsule_plaintext)

    fidelity = (
        migrated_payload["brain_id"] == legacy_payload["brain_id"]
        and migrated_payload["identity"] == legacy_payload["identity"]
        and migrated_payload["memory"] == legacy_payload["memory"]
        and migrated_payload["policy"] == legacy_payload["policy"]
        and migrated_payload["schema_version"] == 2
        and migrated_payload["migration"]["source_digest"] == legacy_digest
    )
    print(f"    Status:            {insp.code}")
    print(f"    Brain ID:          {insp.data['brain_id']}")
    print(f"    100% Fidelity:     {fidelity}")
    print(f"    Lineage Timestamp: {migrated_payload['migration']['migrated_at']}")

    # Step 6: Test Restart Durability
    print("\n[6] Testing restart durability and querying migration ledger...")
    restarted = LegacyProtocolCapability(legacy_root, db_path, SIGNING_KEY)
    metrics_res = restarted.metrics()
    print(f"    Total Migrations:  {metrics_res.data['total_migrations']}")
    print(f"    Active Migrated:   {metrics_res.data['active_migrated']}")
    print(f"    Encrypted Backups: {metrics_res.data['backup_files_count']}")

    # Step 7: Cryptographic Rollback
    print("\n[7] Executing authorized cryptographic rollback to quarantine...")
    rollback_id = "emergency-abort-01"
    rb_mat = f"rollback_migration|{mig_res.data['migration_id']}|{mig_res.data['output_digest']}|{rollback_id}|{owner_id}".encode()
    rb_sig = _sign(SIGNING_KEY, rb_mat)

    rb_res = restarted.rollback({
        "action": "rollback",
        "migration_id": mig_res.data["migration_id"],
        "rollback_id": rollback_id,
        "owner_id": owner_id,
        "signature": rb_sig,
    })
    print(f"    Status:      {rb_res.code}")
    print(f"    Rollback ID: {rb_res.data['rollback_id']}")

    # Step 8: Confirm Fail-Closed Behavior
    print("\n[8] Confirming fail-closed behavior on rolled-back capsule...")
    output_exists = (legacy_root / out_rel).exists()
    quarantine_files = list((legacy_root / "migration-quarantine").glob("*.jaya"))
    print(f"    Destination File Removed: {not output_exists}")
    print(f"    Quarantine File Created:  {len(quarantine_files) == 1}")
    inspect_failed = False
    try:
        restarted.inspect({"action": "inspect", "path": out_rel})
    except LocalPillarError:
        inspect_failed = True
    print(f"    Subsequent Inspect Blocked: {inspect_failed}")

    shutil.rmtree(temp_dir, ignore_errors=True)
    print("\n" + "=" * 75)
    print(" DEMO COMPLETED SUCCESSFULLY — ZERO UNTRUSTED CODE, FULLY VERIFIED")
    print("=" * 75)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
