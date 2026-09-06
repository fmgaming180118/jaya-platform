#!/usr/bin/env python3
"""Interactive demonstration of Pillar 09 Neural Regeneration lifecycle."""

from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.maintenance_capabilities import NeuralRegenerationCapability

SIGNING_KEY = bytes(range(32))


def _digest_bytes(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_regeneration_"))
    maint_root = temp_dir / "maintenance"
    maint_root.mkdir(parents=True, exist_ok=True)
    db_path = maint_root / "recovery.sqlite3"

    print("=" * 75)
    print(" JAYA COGNITIVE ARCHITECTURE — PILAR 09: NEURAL REGENERATION DEMO")
    print("=" * 75)
    print(f"Maintenance Root: {maint_root}\n")

    service = NeuralRegenerationCapability(maint_root, db_path, SIGNING_KEY)

    # Step 1: Create active neural state
    print("[1] Creating active operational neural artifact (cortex_weights.json)...")
    cortex_file = maint_root / "cortex_weights.json"
    initial_weights = {
        "model_id": "cortex-morphic-v2",
        "synaptic_density": 0.892,
        "layers": [
            {"name": "sensory_input", "weights": [0.45, -0.12, 0.78, 0.91]},
            {"name": "recurrent_core", "weights": [0.33, 0.67, -0.89, 0.14]},
            {"name": "action_policy", "weights": [-0.55, 0.82, 0.11, -0.09]},
        ],
    }
    cortex_file.write_text(json.dumps(initial_weights, indent=2), encoding="utf-8")
    initial_digest = _digest_bytes(cortex_file.read_bytes())
    print(f"    Artifact digest: {initial_digest}")

    # Step 2: Encrypted backup
    print("\n[2] Creating encrypted recovery point (AES-GCM-256 + HMAC-SHA256 manifest)...")
    backup_res = service.backup({
        "action": "backup",
        "artifact_id": "cortex-weights-prod",
        "version": 1,
        "source_path": "cortex_weights.json",
        "content_type": "JSON",
    })
    print(f"    Status:           {backup_res.code}")
    print(f"    Artifact ID:      {backup_res.data['artifact_id']}")
    print(f"    Version:          {backup_res.data['version']}")
    print(f"    Plaintext Digest: {backup_res.data['plaintext_digest']}")
    print(f"    Signature:        {backup_res.data['signature'][:32]}...")

    # Step 3: Run diagnosis on intact state
    print("\n[3] Running damage diagnosis on healthy state...")
    diag_healthy = service.diagnose({
        "action": "diagnose",
        "artifact_id": "cortex-weights-prod",
        "target_path": "cortex_weights.json",
    })
    print(f"    Diagnosis: {diag_healthy.data['diagnosis']} (Damaged: {diag_healthy.data['damaged']})")
    assert diag_healthy.data["diagnosis"] == "HEALTHY"

    # Step 4: Damage injection / corruption
    print("\n[4] Simulating hostile corruption / bit-rot on live cortex state...")
    corrupted_content = {
        "model_id": "cortex-morphic-v2",
        "synaptic_density": 0.0,
        "layers": "MALICIOUS_OVERWRITE_PAYLOAD_CORRUPTED",
    }
    cortex_file.write_text(json.dumps(corrupted_content), encoding="utf-8")
    corrupt_digest = _digest_bytes(cortex_file.read_bytes())
    print(f"    Corrupted digest: {corrupt_digest}")

    # Step 5: Diagnosis detects corruption
    print("\n[5] Running damage diagnosis on corrupted state...")
    diag_corrupt = service.diagnose({
        "action": "diagnose",
        "artifact_id": "cortex-weights-prod",
        "target_path": "cortex_weights.json",
    })
    print(f"    Diagnosis:          {diag_corrupt.data['diagnosis']}")
    print(f"    Damaged:            {diag_corrupt.data['damaged']}")
    print(f"    Recommended Action: {diag_corrupt.data['recommended_action']}")
    assert diag_corrupt.data["diagnosis"] == "CHECKSUM_MISMATCH"

    # Step 6: Atomic restoration with quarantine
    print("\n[6] Executing atomic state restoration with automatic quarantine...")
    restore_res = service.restore({
        "action": "restore",
        "artifact_id": "cortex-weights-prod",
        "version": 1,
        "destination_path": "cortex_weights.json",
        "corruption_signal": "CHECKSUM_MISMATCH",
    })
    restored_bytes = cortex_file.read_bytes()
    restored_digest = _digest_bytes(restored_bytes)
    print(f"    Status:                {restore_res.code}")
    print(f"    Recovery ID:           {restore_res.data['recovery_id']}")
    print(f"    Restored Digest:       {restored_digest}")
    print(f"    Canary Verification:   {restore_res.data['canary']}")
    print(f"    Duration:              {restore_res.data['duration_ns'] / 1_000_000:.3f} ms")
    print(f"    Quarantined Old State: {restore_res.data['previous_state_quarantined']}")
    assert restored_digest == initial_digest

    quarantine_files = list((maint_root / "quarantine").glob("*.previous"))
    print(f"    Quarantine entries preserved: {len(quarantine_files)}")

    # Step 7: Post-recovery health and metrics
    print("\n[7] Verifying recovery ledger metrics and post-restore health...")
    metrics_res = service.metrics()
    print(f"    Total Recoveries:      {metrics_res.data['total_recoveries']}")
    print(f"    Successful:            {metrics_res.data['successful_recoveries']}")
    print(f"    Success Rate:          {metrics_res.data['success_rate'] * 100:.1f}%")
    print(f"    Mean Observed RTO:     {metrics_res.data['mean_rto_ms']:.3f} ms")

    # Step 8: Durability across restart
    print("\n[8] Probing restart durability with new capability instance...")
    restarted = NeuralRegenerationCapability(maint_root, db_path, SIGNING_KEY)
    points = restarted.list_recovery_points({}).data
    print(f"    Restarted health:      {'HEALTHY' if restarted.health_check() else 'UNHEALTHY'}")
    print(f"    Recovery points count: {points['count']}")

    print("\n" + "=" * 75)
    print(" DEMO COMPLETED SUCCESSFULLY — ZERO DATA LOSS, CRYPTOGRAPHICALLY VERIFIED")
    print("=" * 75)

    shutil.rmtree(temp_dir, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
