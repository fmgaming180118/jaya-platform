"""Real local behavior and persistence tests for P8/P23/P27/P35."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.memory.episodic import EpisodicMemoryStore
from jaya_core.pillars.foundation_capabilities import (
    MEMORY_CAPABILITY_ID,
    SANDBOX_CAPABILITY_ID,
    SPARSE_CAPABILITY_ID,
    TEMPORAL_CAPABILITY_ID,
    FoundationPillarCapabilityService,
    SandboxedImaginationCapability,
    TemporalWeightingCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError

SOURCE_DIGEST = "sha256:" + "a" * 64


def _memory_metadata() -> dict[str, object]:
    return {
        "provenance": {
            "source_digest": SOURCE_DIGEST,
            "confidence": 0.9,
            "owner_id": "owner-test",
            "policy": "INTERNAL",
            "observed_at": time.time(),
        },
        "indexes": {
            "semantic": ["measured-local-evidence"],
            "entity": ["jaya"],
            "task": ["research-validation"],
        },
    }


def _service(
    tmp_path: Path,
    *,
    node_id: str = "node-a",
) -> tuple[FoundationPillarCapabilityService, EpisodicMemoryStore]:
    memory = EpisodicMemoryStore(tmp_path / f"{node_id}-memory.sqlite3")
    return (
        FoundationPillarCapabilityService(
            data_dir=tmp_path / node_id,
            episodic_memory=memory,
        ),
        memory,
    )


def test_p008_memory_uses_canonical_store_and_survives_restart(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    request = {
        "action": "append",
        "event_id": "memory-event-001",
        "event_type": "RESEARCH_OBSERVATION",
        "session_id": "session-001",
        "goal_id": "goal-001",
        "payload": {"claim": "measured locally", "label": "EMPIRICAL"},
        "sequence_number": 1,
        **_memory_metadata(),
    }
    appended = service.execute(MEMORY_CAPABILITY_ID, request)
    duplicate = service.execute(MEMORY_CAPABILITY_ID, request)
    memory.close()

    restarted_memory = EpisodicMemoryStore(tmp_path / "node-a-memory.sqlite3")
    restarted = FoundationPillarCapabilityService(
        data_dir=tmp_path / "node-a",
        episodic_memory=restarted_memory,
    )
    read = restarted.execute(
        MEMORY_CAPABILITY_ID,
        {"action": "query_session", "session_id": "session-001"},
    )
    restarted_memory.close()

    assert appended.code == "MEMORY_EVENT_APPENDED"
    assert duplicate.code == "MEMORY_EVENT_DUPLICATE"
    assert read.data["events"][0]["payload"]["label"] == "EMPIRICAL"


def test_p008_rejects_unknown_fields_and_oversized_payload(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    try:
        with pytest.raises(LocalPillarError) as unknown:
            service.execute(
                MEMORY_CAPABILITY_ID,
                {"action": "query_session", "session_id": "s", "unsafe": True},
            )
        assert unknown.value.code == "UNKNOWN_FIELD"
        with pytest.raises(LocalPillarError) as oversized:
            service.execute(
                MEMORY_CAPABILITY_ID,
                {
                    "action": "append",
                    "event_id": "oversized",
                    "event_type": "TEST",
                    "session_id": "session",
                    "goal_id": "goal",
                    "payload": {"content": "x" * (256 * 1024)},
                    **_memory_metadata(),
                },
            )
        assert oversized.value.code == "RESOURCE_LIMIT"
    finally:
        memory.close()


def test_p008_multi_index_revoke_and_provenance_conflict(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    request = {
        "action": "append",
        "event_id": "indexed-event-001",
        "event_type": "RESEARCH_EVIDENCE",
        "session_id": "session-indexed",
        "goal_id": "goal-indexed",
        "payload": {"claim": "indexed evidence"},
        **_memory_metadata(),
    }
    try:
        service.execute(MEMORY_CAPABILITY_ID, request)
        found = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "entity", "index_value": "JAYA"},
        )
        assert found.data["events"][0]["provenance"]["source_digest"] == SOURCE_DIGEST
        service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "revoke", "event_id": "indexed-event-001", "reason": "source withdrawn"},
        )
        hidden = service.execute(
            MEMORY_CAPABILITY_ID,
            {"action": "query", "index_type": "entity", "index_value": "jaya"},
        )
        audit = service.execute(
            MEMORY_CAPABILITY_ID,
            {
                "action": "query",
                "index_type": "entity",
                "index_value": "jaya",
                "include_revoked": True,
            },
        )
        assert hidden.data["events"] == []
        assert audit.data["events"][0]["provenance"]["revoke_reason"] == "source withdrawn"
        with pytest.raises(LocalPillarError) as conflict:
            service.execute(
                MEMORY_CAPABILITY_ID,
                {
                    **request,
                    "provenance": {
                        **request["provenance"],
                        "source_digest": "sha256:" + "b" * 64,
                    },
                },
            )
        assert conflict.value.code == "MEMORY_CONFLICT"
    finally:
        memory.close()


def test_p023_runs_real_isolated_worker_and_blocks_code_execution() -> None:
    sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)
    result = sandbox.evaluate("(12 + 8) * 3 == 60 and 7 > 2")

    assert result.data["result"] is True
    assert result.data["duration_ns"] > 0
    with pytest.raises(LocalPillarError) as forbidden:
        sandbox.evaluate("__import__('os').listdir('.')")
    assert forbidden.value.code == "SECURITY_VIOLATION"
    with pytest.raises(LocalPillarError) as resource:
        sandbox.evaluate("2 ** 99")
    assert resource.value.code == "SECURITY_VIOLATION"


def test_p027_persists_ranks_and_supersedes_records(tmp_path: Path) -> None:
    database = tmp_path / "temporal.sqlite3"
    service = TemporalWeightingCapability(database)
    now = time.time()
    service.execute(
        {
            "action": "add",
            "record_id": "old",
            "source_ref": "artifact:old",
            "base_score": 0.95,
            "observed_at": now - 7200,
            "payload": {"version": 1},
        }
    )
    service.execute(
        {
            "action": "add",
            "record_id": "new",
            "source_ref": "artifact:new",
            "base_score": 0.8,
            "observed_at": now,
            "supersedes": "old",
            "payload": {"version": 2},
        }
    )

    ranked = TemporalWeightingCapability(database).execute(
        {"action": "rank", "decay_rate": 0.1, "now": now}
    )

    assert [item["record_id"] for item in ranked.data["records"]] == ["new"]
    assert ranked.data["records"][0]["payload"] == {"version": 2}


def test_p027_rejects_future_clock_skew_and_conflicting_duplicate(tmp_path: Path) -> None:
    service = TemporalWeightingCapability(tmp_path / "temporal.sqlite3")
    request = {
        "action": "add",
        "record_id": "record-1",
        "source_ref": "artifact:record-1",
        "base_score": 0.5,
        "observed_at": time.time(),
        "payload": {"value": 1},
    }
    service.execute(request)
    duplicate = service.execute(request)
    assert duplicate.code == "TEMPORAL_RECORD_DUPLICATE"
    assert duplicate.data["inserted"] is False
    with pytest.raises(LocalPillarError) as conflict:
        service.execute({**request, "base_score": 0.6})
    assert conflict.value.code == "TEMPORAL_CONFLICT"
    with pytest.raises(LocalPillarError) as skew:
        service.execute({**request, "record_id": "future", "observed_at": time.time() + 600})
    assert skew.value.code == "CLOCK_SKEW"


def test_p035_executes_sparse_kernel_and_checks_scalar_baseline(tmp_path: Path) -> None:
    service, memory = _service(tmp_path)
    try:
        result = service.execute(
            SPARSE_CAPABILITY_ID,
            {"action": "run", "values": [1.0, -5.0, 2.0, 0.2], "top_k": 2},
        )
        assert result.data["indices"] == [1, 2]
        assert result.data["non_zero"] == 2
        assert result.data["achieved_sparsity"] == 0.5
        assert result.data["verified_against"] == "PYTHON_SCALAR_TOP_K"
    finally:
        memory.close()


def test_runtime_dispatches_foundation_capabilities(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
    )
    try:
        sandbox = runtime.execute_local_pillar(
            SANDBOX_CAPABILITY_ID,
            {"action": "evaluate", "expression": "40 + 2"},
        )
        health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        assert sandbox.data["result"] == 42
        assert health[SANDBOX_CAPABILITY_ID] == "HEALTHY"
        assert health[TEMPORAL_CAPABILITY_ID] == "HEALTHY"
        assert health[MEMORY_CAPABILITY_ID] == "HEALTHY"
        ranked = runtime.execute_local_pillar(
            TEMPORAL_CAPABILITY_ID,
            {"action": "rank", "decay_rate": 0.1},
        )
        assert ranked.data["records"] == []
    finally:
        runtime.close()
