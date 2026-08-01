"""Truth-boundary tests for the evidence-first deep-research workflow."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from provider_errors import ProviderNetworkError
from research.agent import ResearchAgent, ResearchWorkflowError
from research.retrieval_evidence import build_grounded_response


class StubConfig:
    max_queries = 4
    max_iterations = 1
    reports_dir = "."

    @staticmethod
    def get_prompt(prompt_name: str, **values: Any) -> str:
        return f"{prompt_name}:{values['topic']}"


class EmptyRAG:
    @staticmethod
    def search(query: str, *, top_k: int) -> list[dict[str, Any]]:
        return []


class CountingTeacher:
    def __init__(self, response: str = "") -> None:
        self.response = response
        self.calls = 0

    def ask(self, prompt: str, *, system_instruction: str) -> str:
        self.calls += 1
        return self.response


class CompleteEvidenceRAG:
    @staticmethod
    def search(query: str, *, top_k: int) -> list[dict[str, Any]]:
        return [
            {
                "score": 0.92,
                "content": "The measured latency was 14 ms in the cited run.",
                "metadata": {
                    "source_id": "paper-1",
                    "source_uri": "https://example.invalid/paper-1",
                    "page_number": 3,
                    "word_start": 20,
                    "word_end": 30,
                    "license_id": "CC-BY-4.0",
                },
            }
        ]


class RejectingGraph:
    def __init__(self) -> None:
        self.ingest_calls = 0

    def ingest_document(self, *args: Any, **kwargs: Any) -> None:
        self.ingest_calls += 1
        raise AssertionError("Generated prose must not be graph evidence")


class FailingTeacher:
    @staticmethod
    def ask(prompt: str, *, system_instruction: str) -> str:
        raise ProviderNetworkError("test-model", "offline")


class ResolvingRAG:
    def __init__(self) -> None:
        self.calls = 0

    def search(self, query: str, *, top_k: int) -> list[dict[str, Any]]:
        self.calls += 1
        if self.calls == 1:
            return []
        return CompleteEvidenceRAG.search(query, top_k=top_k)


def _agent(*, teacher: Any, rag: Any, graph: Any = None) -> ResearchAgent:
    return ResearchAgent(
        "Bounded research",
        teacher=teacher,
        rag=rag,
        web_search=None,
        graph_rag=graph,
        research_config=StubConfig(),
        plan_questions=["What evidence is available for this claim?"],
    )


def test_empty_retrieval_abstains_without_asking_model_for_an_answer() -> None:
    teacher = CountingTeacher("This internal answer must never be used.")
    agent = _agent(teacher=teacher, rag=EmptyRAG())

    findings = agent.execute_queries(
        ["What evidence is available for this claim?"]
    )

    assert findings[0]["status"] == "ABSTAINED_NO_EVIDENCE"
    assert findings[0]["citations"] == []
    assert findings[0]["promotion_eligible"] is False
    assert teacher.calls == 0


def test_invalid_planner_output_fails_closed_without_generic_questions() -> None:
    teacher = CountingTeacher("A paragraph that answers instead of planning.")
    agent = ResearchAgent(
        "Planner boundary",
        teacher=teacher,
        rag=EmptyRAG(),
        web_search=None,
        research_config=StubConfig(),
    )

    with pytest.raises(ResearchWorkflowError) as caught:
        agent.generate_plan()

    assert caught.value.code == "PLAN_INVALID"
    assert agent.queries == []


def test_model_draft_is_excluded_from_report_and_never_graph_ingested() -> None:
    teacher = CountingTeacher("[CIT-1] A fluent but generated interpretation.")
    graph = RejectingGraph()
    agent = _agent(teacher=teacher, rag=CompleteEvidenceRAG(), graph=graph)

    agent.findings = agent.execute_queries(
        ["What evidence is available for this claim?"]
    )
    report = agent.write_report()

    assert agent.findings[0]["model_synthesis_status"] == "UNVERIFIED_CITED_DRAFT"
    assert "A fluent but generated interpretation" not in report
    assert "The measured latency was 14 ms" in report
    assert "Promotion eligible:** false" in report
    assert graph.ingest_calls == 0


def test_report_path_is_contained_in_configured_directory(tmp_path: Path) -> None:
    agent = _agent(teacher=CountingTeacher(), rag=EmptyRAG())
    agent.config = SimpleNamespace(reports_dir=str(tmp_path), max_queries=4)
    agent._clock = lambda: 123.0
    agent._run_id = "testrun0001"

    assert agent.get_report_path() == str(
        tmp_path / "Bounded_research_123_testrun0001.md"
    )


def test_missing_real_uri_never_becomes_complete_provenance() -> None:
    item = {
        "score": 0.9,
        "content": "A claim with a label but no openable source.",
        "metadata": {
            "page_number": 1,
            "word_start": 0,
            "word_end": 8,
            "license_id": "CC-BY-4.0",
        },
    }
    normalized = ResearchAgent._normalize_result(item, source_kind="LOCAL")

    assert normalized is not None
    grounded = build_grounded_response([normalized])
    assert grounded["evidence_quality"] == "INCOMPLETE_PROVENANCE"
    assert grounded["promotable"] is False


def test_retry_replaces_abstention_with_latest_complete_finding(
    tmp_path: Path,
) -> None:
    rag = ResolvingRAG()
    agent = ResearchAgent(
        "Retry research",
        teacher=None,
        rag=rag,
        web_search=None,
        research_config=StubConfig(),
        plan_questions=["What evidence is available for this claim?"],
        memory_path=tmp_path / "memory.json",
        run_id="retryrun001",
    )
    agent.config = SimpleNamespace(
        reports_dir=str(tmp_path / "reports"),
        max_queries=4,
        max_iterations=1,
    )

    report = agent.run(human_in_loop=False)

    assert rag.calls == 2
    assert len(agent.attempt_history) == 2
    assert len(agent.findings) == 1
    assert agent.findings[0]["status"] == "ANSWERED"
    assert agent.findings[0]["evidence_quality"] == "COMPLETE_PROVENANCE"
    assert "The measured latency was 14 ms" in report


def test_optional_provider_failure_preserves_grounded_extractive_answer() -> None:
    agent = _agent(teacher=FailingTeacher(), rag=CompleteEvidenceRAG())

    finding = agent.execute_queries(agent._supplied_plan)[0]

    assert finding["status"] == "ANSWERED"
    assert finding["model_synthesis"] == ""
    assert finding["model_synthesis_status"] == "PROVIDER_UNAVAILABLE"
    assert "The measured latency was 14 ms" in finding["answer"]


def test_same_second_runs_have_distinct_immutable_report_paths(tmp_path: Path) -> None:
    first = _agent(teacher=None, rag=EmptyRAG())
    second = _agent(teacher=None, rag=EmptyRAG())
    for agent in (first, second):
        agent.config = SimpleNamespace(reports_dir=str(tmp_path), max_queries=4)
        agent._clock = lambda: 123.0
        agent.report = "# Immutable report\n"

    first_path = first.get_report_path()
    second_path = second.get_report_path()

    assert first_path != second_path
    first._write_report_once(Path(first_path), first.report)
    with pytest.raises(ResearchWorkflowError) as caught:
        first._write_report_once(Path(first_path), first.report)
    assert caught.value.code == "REPORT_ALREADY_EXISTS"
