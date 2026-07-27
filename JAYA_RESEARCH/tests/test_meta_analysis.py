"""Deterministic unit tests for research meta-analysis.

Live model-provider checks are intentionally excluded from pytest. They belong
in an explicitly invoked manual check with credentials and network access.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import sys
from pathlib import Path
from typing import Any

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_meta_analysis_module():
    """Import production code only during test execution, without import prints."""
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return importlib.import_module("research.meta_analysis")


class FakeMemory:
    def __init__(self, history: list[dict[str, Any]]) -> None:
        self.history = history
        self.added: list[dict[str, Any]] = []

    def add_experience(
        self,
        *,
        code: str,
        result: str,
        metadata: dict[str, Any],
    ) -> None:
        entry = {
            "code": code,
            "result": result,
            "metadata": dict(metadata),
            "timestamp": metadata["timestamp"],
        }
        self.history.append(entry)
        self.added.append(entry)


class FakeTeacher:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, str]] = []

    def ask(self, prompt: str, *, system_instruction: str) -> str:
        self.calls.append(
            {
                "prompt": prompt,
                "system_instruction": system_instruction,
            }
        )
        return self.response


class FakeConfig:
    def __init__(self, reports_dir: Path) -> None:
        self.reports_dir = str(reports_dir)
        self.prompt_calls: list[dict[str, Any]] = []

    def get_prompt(self, prompt_name: str, **values: Any) -> str:
        self.prompt_calls.append({"name": prompt_name, **values})
        return f"Topic: {values['topic']}\n{values['summaries']}"


def test_meta_analysis_uses_only_recent_matching_reports_and_persists_result(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_meta_analysis_module()
    fixed_time = 2_000_000_000.0
    monkeypatch.setattr(module.time, "time", lambda: fixed_time)

    memory = FakeMemory(
        [
            {
                "result": "RESEARCH_REPORT",
                "timestamp": fixed_time - 60,
                "code": "Recent evidence about JIT compilation.",
                "metadata": {"topic": "JIT Compilation"},
            },
            {
                "result": "RESEARCH_REPORT",
                "timestamp": fixed_time - (2 * 86_400),
                "code": "Old JIT evidence outside the lookback window.",
                "metadata": {"topic": "JIT Runtime"},
            },
            {
                "result": "RESEARCH_REPORT",
                "timestamp": fixed_time - 30,
                "code": "Recent but unrelated database evidence.",
                "metadata": {"topic": "Database Indexing"},
            },
        ]
    )
    teacher = FakeTeacher("# Offline Meta Report\nGrounded synthesis.")
    config = FakeConfig(tmp_path / "reports")
    analyst = module.MetaAnalyst.__new__(module.MetaAnalyst)
    analyst.memory = memory
    analyst.teacher = teacher
    analyst.config = config

    with contextlib.redirect_stdout(io.StringIO()):
        result = analyst.run_meta_analysis("JIT", lookback_days=1)

    assert result == "# Offline Meta Report\nGrounded synthesis."
    assert len(teacher.calls) == 1
    prompt = teacher.calls[0]["prompt"]
    assert "Recent evidence about JIT compilation." in prompt
    assert "Old JIT evidence" not in prompt
    assert "database evidence" not in prompt

    report_path = tmp_path / "reports" / "META_JIT_2000000000.md"
    assert report_path.read_text(encoding="utf-8") == result
    assert memory.added[-1]["result"] == "META_ANALYSIS"
    assert memory.added[-1]["metadata"]["reports_analyzed"] == 2


def test_meta_analysis_without_matching_history_does_not_call_provider(
    tmp_path: Path,
) -> None:
    module = _load_meta_analysis_module()
    teacher = FakeTeacher("must not be returned")
    analyst = module.MetaAnalyst.__new__(module.MetaAnalyst)
    analyst.memory = FakeMemory([])
    analyst.teacher = teacher
    analyst.config = FakeConfig(tmp_path / "reports")

    with contextlib.redirect_stdout(io.StringIO()):
        result = analyst.run_meta_analysis("missing topic", lookback_days=1)

    assert result == "No research data available for meta-analysis."
    assert teacher.calls == []
    assert not (tmp_path / "reports").exists()
