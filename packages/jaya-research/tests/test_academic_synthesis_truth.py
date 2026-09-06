"""Offline acceptance tests for truthful Phase A academic synthesis."""

from __future__ import annotations

from jaya_research.research.academic.contracts import AcademicGenerationStatus
from jaya_research.research.academic.drafter import ThesisDrafter
from jaya_research.research.academic.editor import AcademicEditor
from jaya_research.research.academic.reviewer import ReviewerAgent
from jaya_research.research.scientific_writer import ScientificWriter


class StaticProvider:
    def __init__(self, response: str = "", error: Exception | None = None) -> None:
        self.response = response
        self.error = error
        self.prompts: list[str] = []

    def generate_completion(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self.error is not None:
            raise self.error
        return self.response


def _paper(evidence_id: str = "SRC-1") -> dict[str, object]:
    return {
        "evidence_id": evidence_id,
        "title": "Measured retrieval benchmark",
        "authors": ["A. Researcher"],
        "published": "2025",
        "source": "Evidence Journal",
        "url": "https://evidence.invalid/record",
        "summary": "The supplied study reports a bounded retrieval benchmark.",
    }


def test_literature_review_uses_only_supplied_bibliography_and_citations() -> None:
    provider = StaticProvider(
        "## Introduction\n\n"
        "The bounded benchmark reports a measured comparison [SRC-1].\n\n"
        "## Conclusion\n\n"
        "A broader claim still needs verification.\n\n"
        "## References\n\n"
        "[FAKE-9] Fabricated Author. Fabricated Paper."
    )
    result = ThesisDrafter(writer=provider).generate_literature_review_result(
        "Bounded retrieval",
        [_paper()],
    )

    assert result.status is AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED
    assert result.publication_ready is False
    assert result.human_review_required is True
    assert result.evidence_ids == ("SRC-1",)
    assert result.content.count("## References") == 1
    assert "[SRC-1] A. Researcher. 2025. Measured retrieval benchmark" in result.content
    assert "FAKE-9" not in result.content
    assert "Fabricated" not in result.content
    assert "A broader claim still needs verification. [UNSUPPORTED:" in result.content


def test_missing_traceable_papers_abstains_without_loading_provider() -> None:
    provider_loads = 0

    def factory():
        nonlocal provider_loads
        provider_loads += 1
        return StaticProvider("must not run")

    drafter = ThesisDrafter(provider_factory=factory)
    assert provider_loads == 0

    result = drafter.generate_literature_review_result(
        "Unverified topic",
        [{"title": "A title without an evidence identifier"}],
    )

    assert result.status is AcademicGenerationStatus.ABSTAINED_INSUFFICIENT_EVIDENCE
    assert result.evidence_ids == ()
    assert "ABSTAINED" in result.content
    assert "References" not in result.content
    assert provider_loads == 0


def test_all_academic_agents_construct_without_loading_provider() -> None:
    provider_loads = 0

    def factory():
        nonlocal provider_loads
        provider_loads += 1
        return StaticProvider("unused")

    ThesisDrafter(provider_factory=factory)
    ReviewerAgent(provider_factory=factory)
    AcademicEditor(provider_factory=factory)

    assert provider_loads == 0


def test_provider_failure_is_typed_and_does_not_fabricate_text() -> None:
    provider = StaticProvider(error=RuntimeError("secret provider body"))
    result = ThesisDrafter(writer=provider).generate_literature_review_result(
        "Measured retrieval",
        [_paper()],
    )

    assert result.status is AcademicGenerationStatus.PROVIDER_UNAVAILABLE
    assert result.provider_error_code == "RuntimeError"
    assert "secret provider body" not in result.content
    assert "PROVIDER_UNAVAILABLE" in result.content
    assert "[SRC-1]" in result.content


def test_unknown_provider_citation_is_rejected_without_fake_bibliography() -> None:
    provider = StaticProvider(
        "## Introduction\n\nA confident but untraceable claim [INVENTED-2]."
    )
    result = ThesisDrafter(writer=provider).generate_literature_review_result(
        "Measured retrieval",
        [_paper()],
    )

    assert result.status is AcademicGenerationStatus.INVALID_PROVIDER_OUTPUT
    assert "INVENTED-2" not in result.content
    assert "[SRC-1]" in result.content
    assert result.publication_ready is False


def test_editor_rejects_changed_structure_citation_or_bibliography() -> None:
    original = (
        "# Results\n\nMeasured result [SRC-1].\n\n"
        "## References\n\n[SRC-1] Supplied study."
    )
    provider = StaticProvider(
        "# Renamed Results\n\nAltered result [NEW-9].\n\n"
        "## References\n\n[NEW-9] Fabricated study."
    )
    result = AcademicEditor(editor=provider).revise_chapter_result(
        original,
        "Improve clarity.",
    )

    assert result.status is AcademicGenerationStatus.INVALID_PROVIDER_OUTPUT
    assert result.content == original
    assert result.provider_error_code == "structure_changed"
    assert "NEW-9" not in result.content


def test_editor_accepts_revision_only_when_structure_and_sources_survive() -> None:
    original = (
        "# Results\n\nMeasured result [SRC-1].\n\n"
        "## Discussion\n\nInitial interpretation [SRC-1].\n\n"
        "## References\n\n[SRC-1] Supplied study."
    )
    revised = (
        "# Results\n\nThe measured result is stated more precisely [SRC-1].\n\n"
        "## Discussion\n\nInitial interpretation remains bounded [SRC-1].\n\n"
        "This new extrapolation needs review.\n\n"
        "## References\n\n[SRC-1] Supplied study."
    )
    result = AcademicEditor(editor=StaticProvider(revised)).revise_chapter_result(
        original,
        "Improve clarity without changing evidence.",
    )

    assert result.status is AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED
    assert "# Results" in result.content
    assert "## Discussion" in result.content
    assert result.content.endswith("[SRC-1] Supplied study.")
    assert result.content.count("[SRC-1]") == 3
    assert "This new extrapolation needs review. [UNSUPPORTED:" in result.content


def test_editor_provider_failure_preserves_original_exactly() -> None:
    original = "# Methods\n\nA supplied procedure [METHOD-1]."
    result = AcademicEditor(
        editor=StaticProvider(error=ConnectionError("offline"))
    ).revise_chapter_result(original, "Clarify the prose.")

    assert result.status is AcademicGenerationStatus.PROVIDER_UNAVAILABLE
    assert result.content == original
    assert result.provider_error_code == "ConnectionError"


def test_reviewer_never_accepts_invented_citations_or_bibliography() -> None:
    provider = StaticProvider(
        "## Overall Assessment\n\nMajor revision [SRC-1].\n\n"
        "## References\n\n[FAKE-1] Fabricated review source."
    )
    result = ReviewerAgent(critic=provider).critique_chapter_result(
        "# Introduction\n\nSupplied observation [SRC-1].",
        "Measured retrieval",
    )

    assert result.status is AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED
    assert "FAKE-1" not in result.content
    assert "References" not in result.content
    assert result.publication_ready is False
    assert "not a publication-readiness decision" in result.content


def test_scientific_claim_coverage_is_explicit_and_unmapped_claim_abstains() -> None:
    hypothesis = {
        "hypothesis_id": "HYP-1",
        "topic": "Measured retrieval",
        "statement": "The treatment changes measured retrieval.",
        "knowledge_gap": "The broader population effect is unknown.",
        "references": [_paper()],
        "claim_evidence_ids": {"statement": ["SRC-1"]},
    }
    run_result = {
        "status": "COMPLETED_EMPIRICAL",
        "evidence_kind": "EMPIRICAL",
        "dataset_sha256": "d" * 64,
        "result_sha256": "r" * 64,
        "method": "Welch t-test",
        "metrics": {"mean_delta": 1.0, "effect_size_cohen_d": 0.8},
        "p_value": 0.01,
        "outcome_summary": "The supplied observations differ in this run.",
        "reproduction": {"reproduced": True, "run_count": 2},
    }
    analysis = {
        "analysis_summary": "The measured effect warrants bounded follow-up.",
        "recommendation": "HOLD_FOR_HUMAN_REVIEW",
        "evidence_ids": ["SRC-1"],
    }

    paper = ScientificWriter().generate_paper(
        hypothesis,
        {"execution_mode": "EMPIRICAL"},
        run_result,
        analysis,
    )

    assert paper["paper_status"] == "EMPIRICAL_DRAFT"
    assert paper["publication_ready"] is False
    assert paper["human_review_required"] is True
    assert paper["claim_evidence_ids"]["hypothesis"] == ["SRC-1"]
    assert "knowledge_gap" in paper["unsupported_claims"]
    assert "[UNSUPPORTED: no supplied evidence ID]" in paper["sections"]["introduction"]
    assert paper["references"] == [
        "[SRC-1] A. Researcher. 2025. Measured retrieval benchmark. "
        "Evidence Journal. https://evidence.invalid/record"
    ]
    assert "publication-ready" in paper["abstract"]


def test_scientific_writer_drops_untraceable_reference_instead_of_placeholder() -> None:
    paper = ScientificWriter().generate_paper(
        {
            "topic": "Unverified synthesis",
            "statement": "A broad claim",
            "references": [{"title": "Missing identifier"}],
        },
        {},
        {"evidence_kind": "UNVERIFIED"},
    )

    assert paper["references"] == []
    assert paper["synthesis_status"] == "ABSTAINED_INSUFFICIENT_EVIDENCE"
    assert "Untitled source" not in str(paper)
    assert "Missing identifier" not in str(paper)
