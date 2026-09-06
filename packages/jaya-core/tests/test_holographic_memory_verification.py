"""Verification tests for Pilar 08: Holographic Memory."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from jaya_core.memory.episodic import EpisodicMemoryStore
from jaya_core.memory.events import MemoryEvent
from jaya_core.pillars.foundation_capabilities import (
    MEMORY_CAPABILITY_ID,
    FoundationPillarCapabilityService,
)
from jaya_core.pillars.local_capabilities import LocalPillarError


def _valid_provenance(owner_id: str = "agent-node-01") -> dict[str, object]:
    return {
        "source_digest": "sha256:" + "a" * 64,
        "confidence": 0.95,
        "owner_id": owner_id,
        "policy": "INTERNAL",
        "observed_at": time.time(),
    }


def _valid_indexes() -> dict[str, list[str]]:
    return {
        "semantic": ["quantum_coherence", "qubit_stability"],
        "entity": ["lab_sensor_42", "node_alpha"],
        "task": ["calibrate_qubits"],
        "procedure": ["standard_telemetry_v1"],
    }


def test_holographic_store_append_and_multi_index_retrieval(tmp_path: Path) -> None:
    db_file = tmp_path / "holo_test.sqlite3"
    store = EpisodicMemoryStore(db_file)
    service = FoundationPillarCapabilityService(
        data_dir=tmp_path / "pillars",
        episodic_memory=store,
    )
    try:
        req = {
            "action": "append",
            "event_id": "holo-evt-001",
            "event_type": "QUANTUM_TELEMETRY",
            "session_id": "sess-quantum-1",
            "goal_id": "goal-calibration-1",
            "payload": {"decoherence_rate_ms": 12.4, "fidelity": 0.998},
            "sequence_number": 1,
            "provenance": _valid_provenance(),
            "indexes": _valid_indexes(),
        }
        res = service.execute(MEMORY_CAPABILITY_ID, req)
        assert res.code == "MEMORY_EVENT_APPENDED"
        assert res.data["inserted"] is True

        # Query by each index type
        for idx_type, idx_val in [
            ("session", "sess-quantum-1"),
            ("goal", "goal-calibration-1"),
            ("event_type", "quantum_telemetry"),
            ("semantic", "quantum_coherence"),
            ("entity", "lab_sensor_42"),
            ("task", "calibrate_qubits"),
            ("procedure", "standard_telemetry_v1"),
        ]:
            q_res = service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "query", "index_type": idx_type, "index_value": idx_val},
            )
            assert q_res.code == "MEMORY_EVENTS_READ"
            events = q_res.data["events"]
            assert len(events) == 1
            assert events[0]["event_id"] == "holo-evt-001"
            assert events[0]["payload"]["fidelity"] == 0.998
            assert events[0]["provenance"]["confidence"] == 0.95

        # Query get_record
        rec_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "get_record", "event_id": "holo-evt-001"},
        )
        assert rec_res.code == "MEMORY_RECORD_READ"
        rec = rec_res.data["record"]
        assert rec["event"]["event_id"] == "holo-evt-001"
        assert "quantum_coherence" in rec["indexes"]["semantic"]
    finally:
        store.close()


def test_holographic_duplicate_and_conflict_rejection(tmp_path: Path) -> None:
    db_file = tmp_path / "holo_conflict.sqlite3"
    store = EpisodicMemoryStore(db_file)
    service = FoundationPillarCapabilityService(
        data_dir=tmp_path / "pillars",
        episodic_memory=store,
    )
    try:
        prov = _valid_provenance()
        idxs = _valid_indexes()
        req = {
            "action": "append",
            "event_id": "holo-conflict-01",
            "event_type": "METRIC_RECORD",
            "session_id": "sess-conf-1",
            "goal_id": "goal-conf-1",
            "payload": {"value": 42},
            "sequence_number": 1,
            "provenance": prov,
            "indexes": idxs,
        }
        res1 = service.execute(MEMORY_CAPABILITY_ID, req)
        assert res1.code == "MEMORY_EVENT_APPENDED"

        # Exact duplicate is idempotent
        res2 = service.execute(MEMORY_CAPABILITY_ID, req)
        assert res2.code == "MEMORY_EVENT_DUPLICATE"
        assert res2.data["inserted"] is False

        # Conflicting payload
        req_bad_payload = dict(req)
        req_bad_payload["payload"] = {"value": 999}
        with pytest.raises(LocalPillarError) as exc_p:
            service.execute(MEMORY_CAPABILITY_ID, req_bad_payload)
        assert exc_p.value.code == "MEMORY_CONFLICT"

        # Conflicting provenance
        req_bad_prov = dict(req)
        req_bad_prov["provenance"] = dict(prov, confidence=0.1)
        with pytest.raises(LocalPillarError) as exc_pr:
            service.execute(MEMORY_CAPABILITY_ID, req_bad_prov)
        assert exc_pr.value.code == "MEMORY_CONFLICT"

        # Conflicting indexes
        req_bad_idx = dict(req)
        req_bad_idx["indexes"] = dict(idxs, semantic=["completely_different"])
        with pytest.raises(LocalPillarError) as exc_idx:
            service.execute(MEMORY_CAPABILITY_ID, req_bad_idx)
        assert exc_idx.value.code == "MEMORY_CONFLICT"
    finally:
        store.close()


def test_holographic_index_reconstruction(tmp_path: Path) -> None:
    db_file = tmp_path / "holo_rebuild.sqlite3"
    store = EpisodicMemoryStore(db_file)
    service = FoundationPillarCapabilityService(
        data_dir=tmp_path / "pillars",
        episodic_memory=store,
    )
    try:
        for i in range(5):
            service.execute(
                MEMORY_CAPABILITY_ID,
                {
                    "action": "append",
                    "event_id": f"event-rebuild-{i:03d}",
                    "event_type": "AUDIT_LOG",
                    "session_id": "sess-rebuild",
                    "goal_id": "goal-rebuild",
                    "payload": {"step": i},
                    "sequence_number": i,
                    "provenance": _valid_provenance(),
                    "indexes": {
                        "semantic": [f"topic_{i}"],
                        "entity": ["rebuild_worker"],
                    },
                },
            )

        # Corrupt/truncate the index table directly
        with store._get_connection() as conn:
            conn.execute("DELETE FROM holographic_indexes;")

        # Query should now find 0 results
        empty_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "entity", "index_value": "rebuild_worker"},
        )
        assert len(empty_res.data["events"]) == 0

        # Run index reconstruction
        rebuild_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "rebuild_indexes"},
        )
        assert rebuild_res.code == "INDEXES_REBUILT"
        assert rebuild_res.data["indexed_events_count"] == 5

        # Query should now find all 5 events
        restored_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "entity", "index_value": "rebuild_worker"},
        )
        assert len(restored_res.data["events"]) == 5
    finally:
        store.close()


def test_holographic_compaction_and_retention(tmp_path: Path) -> None:
    db_file = tmp_path / "holo_compact.sqlite3"
    store = EpisodicMemoryStore(db_file)
    service = FoundationPillarCapabilityService(
        data_dir=tmp_path / "pillars",
        episodic_memory=store,
    )
    try:
        t0 = time.time()
        # Insert 2 events
        service.execute(
            MEMORY_CAPABILITY_ID,
            {
                "action": "append",
                "event_id": "event-keep",
                "event_type": "DATA",
                "session_id": "s1",
                "goal_id": "g1",
                "payload": {"keep": True},
                "sequence_number": 1,
                "provenance": _valid_provenance(),
                "indexes": {"semantic": ["retention_test"]},
            },
        )
        service.execute(
            MEMORY_CAPABILITY_ID,
            {
                "action": "append",
                "event_id": "event-prune",
                "event_type": "DATA",
                "session_id": "s1",
                "goal_id": "g1",
                "payload": {"keep": False},
                "sequence_number": 2,
                "provenance": _valid_provenance(),
                "indexes": {"semantic": ["retention_test"]},
            },
        )

        # Revoke the second event with timestamp 100 seconds ago
        store.revoke_holographic("event-prune", "data superseded", t0 - 100.0)

        # Compact with retention 50 seconds -> event-prune is older than 50s cutoff -> pruned
        compact_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "compact", "retention_seconds": 50.0},
        )
        assert compact_res.code == "MEMORY_COMPACTED"
        assert compact_res.data["pruned_events_count"] == 1
        assert "event-prune" in compact_res.data["pruned_event_ids"]

        # Verify event-keep is still intact
        q_keep = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "get_record", "event_id": "event-keep"},
        )
        assert q_keep.code == "MEMORY_RECORD_READ"

        # Verify event-prune is gone
        with pytest.raises(LocalPillarError) as exc_gone:
            service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "get_record", "event_id": "event-prune"},
            )
        assert exc_gone.value.code == "MEMORY_NOT_FOUND"
    finally:
        store.close()


def test_holographic_export_and_gdpr_delete(tmp_path: Path) -> None:
    db_file = tmp_path / "holo_export_del.sqlite3"
    store = EpisodicMemoryStore(db_file)
    service = FoundationPillarCapabilityService(
        data_dir=tmp_path / "pillars",
        episodic_memory=store,
    )
    try:
        service.execute(
            MEMORY_CAPABILITY_ID,
            {
                "action": "append",
                "event_id": "user-privacy-001",
                "event_type": "USER_PREFERENCE",
                "session_id": "user-sess-42",
                "goal_id": "onboarding",
                "payload": {"theme": "dark"},
                "sequence_number": 1,
                "provenance": _valid_provenance(owner_id="user-42"),
                "indexes": {"semantic": ["user_settings"]},
            },
        )

        # Export
        exp_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "export", "owner_id": "user-42"},
        )
        assert exp_res.code == "MEMORY_EXPORTED"
        assert exp_res.data["count"] == 1
        assert exp_res.data["events"][0]["event"]["event_id"] == "user-privacy-001"

        # Unauthorized delete attempt
        with pytest.raises(LocalPillarError) as exc_unauth:
            service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "delete", "event_id": "user-privacy-001", "owner_id": "attacker"},
            )
        assert exc_unauth.value.code == "MEMORY_NOT_FOUND_OR_DENIED"

        # Authorized delete
        del_res = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "delete", "event_id": "user-privacy-001", "owner_id": "user-42"},
        )
        assert del_res.code == "MEMORY_EVENT_DELETED"
        assert del_res.data["deleted"] is True

        # Assert no record remains
        with pytest.raises(LocalPillarError):
            service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "get_record", "event_id": "user-privacy-001"},
            )
    finally:
        store.close()


def test_holographic_schema_version_and_restart(tmp_path: Path) -> None:
    db_file = tmp_path / "holo_restart.sqlite3"
    store = EpisodicMemoryStore(db_file)
    try:
        # Check meta table
        with store._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM holographic_meta WHERE key='schema_version';"
            ).fetchone()
            assert row is not None
            assert str(row["value"]) == "1"

        store.append_holographic(
            MemoryEvent(
                event_id="persist-01",
                event_type="STATE",
                session_id="s-persist",
                goal_id="g-persist",
                payload={"checkpoint": 100},
                node_id="local",
                sequence_number=1,
            ),
            _valid_provenance(),
            {"entity": ["checkpoint_node"]},
        )
    finally:
        store.close()

    # Reopen from disk
    reopened = EpisodicMemoryStore(db_file)
    try:
        assert reopened.health_check() is True
        rec = reopened.holographic_record("persist-01")
        assert rec is not None
        assert rec["event"]["payload"]["checkpoint"] == 100
        assert rec["indexes"]["entity"] == ["checkpoint_node"]
    finally:
        reopened.close()
