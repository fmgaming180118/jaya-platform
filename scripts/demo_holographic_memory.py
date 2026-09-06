#!/usr/bin/env python3
"""Interactive vertical slice demo for Pillar 08: Holographic Memory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.memory.episodic import EpisodicMemoryStore  # noqa: E402
from jaya_core.pillars.foundation_capabilities import (  # noqa: E402
    MEMORY_CAPABILITY_ID,
    FoundationPillarCapabilityService,
)
from jaya_core.pillars.local_capabilities import LocalPillarError  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir", default=str(ROOT / "artifacts" / "demo-holographic-memory")
    )
    args = parser.parse_args()
    data_dir = Path(args.data_dir).expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)

    db_path = data_dir / "holographic_demo.sqlite3"
    store = EpisodicMemoryStore(db_path)
    service = FoundationPillarCapabilityService(
        data_dir=data_dir / "pillars",
        episodic_memory=store,
    )

    print("=" * 75)
    print(" PILAR 08: HOLOGRAPHIC MEMORY — LIVE VERTICAL SLICE DEMO")
    print("=" * 75)
    print(f"Database: {db_path}\n")

    try:
        # Step 1: Append Episodic Events with Provenance & Multi-Indexes
        print("1. Ingesting Holographic Memory Events with Multi-Index Tagging...")
        source_digest_1 = "sha256:" + hashlib.sha256(b"quantum_exp_telemetry_dataset_v1").hexdigest()
        source_digest_2 = "sha256:" + hashlib.sha256(b"ion_trap_cooling_log_2026").hexdigest()

        events = [
            {
                "event_id": "demo-evt-001",
                "event_type": "QUANTUM_TELEMETRY",
                "session_id": "sess-quantum-lab",
                "goal_id": "goal-qubit-cooling",
                "payload": {
                    "temperature_mk": 15.2,
                    "coherence_time_us": 125.4,
                    "fidelity": 0.9992,
                },
                "sequence_number": 1,
                "provenance": {
                    "source_digest": source_digest_1,
                    "confidence": 0.995,
                    "owner_id": "alice_physicist",
                    "policy": "RESTRICTED",
                    "observed_at": time.time(),
                },
                "indexes": {
                    "semantic": ["quantum_coherence", "cryogenic_cooling"],
                    "entity": ["ion_trap_rig_01", "cryostat_alpha"],
                    "task": ["cool_to_ground_state"],
                    "procedure": ["standard_laser_cooling_v3"],
                },
            },
            {
                "event_id": "demo-evt-002",
                "event_type": "RESEARCH_HYPOTHESIS",
                "session_id": "sess-quantum-lab",
                "goal_id": "goal-error-suppression",
                "payload": {
                    "hypothesis": "Dynamical decoupling pulses increase T2 by 4x",
                    "status": "TESTING",
                },
                "sequence_number": 2,
                "provenance": {
                    "source_digest": source_digest_2,
                    "confidence": 0.88,
                    "owner_id": "alice_physicist",
                    "policy": "INTERNAL",
                    "observed_at": time.time(),
                },
                "indexes": {
                    "semantic": ["quantum_coherence", "dynamical_decoupling"],
                    "entity": ["qubit_cluster_bravo"],
                    "task": ["apply_cpmg_pulses"],
                    "procedure": ["pulse_sequence_calibration"],
                },
            },
        ]

        for ev in events:
            res = service.execute(MEMORY_CAPABILITY_ID, dict(action="append", **ev))
            print(f"   [+] Appended event: {ev['event_id']:<14} | Type: {ev['event_type']:<20} | Code: {res.code}")
        print()

        # Step 2: Multi-Index Retrieval
        print("2. Querying Multi-Index Projections with Full Provenance...")
        index_queries = [
            ("semantic", "quantum_coherence"),
            ("entity", "cryostat_alpha"),
            ("procedure", "standard_laser_cooling_v3"),
            ("session", "sess-quantum-lab"),
        ]
        for idx_type, idx_val in index_queries:
            q_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "query", "index_type": idx_type, "index_value": idx_val},
            )
            matched = q_res.data.get("events", [])
            print(f"   Query [{idx_type.upper():<9} = '{idx_val}'] -> Matched {len(matched)} event(s):")
            for m in matched:
                print(f"      - ID: {m['event_id']} | Conf: {m['provenance']['confidence']} | Owner: {m['provenance']['owner_id']} | Payload: {json.dumps(m['payload'])}")
        print()

        # Step 3: Duplicate Idempotency
        print("3. Demonstrating Strict Idempotency on Re-append...")
        dup_res = service.execute(MEMORY_CAPABILITY_ID, dict(action="append", **events[0]))
        print(f"   Re-appending {events[0]['event_id']}: Code={dup_res.code}, Inserted={dup_res.data.get('inserted')}")
        assert dup_res.code == "MEMORY_EVENT_DUPLICATE"
        assert dup_res.data.get("inserted") is False
        print("   -> Duplicate handled safely without side-effects.\n")

        # Step 4: Conflict Detection on Diverging Payload/Provenance
        print("4. Demonstrating Conflict Rejection (MEMORY_CONFLICT)...")
        tampered = dict(events[0], payload={"temperature_mk": 999.9, "fidelity": 0.1})
        try:
            service.execute(MEMORY_CAPABILITY_ID, dict(action="append", **tampered))
            print("   [!] ERROR: Tampered event unexpectedly accepted!")
        except LocalPillarError as exc:
            print(f"   Rejected conflicting event correctly with code: {exc.code} ('{exc}')")
            assert exc.code == "MEMORY_CONFLICT"
        print()

        # Step 5: Self-Healing Index Reconstruction
        print("5. Demonstrating Index Self-Healing (Index Rebuild from Canonical Records)...")
        print("   Simulating index table corruption by truncating holographic_indexes...")
        with store._get_connection() as conn:
            conn.execute("DELETE FROM holographic_indexes;")

        empty_check = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "semantic", "index_value": "quantum_coherence"},
        )
        print(f"   Query before rebuild -> Matched {len(empty_check.data.get('events', []))} events (indices missing).")

        rebuild_res = service.execute(MEMORY_CAPABILITY_ID, {"action": "rebuild_indexes"})
        print(f"   Rebuild triggered: Code={rebuild_res.code}, Rebuilt={rebuild_res.data.get('indexed_events_count')} records.")

        restored_check = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "semantic", "index_value": "quantum_coherence"},
        )
        print(f"   Query after rebuild  -> Matched {len(restored_check.data.get('events', []))} events (100% restored).")
        assert len(restored_check.data.get("events", [])) == 2
        print()

        # Step 6: Revocation & Compaction Lifecycle
        print("6. Demonstrating Revocation & Compaction Lifecycle...")
        t_now = time.time()
        rev_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "revoke", "event_id": "demo-evt-002", "reason": "superseded by rig recalibration"},
        )
        print(f"   Revoked event demo-evt-002: Code={rev_res.code}")

        # Active query omits revoked event by default
        active_q = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "semantic", "index_value": "quantum_coherence"},
        )
        print(f"   Active query (default) -> {len(active_q.data.get('events', []))} active event(s) returned.")
        assert len(active_q.data.get("events", [])) == 1

        # Audit query with include_revoked=True returns it
        audit_q = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "semantic", "index_value": "quantum_coherence", "include_revoked": True},
        )
        print(f"   Audit query (include_revoked=True) -> {len(audit_q.data.get('events', []))} total event(s) including revoked.")
        assert len(audit_q.data.get("events", [])) == 2

        # Step 7: Sovereign Privacy Deletion
        print("\n7. Demonstrating Sovereign Privacy Deletion (Right to be Forgotten)...")
        # Unauthorized attempt
        try:
            service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "delete", "event_id": "demo-evt-001", "owner_id": "unauthorized_party"},
            )
        except LocalPillarError as exc:
            print(f"   Unauthorized deletion attempt blocked: {exc.code} ('{exc}')")

        # Authorized deletion
        del_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "delete", "event_id": "demo-evt-001", "owner_id": "alice_physicist"},
        )
        print(f"   Authorized deletion by owner 'alice_physicist': Code={del_res.code}, Deleted={del_res.data.get('deleted')}")
        assert del_res.code == "MEMORY_EVENT_DELETED"
        print()

        # Step 8: Durability Across Store Restart
        print("8. Verifying Restart Durability...")
        # Append an event before closing
        service.execute(
            MEMORY_CAPABILITY_ID,
            {
                "action": "append",
                "event_id": "demo-durability-final",
                "event_type": "SYSTEM_STATE",
                "session_id": "sess-final",
                "goal_id": "goal-durability",
                "payload": {"state": "golden_checkpoint"},
                "sequence_number": 99,
                "provenance": {
                    "source_digest": source_digest_1,
                    "confidence": 1.0,
                    "owner_id": "admin",
                    "policy": "INTERNAL",
                    "observed_at": time.time(),
                },
                "indexes": {"semantic": ["golden_checkpoint"]},
            },
        )
    finally:
        store.close()

    # Reopen from disk
    reopened_store = EpisodicMemoryStore(db_path)
    reopened_service = FoundationPillarCapabilityService(
        data_dir=data_dir / "pillars",
        episodic_memory=reopened_store,
    )
    try:
        chk = reopened_service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "get_record", "event_id": "demo-durability-final"},
        )
        print(f"   Reopened SQLite database from disk: Record read -> ID={chk.data['record']['event']['event_id']}, State={chk.data['record']['event']['payload']['state']}")
        assert chk.data["record"]["event"]["event_id"] == "demo-durability-final"
        print("   -> 100% Data durability across process restart verified successfully!")
    finally:
        reopened_store.close()

    print("\n" + "=" * 75)
    print(" PILAR 08: HOLOGRAPHIC MEMORY — DEMO COMPLETED SUCCESSFULLY")
    print("=" * 75)
    return 0


if __name__ == "__main__":
    sys.exit(main())
