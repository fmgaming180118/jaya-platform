"""Tests for the review-only Crucible boundary."""

from __future__ import annotations

import json
from pathlib import Path

from jaya_research.evolution.crucible import Crucible
from jaya_research.research.research_artifact import validate_artifact_dict


def test_crucible_exports_simulation_candidate_without_execution(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "must-not-exist.txt"
    python_code = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed')\n"
    )
    crucible = Crucible(
        workspace_id="pytest_env",
        source_root=tmp_path,
        outbox_dir=tmp_path / "outbox",
    )

    success, log, result = crucible.run_experiment(
        "Unverified test hypothesis",
        python_code,
        timeout_seconds=5,
    )

    assert success is False
    assert log.startswith("SIMULATION_CANDIDATE_EXPORTED")
    assert result["status"] == "SIMULATION_CANDIDATE_EXPORTED"
    assert result["candidate_executed"] is False
    assert result["benchmark_status"] == "NOT_RUN"
    assert result["novelty_status"] == "NOT_ASSESSED"
    assert result["empirical_metrics"] is None
    assert not marker.exists()

    artifact = json.loads(
        Path(result["artifact_path"]).read_text(encoding="utf-8")
    )
    validate_artifact_dict(artifact)
    assert artifact["evidence_kind"] == "SIMULATION"
    assert artifact["status"] == "SIMULATION_ONLY"
    assert artifact["payload"]["execution_backend"] == "UNAVAILABLE"


def test_crucible_rejects_invalid_syntax(tmp_path: Path) -> None:
    crucible = Crucible(
        workspace_id="pytest_env",
        source_root=tmp_path,
        outbox_dir=tmp_path / "outbox",
    )

    success, log, result = crucible.run_experiment(
        "Broken candidate",
        "def calc()\n    return 1\n",
        timeout_seconds=5,
    )

    assert success is False
    assert "CANDIDATE_REJECTED" in log
    assert result["candidate_executed"] is False
    assert list((tmp_path / "outbox").glob("*.json")) == []


def test_crucible_rejects_unbounded_loop_and_timeout(tmp_path: Path) -> None:
    crucible = Crucible(
        workspace_id="pytest_env",
        source_root=tmp_path,
        outbox_dir=tmp_path / "outbox",
    )

    success, log, result = crucible.run_experiment(
        "Unbounded candidate",
        "while True:\n    pass\n",
        timeout_seconds=5,
    )

    assert success is False
    assert "Unbounded loop rejected" in log
    assert result["candidate_executed"] is False

    success, log, result = crucible.run_experiment(
        "Invalid timeout",
        "VALUE = 1\n",
        timeout_seconds=0,
    )
    assert success is False
    assert "bounded integer" in log
    assert result == {}
