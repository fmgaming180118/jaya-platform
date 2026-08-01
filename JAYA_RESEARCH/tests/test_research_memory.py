"""Offline regression test for ResearchAgent report persistence."""

from __future__ import annotations

import contextlib
import importlib
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))


def _load_agent_module():
    """Import the agent only during test execution and suppress import banners."""
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return importlib.import_module("research.agent")


def test_save_report_writes_only_to_injected_report_and_memory_paths(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_agent_module()
    reports_dir = tmp_path / "reports"
    memory_path = tmp_path / "memory" / "discoveries.json"
    fixed_time = 2_000_000_000.0
    monkeypatch.setattr(module.time, "time", lambda: fixed_time)

    agent = module.ResearchAgent.__new__(module.ResearchAgent)
    agent.config = SimpleNamespace(reports_dir=str(reports_dir))
    agent.topic = "JIT Compilation Optimization"
    agent.focus_areas = "Compiler performance"
    agent.queries = ["What is JIT?", "How is JIT optimized?"]
    agent.findings = [
        {
            "query": "What is JIT?",
            "answer": "A runtime compilation strategy.",
            "sources": ["fixture.md"],
        }
    ]
    agent.report = "# Deterministic Research Report\nOffline evidence."
    agent._memory_path = memory_path
    agent._run_id = "memoryrun001"

    with contextlib.redirect_stdout(io.StringIO()):
        agent.save_report()

    report_path = (
        reports_dir
        / "JIT_Compilation_Optimization_2000000000_memoryrun001.md"
    )
    assert report_path.read_text(encoding="utf-8") == agent.report

    stored = json.loads(memory_path.read_text(encoding="utf-8"))
    assert len(stored) == 1
    entry = stored[0]
    assert entry["result"] == "UNVERIFIED_RESEARCH_REPORT"
    assert entry["topic"] == agent.topic
    assert entry["focus_areas"] == agent.focus_areas
    assert entry["queries_count"] == 2
    assert entry["findings_count"] == 1
    assert entry["report_path"] == str(report_path)
    assert entry["evidence_kind"] == "SYNTHESIS_DRAFT"
    assert entry["promotion_eligible"] is False
    assert len(entry["report_sha256"]) == 64
    assert len(entry["hash"]) == 64
