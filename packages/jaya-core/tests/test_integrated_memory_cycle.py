"""End-to-end tests for semantic, temporal, and holographic memory integration."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.local_capabilities import LocalPillarError


def _request(now: float) -> dict[str, object]:
    return {
        "source_ref": "test:integrated-memory-source",
        "content": (
            "artifact:Evidence_42 -supports-> concept:Traceable_Reasoning and "
            "model:Jaya_Core"
        ),
        "namespace": "integration-test",
        "record_id": "temporal-integrated-memory-1",
        "event_id": "memory-integrated-memory-1",
        "session_id": "session-integrated-memory",
        "goal_id": "goal-integrated-memory",
        "owner_id": "owner-integrated-memory",
        "policy": "internal",
        "base_score": 0.9,
        "confidence": 0.85,
        "observed_at": now,
        "evaluated_at": now,
        "decay_rate": 0.05,
        "sequence_number": 1,
    }


def test_memory_cycle_rejects_untyped_content_before_any_write(tmp_path: Path) -> None:
    data_dir = tmp_path / "pillars"
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3", local_pillar_data_dir=data_dir
    )
    request = _request(time.time())
    request["content"] = "untyped text cannot enter the semantic memory slice"
    try:
        with pytest.raises(LocalPillarError) as failure:
            runtime.execute_integrated_memory_cycle(request)
        assert failure.value.code == "SEMANTIC_ENTITY_REQUIRED"
    finally:
        runtime.close()

    with sqlite3.connect(data_dir / "semantic_bridge.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM semantic_sources").fetchone()[0] == 0
    with sqlite3.connect(data_dir / "temporal_weighting.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM temporal_records").fetchone()[0] == 0


def test_memory_cycle_is_idempotent_and_survives_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "pillars"
    database = tmp_path / "core.sqlite3"
    request = _request(time.time())
    runtime = JayaCoreRuntime(db_path=database, local_pillar_data_dir=data_dir)
    try:
        first = runtime.execute_integrated_memory_cycle(request)
        duplicate = runtime.execute_integrated_memory_cycle(request)
        assert first["status"] == "INTEGRATED_MEMORY_CYCLE_COMPLETED"
        assert first["pillars"] == ["P008", "P026", "P027"]
        assert first["semantic"]["method"] == "RULE_BASED_TYPED_GRAMMAR"
        assert first["temporal"]["ranked_record"]["weighted_score"] == pytest.approx(0.9)
        assert first["memory"]["inserted"] is True
        assert first["evidence_status"] == "UNVERIFIED"
        assert duplicate["memory"]["inserted"] is False
        assert duplicate["temporal"]["record_id"] == request["record_id"]
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(db_path=database, local_pillar_data_dir=data_dir)
    try:
        semantic = restarted.foundation_pillar_capabilities.semantic.execute(
            {"action": "query", "value": "traceable_reasoning", "namespace": "integration-test"}
        )
        temporal = restarted.foundation_pillar_capabilities.temporal.execute(
            {
                "action": "rank",
                "decay_rate": request["decay_rate"],
                "now": request["evaluated_at"],
            }
        )
        memory = restarted.foundation_pillar_capabilities.memory.execute(
            {
                "action": "query_session",
                "session_id": request["session_id"],
            }
        )
        assert semantic.data["matches"][0]["source_ref"] == request["source_ref"]
        assert temporal.data["records"][0]["record_id"] == request["record_id"]
        assert memory.data["events"][0]["event_id"] == request["event_id"]
        assert memory.data["events"][0]["payload"]["evidence_status"] == "UNVERIFIED"
    finally:
        restarted.close()


def test_holographic_duplicate_rejects_payload_conflict(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
    )
    request = _request(time.time())
    try:
        runtime.execute_integrated_memory_cycle(request)
        with pytest.raises(LocalPillarError) as conflict:
            runtime.foundation_pillar_capabilities.memory.execute(
                {
                    "action": "append",
                    "event_id": request["event_id"],
                    "event_type": "SEMANTIC_EVIDENCE_INDEXED",
                    "session_id": request["session_id"],
                    "goal_id": request["goal_id"],
                    "sequence_number": request["sequence_number"],
                    "payload": {"different": True},
                    "provenance": {
                        "source_digest": runtime.foundation_pillar_capabilities.semantic.execute(
                            {"action": "source", "source_ref": request["source_ref"]}
                        ).data["source_digest"],
                        "confidence": request["confidence"],
                        "owner_id": request["owner_id"],
                        "policy": request["policy"],
                        "observed_at": request["observed_at"],
                    },
                    "indexes": {
                        "semantic": ["concept:traceable_reasoning"],
                        "entity": ["traceable_reasoning"],
                        "task": [request["goal_id"]],
                    },
                }
            )
        assert conflict.value.code == "MEMORY_CONFLICT"
    finally:
        runtime.close()

