"""End-to-end coverage for the production integrated reasoning vertical slice."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.control_capabilities import OBJECTIVE_CAPABILITY_ID
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.reasoning_capabilities import DREAM_CAPABILITY_ID

APPROVAL_KEY = b"test-only-integrated-reasoning-key-32-bytes"


def _request() -> dict[str, object]:
    return {
        "source_ref": "test:integrated-reasoning-evidence",
        "title": "Measured integrated reasoning evidence",
        "content": (
            "Measured evidence shows that a bounded integrated reasoning cycle requires "
            "citation-backed retrieval before hypothesis selection. Owner constraints remain "
            "true throughout the plan, and generated hypotheses remain unverified until an "
            "independent empirical experiment is completed."
        ),
        "topic": "bounded evidence reasoning",
        "query": "citation backed retrieval hypothesis selection",
        "constraints": ["2 + 2 == 4"],
        "candidate_limit": 1,
        "seed": 39,
        "goal": "Select one citation-backed hypothesis safely",
        "owner_id": "test-owner",
        "objective_id": "test-objective-integrated-cycle",
        "weights": {"evidence": 0.7, "safety": 0.3},
    }


def test_cycle_fails_closed_before_writes_when_model_is_unavailable(
    tmp_path: Path,
) -> None:
    data_dir = tmp_path / "pillars"
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=data_dir,
        lineage_signing_key=APPROVAL_KEY,
    )
    try:
        with pytest.raises(LocalPillarError) as failure:
            runtime.execute_integrated_reasoning_cycle(_request())
        assert failure.value.code == "PROVIDER_UNAVAILABLE"
    finally:
        runtime.close()

    with sqlite3.connect(data_dir / "agentic_rag.sqlite3") as connection:
        assert connection.execute("SELECT count(*) FROM rag_sources").fetchone()[0] == 0


@pytest.mark.integration
def test_live_integrated_cycle_survives_runtime_restart(tmp_path: Path) -> None:
    data_dir = tmp_path / "pillars"
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=data_dir,
        lineage_signing_key=APPROVAL_KEY,
        ollama_base_url="http://127.0.0.1:11434",
        local_model_name="qwen3.5:0.8b",
        local_model_timeout_seconds=120,
    )
    snapshot = runtime.operational_snapshot()["local_pillar_capabilities"]
    if not snapshot["integrated_reasoning_cycle"]["ready"]:
        runtime.close()
        pytest.skip("BLOCKED_EXTERNAL: configured Ollama test model is unavailable")
    try:
        result = runtime.execute_integrated_reasoning_cycle(_request())
        assert result["status"] == "INTEGRATED_REASONING_CYCLE_COMPLETED"
        assert set(result["pillars"]) == {
            "P003",
            "P023",
            "P033",
            "P036",
            "P037",
            "P038",
            "P039",
        }
        assert result["grounded_answer"]["provider_type"] == "LOCAL_MODEL"
        assert result["grounded_answer"]["result"]["citations"]
        assert result["hypothesis_artifact"]["provider_type"] == "LOCAL_MODEL"
        assert result["verification"]["selected"] is not None
        assert result["verification"]["empirical_status"] == "UNVERIFIED"
        assert result["plan"]["status"] == "COMPLETED"
        assert result["plan"]["objective_version"] == 1
        dream_id = result["hypothesis_artifact"]["dream_id"]
    finally:
        runtime.close()

    restarted = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=data_dir,
        lineage_signing_key=APPROVAL_KEY,
        ollama_base_url="http://127.0.0.1:11434",
        local_model_name="qwen3.5:0.8b",
        local_model_timeout_seconds=120,
    )
    try:
        persisted_dream = restarted.execute_local_pillar(
            DREAM_CAPABILITY_ID, {"action": "get", "dream_id": dream_id}
        )
        persisted_objective = restarted.execute_local_pillar(
            OBJECTIVE_CAPABILITY_ID,
            {
                "action": "get_active",
                "objective_id": "test-objective-integrated-cycle",
            },
        )
        assert persisted_dream.data["uncertainty"] == "UNVERIFIED"
        assert persisted_objective.data["version"] == 1
        assert restarted.advanced_pillar_capabilities.rag.retrieve(
            "citation backed retrieval", 5
        )
    finally:
        restarted.close()

