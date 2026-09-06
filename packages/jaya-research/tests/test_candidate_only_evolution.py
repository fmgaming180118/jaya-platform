"""Regression tests for the candidate-only Research evolution boundary."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from digital_twin_compiler import DigitalTwinCompiler
from jaya_research.optimizer import CandidateProposalError, Optimizer
from jaya_research.research.research_artifact import validate_artifact_dict


class FakeTeacher:
    def __init__(self, proposal: str) -> None:
        self.proposal = proposal

    def suggest_optimization(self, _source: str, *, focus: str) -> str:
        assert focus
        return self.proposal


def test_optimizer_exports_candidate_without_mutating_or_executing_source(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    target = source_root / "engine.py"
    original = "VALUE = 1\n"
    target.write_text(original, encoding="utf-8")
    marker = tmp_path / "must-not-exist.txt"
    proposed = (
        "def compile_jaya(source_code):\n"
        f"    open({str(marker)!r}, 'w').write('unsafe')\n"
        "    return source_code\n"
    )
    optimizer = Optimizer(
        teacher=FakeTeacher(proposed),
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
    )

    receipt = optimizer.evolve("engine.py")

    assert receipt["status"] == "SIMULATION_CANDIDATE_EXPORTED"
    assert receipt["source_mutated"] is False
    assert receipt["candidate_executed"] is False
    assert target.read_text(encoding="utf-8") == original
    assert not marker.exists()

    artifact = json.loads(Path(receipt["artifact_path"]).read_text(encoding="utf-8"))
    validate_artifact_dict(artifact)
    assert artifact["status"] == "SIMULATION_ONLY"
    assert artifact["payload"]["executable"] is False
    assert "risky_call:open" in artifact["payload"]["static_risks"]


def test_optimizer_rejects_target_escape_and_missing_teacher(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "engine.py").write_text("VALUE = 1\n", encoding="utf-8")
    optimizer = Optimizer(
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
    )

    with pytest.raises(CandidateProposalError, match="inside"):
        optimizer.read_target("../outside.py")
    with pytest.raises(CandidateProposalError, match="Teacher"):
        optimizer.evolve("engine.py")


def test_digital_twin_never_supports_unbounded_loop(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    (source_root / "engine.py").write_text(
        "def compile_jaya(source_code):\n    return source_code\n",
        encoding="utf-8",
    )
    twin = DigitalTwinCompiler(
        teacher=FakeTeacher(
            "def compile_jaya(source_code):\n    return source_code\n"
        ),
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
    )

    with pytest.raises(CandidateProposalError, match="Unbounded"):
        twin.run_evolution_loop(forever=True)


def test_legacy_candidate_export_script_contains_no_dynamic_execution() -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "auto_apply_upgrade.py"
    )
    tree = ast.parse(script.read_text(encoding="utf-8"))

    forbidden_calls = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in {"exec", "eval", "compile"}
    }
    assert forbidden_calls == set()
    assert "JAYA_CORE" not in script.read_text(encoding="utf-8")

