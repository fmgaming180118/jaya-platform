#!/usr/bin/env python3
"""Interactive demonstration of Pillar 25 Digital Epigenetics lifecycle."""

from __future__ import annotations

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

from jaya_core.pillars.local_capabilities import (
    DigitalEpigeneticsService,
    LocalPillarError,
)

SIGNING_KEY = bytes(range(32))


def main() -> int:
    temp_dir = Path(tempfile.mkdtemp(prefix="jaya_demo_epigenetics_"))
    db_path = temp_dir / "lineage_demo.sqlite3"
    print("=" * 70)
    print(" JAYA COGNITIVE ARCHITECTURE — PILAR 25: DIGITAL EPIGENETICS DEMO")
    print("=" * 70)
    print(f"Database: {db_path}\n")

    service = DigitalEpigeneticsService(db_path, SIGNING_KEY)

    # Step 1: Baseline inspection
    print("[1] Inspecting initial active state...")
    init_active = service.get_active_state().data
    print(f"    Initial generation: {init_active['generation_id']} (traits: {init_active['traits']})")
    assert init_active["generation_id"] is None

    # Step 2: Generation 1 — Runtime Tuning
    print("\n[2] Applying Generation 1 (runtime tuning: batch_size=32, cache=4096MB)...")
    gen1 = service.append(
        generation_id="gen-001-tuning",
        payload={"batch_size": 32, "cache_limit_mb": 4096, "temperature": 0.7},
        evidence_refs=["artifact:benchmarks/tuning_v1.json"],
        approval_ref="approval:sysadmin-alice",
        policy_decision={"evaluator": "EthicalHeart", "action": "ALLOW"},
        signer_id="operator:alice",
    )
    print(f"    Entry Sequence: {gen1.data['sequence']}")
    print(f"    Entry Digest:   {gen1.data['entry_digest']}")
    print(f"    Parent Digest:  {gen1.data['parent_digest']}")

    active1 = service.get_active_state().data
    print(f"    Active State:   {active1['generation_id']} -> {active1['traits']}")
    assert active1["generation_id"] == "gen-001-tuning"

    # Step 3: Generation 2 — Higher Concurrency & Cache
    print("\n[3] Applying Generation 2 (high throughput: batch_size=64, cache=8192MB)...")
    gen2 = service.append(
        generation_id="gen-002-highperf",
        payload={"batch_size": 64, "cache_limit_mb": 8192, "temperature": 1.0},
        evidence_refs=["artifact:benchmarks/tuning_v2.json"],
        approval_ref="approval:sysadmin-alice",
        expected_parent_generation_id="gen-001-tuning",
        expected_parent_digest=gen1.data["entry_digest"],
        signer_id="operator:alice",
    )
    print(f"    Entry Sequence: {gen2.data['sequence']}")
    print(f"    Entry Digest:   {gen2.data['entry_digest']}")
    print(f"    Parent Digest:  {gen2.data['parent_digest']}")

    active2 = service.get_active_state().data
    print(f"    Active State:   {active2['generation_id']} -> {active2['traits']}")
    assert active2["generation_id"] == "gen-002-highperf"

    # Step 4: Defense against Immutable Field Tamper
    print("\n[4] Testing protection of immutable identity fields (attempting to mutate brain_id)...")
    try:
        service.append(
            generation_id="gen-malicious",
            payload={"brain_id": "forged-id-999"},
            evidence_refs=["artifact:untrusted"],
            approval_ref="approval:unknown",
        )
        print("    ERROR: Failed to block immutable field mutation!")
        return 1
    except LocalPillarError as exc:
        print(f"    SUCCESS: Blocked immutable field mutation! Error: [{exc.code}] {exc}")
        assert exc.code == "IMMUTABLE_FIELD_VIOLATION"

    # Step 5: Defense against Stale / Fork Conflict
    print("\n[5] Testing defense against stale mutation (expected parent gen-001 when head is gen-002)...")
    try:
        service.append(
            generation_id="gen-conflict",
            payload={"batch_size": 16},
            evidence_refs=["artifact:test"],
            approval_ref="approval:alice",
            expected_parent_generation_id="gen-001-tuning",
        )
        print("    ERROR: Failed to reject stale mutation!")
        return 1
    except LocalPillarError as exc:
        print(f"    SUCCESS: Blocked stale mutation! Error: [{exc.code}] {exc}")
        assert exc.code == "STALE_MUTATION"

    # Step 6: Transactional Rollback to Gen-1
    print("\n[6] Executing transactional rollback to Generation 1...")
    rb = service.rollback(
        target_generation_id="gen-001-tuning",
        approval_ref="approval:rollback-incident-42",
        generation_id="rollback-to-gen-001",
    )
    print(f"    Rollback Sequence: {rb.data['sequence']}")
    print(f"    Rollback Target:   {rb.data['rollback_target']}")
    print(f"    Restored Traits:   {rb.data['restored_traits']}")

    active_rb = service.get_active_state().data
    print(f"    Active State now:  {active_rb['generation_id']} -> {active_rb['traits']}")
    assert active_rb["traits"]["batch_size"] == 32
    assert active_rb["traits"]["cache_limit_mb"] == 4096

    # Step 7: Restart Durability & Verification
    print("\n[7] Simulating runtime restart and verifying full cryptographic hash-chain...")
    restarted = DigitalEpigeneticsService(db_path, SIGNING_KEY)
    verified = restarted.verify()
    print(f"    Verification Result: {verified.code}")
    print(f"    Total Ledger Entries: {verified.data['entries']}")
    print(f"    Head Digest: {verified.data['head_digest']}")
    assert verified.code == "LINEAGE_VERIFIED"
    assert verified.data["entries"] == 3

    # Step 8: Tamper Detection
    print("\n[8] Testing cryptographic tamper detection on database row...")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "UPDATE epigenetic_lineage SET payload_json = ? WHERE generation_id = 'gen-001-tuning'",
            ('{"batch_size":999}',),
        )
    try:
        restarted.verify()
        print("    ERROR: Tamper was not detected!")
        return 1
    except LocalPillarError as exc:
        print(f"    SUCCESS: Tamper detected! Error: [{exc.code}] {exc}")
        assert exc.code == "LINEAGE_SIGNATURE_INVALID"

    shutil.rmtree(temp_dir, ignore_errors=True)
    print("\n" + "=" * 70)
    print(" DEMO COMPLETED SUCCESSFULLY: ALL EPIGENETIC INVARIANTS VERIFIED")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
