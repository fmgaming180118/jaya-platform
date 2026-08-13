"""Fail-closed academic review helpers with traceable citation use."""

from __future__ import annotations

import re
from collections.abc import Sequence

from research.academic.contracts import (
    AcademicGenerationResult,
    AcademicGenerationStatus,
    AcademicTextProvider,
    ProviderFactory,
    annotate_unsupported_claims,
    call_provider,
    default_provider_factory,
    extract_citation_ids,
    normalize_evidence_ids,
    safe_provider_error_code,
    strip_generated_bibliography,
    unknown_citation_ids,
)


class ReviewerAgent:
    """Critique supplied text without inventing evidence or approval status."""

    def __init__(
        self,
        critic: AcademicTextProvider | None = None,
        *,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self.critic = critic
        self._provider_factory = provider_factory or default_provider_factory

    def _provider(self) -> AcademicTextProvider:
        if self.critic is None:
            self.critic = self._provider_factory()
        return self.critic

    def critique_chapter_result(
        self,
        chapter_content: str,
        topic: str,
        *,
        evidence_ids: Sequence[str] = (),
    ) -> AcademicGenerationResult:
        """Return a bounded critique whose source markers come from the caller."""
        if not chapter_content.strip():
            raise ValueError("chapter_content must not be empty")
        if not topic.strip():
            raise ValueError("topic must not be empty")
        allowed_ids = normalize_evidence_ids(
            (*evidence_ids, *extract_citation_ids(chapter_content))
        )
        prompt = (
            "Act as a strict academic reviewer. Review only the supplied draft. "
            "Do not add facts, sources, citations, bibliography entries, or claim "
            "that the work is publication-ready. A Pass label may only mean that "
            "this draft has no issue detected by this bounded review; human/domain "
            "review remains mandatory. Every substantive assertion must cite an "
            "exact ALLOWED_EVIDENCE_ID or end with [UNSUPPORTED: no supplied "
            "evidence ID]. If no IDs are allowed, mark every evidentiary assertion "
            "unsupported. Produce Overall Assessment, Weaknesses, Specific "
            "Recommendations, and Missing Perspectives.\n\n"
            f"TOPIC: {topic.strip()}\n"
            f"ALLOWED_EVIDENCE_IDS: {list(allowed_ids)}\n"
            f"DRAFT:\n{chapter_content[:8000]}"
        )
        try:
            generated = call_provider(self._provider(), prompt)
        except Exception as error:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.PROVIDER_UNAVAILABLE,
                content=(
                    "## Review Status\n\n"
                    "[PROVIDER_UNAVAILABLE: no automated critique was accepted. "
                    "Human academic review is required.]"
                ),
                evidence_ids=allowed_ids,
                provider_error_code=safe_provider_error_code(error),
            )

        generated = strip_generated_bibliography(generated)
        if unknown_citation_ids(generated, allowed_ids):
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.INVALID_PROVIDER_OUTPUT,
                content=(
                    "## Review Status\n\n"
                    "[ABSTAINED: reviewer output used a citation ID that was not "
                    "present in the supplied draft or evidence list.]"
                ),
                evidence_ids=allowed_ids,
                provider_error_code="unknown_citation_id",
            )

        grounded, unsupported_count = annotate_unsupported_claims(
            generated,
            allowed_ids,
        )
        banner = (
            "> Automated bounded review; human and domain-expert review remains "
            "mandatory. This is not a publication-readiness decision."
        )
        return AcademicGenerationResult(
            status=AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED,
            content=f"{banner}\n\n{grounded}",
            evidence_ids=allowed_ids,
            unsupported_claim_count=unsupported_count,
        )

    def critique_chapter(self, chapter_content: str, topic: str) -> str:
        """Compatibility wrapper returning Markdown rather than the typed result."""
        return self.critique_chapter_result(chapter_content, topic).content

    def generate_defense_questions_result(
        self,
        topic: str,
        abstract: str,
        *,
        evidence_ids: Sequence[str] = (),
    ) -> AcademicGenerationResult:
        """Generate questions only; statements and new references are forbidden."""
        if not topic.strip() or not abstract.strip():
            raise ValueError("topic and abstract must not be empty")
        allowed_ids = normalize_evidence_ids(
            (*evidence_ids, *extract_citation_ids(abstract))
        )
        prompt = (
            "Generate exactly five thesis-defense QUESTIONS based only on the "
            "supplied topic and abstract. Each line must end with '?'. Do not "
            "answer the questions, make factual assertions, introduce citations, "
            "or add a bibliography. Challenge methodology, validity, limitations, "
            "and contribution.\n\n"
            f"TOPIC: {topic.strip()}\nABSTRACT:\n{abstract[:8000]}"
        )
        try:
            generated = strip_generated_bibliography(
                call_provider(self._provider(), prompt)
            )
        except Exception as error:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.PROVIDER_UNAVAILABLE,
                content="[PROVIDER_UNAVAILABLE: defense questions were not generated.]",
                evidence_ids=allowed_ids,
                provider_error_code=safe_provider_error_code(error),
            )
        if extract_citation_ids(generated) or unknown_citation_ids(generated, allowed_ids):
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.INVALID_PROVIDER_OUTPUT,
                content="[ABSTAINED: defense-question output introduced citations.]",
                evidence_ids=allowed_ids,
                provider_error_code="citation_in_question_output",
            )

        questions = self._parse_questions(generated)
        if len(questions) != 5:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.INVALID_PROVIDER_OUTPUT,
                content="[ABSTAINED: provider did not return exactly five questions.]",
                evidence_ids=allowed_ids,
                provider_error_code="invalid_question_count",
            )
        return AcademicGenerationResult(
            status=AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED,
            content="\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1)),
            evidence_ids=allowed_ids,
        )

    def generate_defense_questions(self, topic: str, abstract: str) -> list[str]:
        result = self.generate_defense_questions_result(topic, abstract)
        if result.status is not AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED:
            return []
        return self._parse_questions(result.content)

    @staticmethod
    def _parse_questions(content: str) -> list[str]:
        questions: list[str] = []
        for raw_line in content.splitlines():
            line = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", raw_line).strip()
            if line.endswith("?"):
                questions.append(line)
        return questions
