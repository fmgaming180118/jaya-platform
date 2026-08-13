"""Deterministic Phase A acceptance tests for academic analysis."""

from __future__ import annotations

import json

import pytest

from provider_errors import ProviderNetworkError
from research.academic.gap_finder import GapFinder
from research.academic.novelty_checker import NoveltyChecker


class FakeLiteratureProvider:
    def __init__(self, results=None, error: Exception | None = None) -> None:
        self.results = list(results or [])
        self.error = error
        self.queries: list[str] = []

    def search_papers(self, query: str, max_results: int = 5):
        self.queries.append(query)
        if self.error is not None:
            raise self.error
        return self.results[:max_results]


class FakeWebProvider(FakeLiteratureProvider):
    def is_available(self) -> bool:
        return True

    def search(self, query: str, max_results: int = 5):
        return self.search_papers(query, max_results=max_results)


class JSONEvaluator:
    def __init__(self, payload) -> None:
        self.payload = payload
        self.prompts: list[str] = []

    def ask(self, prompt: str, **_kwargs) -> str:
        self.prompts.append(prompt)
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


class FakeCitationProvider(FakeLiteratureProvider):
    def __init__(self, results=None, citations=None) -> None:
        super().__init__(results=results)
        self.citations = dict(citations or {})

    def get_citations(self, paper_id: str, limit: int = 5):
        return list(self.citations.get(paper_id, []))[:limit]


def _paper(identifier: str, title: str, summary: str) -> dict[str, str]:
    return {
        "id": identifier,
        "title": title,
        "summary": summary,
        "published": "2025",
        "url": f"https://literature.example/{identifier}",
    }


@pytest.mark.asyncio
async def test_empty_literature_is_not_mislabeled_as_novel() -> None:
    checker = NoveltyChecker(
        arxiv=FakeLiteratureProvider(),
        scholar=FakeLiteratureProvider(),
        web=None,
    )

    result = await checker.verify_novelty(
        "Adaptive causal retrieval for multilingual clinical evidence",
    )

    assert result["status"] == "indeterminate"
    assert result["is_novel"] is None
    assert result["confidence"] == 0.0
    assert result["promotion_eligible"] is False
    assert "not proof of novelty" in result["reasoning"]


@pytest.mark.asyncio
async def test_provider_coverage_fails_closed() -> None:
    unavailable = ProviderNetworkError("semantic_scholar", "offline")
    checker = NoveltyChecker(
        arxiv=FakeLiteratureProvider(
            [_paper("a", "Causal retrieval", "A measured retrieval study")]
        ),
        scholar=FakeLiteratureProvider(error=unavailable),
        web=None,
        min_completed_providers=2,
    )

    result = await checker.verify_novelty(
        "Causal retrieval with measured multilingual evidence",
    )

    assert result["status"] == "indeterminate"
    assert result["coverage"]["completed"] == 1
    assert result["provider_errors"][0]["code"] == "provider_network_error"


@pytest.mark.asyncio
async def test_high_overlap_rejects_known_mechanism_without_model() -> None:
    hypothesis = "causal graph retrieval calibrates multilingual clinical evidence"
    paper = _paper("known", hypothesis, hypothesis)
    checker = NoveltyChecker(
        arxiv=FakeLiteratureProvider([paper]),
        scholar=FakeLiteratureProvider([paper]),
        web=None,
    )

    result = await checker.verify_novelty(hypothesis)

    assert result["status"] == "complete"
    assert result["is_novel"] is False
    assert result["confidence"] >= 0.75
    assert result["evaluation_method"] == "DETERMINISTIC_LEXICAL_REJECTION"
    assert result["decision_evidence_ids"]


@pytest.mark.asyncio
async def test_positive_novelty_requires_traceable_evaluator_evidence() -> None:
    arxiv_paper = _paper(
        "arxiv-a",
        "Graph retrieval baselines",
        "A comparison of conventional retrieval methods.",
    )
    scholar_paper = _paper(
        "scholar-b",
        "Clinical evidence calibration",
        "Calibration without causal multilingual routing.",
    )
    evaluator = JSONEvaluator(
        {
            "is_novel": True,
            "confidence": 0.72,
            "reasoning": "The exact mechanism is not described in the reviewed set.",
            "evidence_ids": ["arxiv:arxiv-a", "semantic_scholar:scholar-b"],
        }
    )
    checker = NoveltyChecker(
        evaluator=evaluator,
        arxiv=FakeLiteratureProvider([arxiv_paper]),
        scholar=FakeLiteratureProvider([scholar_paper]),
        web=None,
    )

    result = await checker.verify_novelty(
        "Adaptive causal routing for multilingual clinical retrieval",
    )

    assert result["status"] == "complete"
    assert result["is_novel"] is True
    assert result["confidence"] == 0.72
    assert set(result["decision_evidence_ids"]) == {
        "arxiv:arxiv-a",
        "semantic_scholar:scholar-b",
    }
    assert result["promotion_eligible"] is False
    assert "EVIDENCE" in evaluator.prompts[0]


@pytest.mark.asyncio
async def test_untraceable_or_malformed_model_decision_is_indeterminate() -> None:
    papers = [_paper("paper-a", "Prior work", "A different measured mechanism")]
    checker = NoveltyChecker(
        evaluator=JSONEvaluator(
            {
                "is_novel": True,
                "confidence": 0.99,
                "reasoning": "Novel.",
                "evidence_ids": ["invented:reference"],
            }
        ),
        arxiv=FakeLiteratureProvider(papers),
        scholar=FakeLiteratureProvider(papers),
        web=None,
    )

    result = await checker.verify_novelty(
        "Adaptive causal routing for multilingual clinical retrieval",
    )

    assert result["status"] == "indeterminate"
    assert result["is_novel"] is None
    assert result["decision_evidence_ids"] == []


def test_keyword_extraction_is_deterministic_and_bounded() -> None:
    text = (
        "Multilingual retrieval retrieval calibrates causal clinical evidence "
        "for sovereign research systems"
    )

    first = NoveltyChecker._extract_keywords(text)
    second = NoveltyChecker._extract_keywords(text)

    assert first == second
    assert first[0] == "retrieval"
    assert 3 <= len(first) <= 8
    assert "research" not in first


def test_gap_screen_requires_search_and_real_graph_evidence() -> None:
    finder = GapFinder(scholar=FakeCitationProvider())

    before_search = finder.analyze_gaps_structured()
    finder.build_network("causal retrieval")
    after_empty_search = finder.analyze_gaps_structured()

    assert before_search["status"] == "SEARCH_NOT_RUN"
    assert after_empty_search["status"] == "INSUFFICIENT_EVIDENCE"
    assert after_empty_search["candidates"] == []
    assert after_empty_search["verified_gap"] is False
    assert after_empty_search["promotion_eligible"] is False


def test_connected_citation_cluster_does_not_fabricate_gap() -> None:
    seed = _paper("seed-a", "Causal retrieval", "")
    citation = {
        "id": "citation-a",
        "title": "Earlier retrieval study",
        "year": 2024,
        "url": "https://literature.example/citation-a",
    }
    finder = GapFinder(
        scholar=FakeCitationProvider(
            results=[seed],
            citations={"seed-a": [citation]},
        )
    )

    finder.build_network("causal retrieval", depth=1)
    result = finder.analyze_gaps_structured()

    assert result["status"] == "NO_STRUCTURAL_HOLE_OBSERVED"
    assert result["graph"] == {"nodes": 2, "edges": 1}
    assert len(result["clusters"]) == 1
    assert result["candidates"] == []


def test_disconnected_clusters_are_unverified_candidates_with_evidence_ids() -> None:
    finder = GapFinder(
        scholar=FakeCitationProvider(
            results=[
                _paper("seed-a", "Clinical retrieval", ""),
                _paper("seed-b", "Causal calibration", ""),
            ]
        )
    )

    finder.build_network("clinical causal evidence", depth=0)
    result = finder.analyze_gaps_structured()
    markdown = finder.analyze_gaps()

    assert result["status"] == "CANDIDATES_REQUIRE_REVIEW"
    assert len(result["clusters"]) == 2
    assert len(result["candidates"]) == 1
    candidate = result["candidates"][0]
    assert candidate["status"] == "CANDIDATE_REQUIRES_REVIEW"
    assert set(candidate["evidence_ids"]) == {
        "semantic_scholar:seed-a",
        "semantic_scholar:seed-b",
    }
    assert result["verified_gap"] is False
    assert result["promotion_eligible"] is False
    assert "not verified or novel gaps" in markdown
    assert "Evidence IDs" in markdown


def test_gap_network_is_reset_between_topics_and_depth_is_bounded() -> None:
    provider = FakeCitationProvider(
        results=[_paper("seed-a", "First topic", "")]
    )
    finder = GapFinder(scholar=provider)
    finder.build_network("first topic", depth=0)
    assert set(finder.graph.nodes) == {"semantic_scholar:seed-a"}

    provider.results = [_paper("seed-b", "Second topic", "")]
    finder.build_network("second topic", depth=0)

    assert set(finder.graph.nodes) == {"semantic_scholar:seed-b"}
    with pytest.raises(ValueError, match="depth"):
        finder.build_network("unbounded topic", depth=2)
