"""Offline tests for bounded multi-query research execution."""

from __future__ import annotations

import contextlib
import importlib
import io
import sys
import types
from typing import Any


def _load_agent_module():
    """Import the agent only during test execution and suppress import banners."""
    with (
        contextlib.redirect_stdout(io.StringIO()),
        contextlib.redirect_stderr(io.StringIO()),
    ):
        return importlib.import_module("jaya_research.research.agent")


class FakeRAG:
    def __init__(self) -> None:
        self.queries: list[tuple[str, int]] = []

    def search(self, query: str, *, top_k: int) -> list[dict[str, Any]]:
        self.queries.append((query, top_k))
        if query == "cached evidence":
            return [
                {
                    "score": 0.9,
                    "snippet": "Evidence stored in the local workspace.",
                    "document": {"file_name": "local-study.md"},
                }
            ]
        return []


class FakeWebSearchClient:
    instances: list[FakeWebSearchClient] = []

    def __init__(self) -> None:
        self.queries: list[tuple[str, int]] = []
        self.instances.append(self)

    def is_available(self) -> bool:
        return True

    def search(self, query: str, *, max_results: int) -> list[dict[str, str]]:
        self.queries.append((query, max_results))
        return [
            {
                "title": "Offline fixture",
                "snippet": f"Deterministic evidence for {query}.",
                "url": "https://example.invalid/offline-fixture",
                "source": "offline_fixture",
            }
        ]


class FakeTeacher:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def ask(self, prompt: str, *, system_instruction: str) -> str:
        self.prompts.append(prompt)
        assert "provided context" in system_instruction
        return "Answer grounded in injected evidence."


def test_execute_queries_uses_local_results_then_injected_web_fallback(
    monkeypatch,
) -> None:
    module = _load_agent_module()
    module_name = "jaya_research.research.web_search"
    fake_web_module = types.ModuleType(module_name)
    fake_web_module.WebSearchClient = FakeWebSearchClient
    monkeypatch.setitem(sys.modules, module_name, fake_web_module)
    FakeWebSearchClient.instances.clear()

    agent = module.ResearchAgent.__new__(module.ResearchAgent)
    agent.topic = "Offline research"
    agent.queries = ["cached evidence", "missing evidence"]
    agent.rag = FakeRAG()
    agent.teacher = FakeTeacher()
    agent.graph_rag = None

    with contextlib.redirect_stdout(io.StringIO()):
        findings = agent.execute_queries()

    assert [finding["query"] for finding in findings] == agent.queries
    assert findings[0]["sources"] == ["local-study.md"]
    assert findings[0]["source_count"] == 1
    assert findings[1]["sources"] == ["Offline fixture"]
    assert findings[1]["source_count"] == 1
    assert agent.rag.queries == [
        ("cached evidence", 3),
        ("missing evidence", 3),
    ]
    assert len(FakeWebSearchClient.instances) == 1
    assert FakeWebSearchClient.instances[0].queries == [("missing evidence", 3)]
    assert len(agent.teacher.prompts) == 2
