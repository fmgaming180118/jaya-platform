"""Abuse tests for the legacy Research evolution boundary."""

from __future__ import annotations

import ast
import asyncio
import hashlib
import importlib
from pathlib import Path
from typing import Any

import pytest
from jaya_research.evolution.mutator import CodeMutator
from jaya_research.evolution.sandbox import EvolutionSandbox
from jaya_research.evolution.twin import DigitalTwin, TwinLoopPolicyError
from jaya_research.provider_errors import ProviderAuthError


class FakeMemory:
    def __init__(self) -> None:
        self.thoughts: list[dict[str, Any]] = []

    def log_thought(
        self,
        content: str,
        mood: str = "neutral",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        thought = {
            "content": content,
            "mood": mood,
            "context": dict(context or {}),
        }
        self.thoughts.append(thought)
        return thought


class FakeTeacher:
    def __init__(self, proposal: str) -> None:
        self.proposal = proposal
        self.calls = 0

    def suggest_optimization(self, source: str, *, focus: str) -> str:
        assert source
        assert focus
        self.calls += 1
        return self.proposal

    def ask(self, prompt: str, *, system_instruction: str) -> str:
        assert prompt
        assert system_instruction
        self.calls += 1
        return self.proposal


class FailingTeacher:
    def suggest_optimization(self, source: str, *, focus: str) -> str:
        del source, focus
        raise ProviderAuthError("test-provider", "credential unavailable")

    def ask(self, prompt: str, *, system_instruction: str) -> str:
        del prompt, system_instruction
        raise ProviderAuthError("test-provider", "credential unavailable")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_mutator_exports_candidate_and_preserves_source_digest(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    target = source_root / "engine.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    marker = tmp_path / "marker.txt"
    teacher = FakeTeacher(
        f"open({str(marker)!r}, 'w').write('executed')\nVALUE = 2\n"
    )
    digest_before = _sha256(target)
    mutator = CodeMutator(
        teacher=teacher,
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
    )

    receipt = mutator.evolve_file("engine.py", "Improve maintainability")

    assert receipt["status"] == "SIMULATION_CANDIDATE_EXPORTED"
    assert receipt["source_mutated"] is False
    assert receipt["candidate_executed"] is False
    assert _sha256(target) == digest_before
    assert not marker.exists()
    assert teacher.calls == 1


def test_sandbox_never_executes_marker_code(tmp_path: Path) -> None:
    marker = tmp_path / "sandbox-marker.txt"
    sandbox = EvolutionSandbox(
        source_root=tmp_path,
        outbox_dir=tmp_path / "outbox",
    )

    receipt = sandbox.run_code(
        f"open({str(marker)!r}, 'w').write('executed')\n",
    )

    assert receipt["status"] == "SIMULATION_CANDIDATE_EXPORTED"
    assert receipt["success"] is False
    assert receipt["candidate_executed"] is False
    assert not marker.exists()


def test_provider_missing_twin_takes_no_action(tmp_path: Path) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    target = source_root / "engine.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    digest_before = _sha256(target)
    memory = FakeMemory()
    twin = DigitalTwin(
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
        memory=memory,
        cycle_interval_seconds=0,
    )

    think_result = asyncio.run(twin.think())
    evolve_result = asyncio.run(twin.evolve("engine.py", "Change VALUE"))

    assert think_result["status"] == "UNAVAILABLE_PROVIDER_MISSING"
    assert think_result["action_dispatched"] is False
    assert evolve_result["status"] == "UNAVAILABLE_PROVIDER_MISSING"
    assert _sha256(target) == digest_before
    assert list((tmp_path / "outbox").glob("*.json")) == []


def test_provider_failure_is_typed_and_never_mutates_source(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    target = source_root / "engine.py"
    target.write_text("VALUE = 1\n", encoding="utf-8")
    digest_before = _sha256(target)
    twin = DigitalTwin(
        teacher=FailingTeacher(),
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
        memory=FakeMemory(),
        cycle_interval_seconds=0,
    )

    think_result = asyncio.run(twin.think())
    evolve_result = asyncio.run(twin.evolve("engine.py", "Change VALUE"))

    assert think_result["status"] == "PROVIDER_ERROR"
    assert think_result["provider_error"]["code"] == "provider_auth_error"
    assert evolve_result["status"] == "PROVIDER_ERROR"
    assert evolve_result["provider_error"]["retryable"] is False
    assert _sha256(target) == digest_before
    assert list((tmp_path / "outbox").glob("*.json")) == []


def test_twin_loop_is_default_off_and_requires_explicit_bound(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "src"
    source_root.mkdir()
    twin = DigitalTwin(
        source_root=source_root,
        outbox_dir=tmp_path / "outbox",
        memory=FakeMemory(),
        cycle_interval_seconds=0,
    )

    disabled = asyncio.run(twin.start_loop())
    assert disabled["status"] == "DISABLED_BY_DEFAULT"
    assert twin.completed_cycles == 0

    with pytest.raises(TwinLoopPolicyError, match="Unbounded loop rejected"):
        asyncio.run(twin.start_loop(max_cycles=None, enabled=True))

    completed = asyncio.run(twin.start_loop(max_cycles=2, enabled=True))
    assert completed["status"] == "BOUNDED_BATCH_COMPLETED"
    assert completed["completed_cycles"] == 2
    assert twin.completed_cycles == 2


def test_legacy_runtime_contains_no_dynamic_or_subprocess_execution() -> None:
    evolution_dir = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "jaya_research"
        / "evolution"
    )
    files = [
        evolution_dir / "twin.py",
        evolution_dir / "mutator.py",
        evolution_dir / "sandbox.py",
        evolution_dir / "crucible.py",
    ]
    forbidden_calls: set[str] = set()
    forbidden_imports: set[str] = set()

    for file_path in files:
        tree = ast.parse(file_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"compile", "eval", "exec"}
            ):
                forbidden_calls.add(f"{file_path.name}:{node.func.id}")
            if isinstance(node, ast.Import):
                forbidden_imports.update(
                    alias.name.partition(".")[0]
                    for alias in node.names
                    if alias.name.partition(".")[0] == "subprocess"
                )
            if isinstance(node, ast.ImportFrom):
                module = str(node.module or "").partition(".")[0]
                if module == "subprocess":
                    forbidden_imports.add(module)

    assert forbidden_calls == set()
    assert forbidden_imports == set()


def test_api_twin_startup_is_default_off_bounded_and_threadless(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = importlib.import_module("jaya_research.network.research_api")
    api_source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "jaya_research"
        / "network"
        / "research_api.py"
    ).read_text(encoding="utf-8")

    class FakeTwin:
        @staticmethod
        def _validate_cycle_bound(value: int) -> int:
            if not 1 <= value <= 5:
                raise ValueError("cycle bound rejected")
            return value

    monkeypatch.setattr(api, "digital_twin", None)
    monkeypatch.setattr(api, "_digital_twin_max_cycles", None)
    monkeypatch.setattr(
        api,
        "_digital_twin_startup_status",
        {"status": "DISABLED_BY_DEFAULT", "candidate_only": True},
    )
    monkeypatch.setattr(
        api,
        "_load_optional_dependency",
        lambda *_args: FakeTwin,
    )
    monkeypatch.delenv("JAYA_ENABLE_DIGITAL_TWIN", raising=False)
    monkeypatch.delenv("JAYA_DIGITAL_TWIN_MAX_CYCLES", raising=False)

    api._configure_digital_twin()

    assert api.digital_twin is None
    assert api._digital_twin_startup_status["status"] == "DISABLED_BY_DEFAULT"

    monkeypatch.setenv("JAYA_ENABLE_DIGITAL_TWIN", "1")
    api._configure_digital_twin()
    assert api.digital_twin is None
    assert api._digital_twin_startup_status["status"] == "MISCONFIGURED_FAIL_CLOSED"

    monkeypatch.setenv("JAYA_DIGITAL_TWIN_MAX_CYCLES", "2")
    api._configure_digital_twin()
    assert isinstance(api.digital_twin, FakeTwin)
    assert api._digital_twin_max_cycles == 2
    assert api._digital_twin_startup_status == {
        "status": "READY_BOUNDED_CANDIDATE_ONLY",
        "candidate_only": True,
        "max_cycles": 2,
    }

    assert "threading.Thread" not in api_source
    assert "digital_twin.start_loop()" not in api_source
