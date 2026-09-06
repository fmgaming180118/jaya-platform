"""Academic revision with citation and structure preservation gates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence

from jaya_research.research.academic.contracts import (
    AcademicGenerationResult,
    AcademicGenerationStatus,
    AcademicTextProvider,
    ProviderFactory,
    annotate_unsupported_claims,
    call_provider,
    default_provider_factory,
    extract_citation_ids,
    headings,
    normalize_evidence_ids,
    reference_section,
    safe_provider_error_code,
    unknown_citation_ids,
)


class AcademicEditor:
    """Revise supplied prose, falling back to the original on trust failures."""

    def __init__(
        self,
        editor: AcademicTextProvider | None = None,
        *,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self.editor = editor
        self._provider_factory = provider_factory or default_provider_factory

    def _provider(self) -> AcademicTextProvider:
        if self.editor is None:
            self.editor = self._provider_factory()
        return self.editor

    def revise_chapter_result(
        self,
        draft: str,
        critique: str,
        context: str = "",
        *,
        evidence_ids: Sequence[str] = (),
    ) -> AcademicGenerationResult:
        """Revise a chapter only if provider output preserves trust invariants."""
        if not draft.strip():
            raise ValueError("draft must not be empty")
        if not critique.strip():
            raise ValueError("critique must not be empty")

        original_citations = extract_citation_ids(draft)
        allowed_ids = normalize_evidence_ids((*evidence_ids, *original_citations))
        original_headings = headings(draft)
        original_bibliography = reference_section(draft)
        prompt = (
            "Revise the supplied academic draft for clarity and flow. Preserve "
            "every heading in the exact original order and preserve every existing "
            "citation marker and the complete References/Bibliography section "
            "verbatim. Do not add citations, sources, bibliography entries, facts, "
            "or publication-readiness claims. Use only ALLOWED_EVIDENCE_IDS. Every "
            "new substantive assertion without one of those IDs must end with "
            "[UNSUPPORTED: no supplied evidence ID]. Return the complete revised "
            "Markdown chapter and nothing else.\n\n"
            f"ALLOWED_EVIDENCE_IDS: {list(allowed_ids)}\n"
            f"CONTEXT: {context[:2000]}\n"
            f"CRITIQUE: {critique[:4000]}\n"
            f"ORIGINAL DRAFT:\n{draft[:16000]}"
        )
        try:
            generated = call_provider(self._provider(), prompt)
        except Exception as error:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.PROVIDER_UNAVAILABLE,
                content=draft,
                evidence_ids=allowed_ids,
                provider_error_code=safe_provider_error_code(error),
            )

        error_code = self._validation_error(
            generated,
            original_headings=original_headings,
            original_citations=original_citations,
            allowed_ids=allowed_ids,
            original_bibliography=original_bibliography,
        )
        if error_code is not None:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.INVALID_PROVIDER_OUTPUT,
                content=draft,
                evidence_ids=allowed_ids,
                provider_error_code=error_code,
            )

        grounded, unsupported_count = annotate_unsupported_claims(
            generated,
            allowed_ids,
        )
        return AcademicGenerationResult(
            status=AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED,
            content=grounded,
            evidence_ids=allowed_ids,
            unsupported_claim_count=unsupported_count,
        )

    @staticmethod
    def _validation_error(
        generated: str,
        *,
        original_headings: tuple[str, ...],
        original_citations: tuple[str, ...],
        allowed_ids: tuple[str, ...],
        original_bibliography: str,
    ) -> str | None:
        if headings(generated) != original_headings:
            return "structure_changed"
        if unknown_citation_ids(generated, allowed_ids):
            return "unknown_citation_id"
        generated_citations = Counter(extract_citation_ids(generated))
        original_counts = Counter(original_citations)
        if any(
            generated_citations[identifier] < count
            for identifier, count in original_counts.items()
        ):
            return "original_citation_removed"
        generated_bibliography = reference_section(generated)
        if generated_bibliography != original_bibliography:
            return "bibliography_changed"
        return None

    def revise_chapter(
        self,
        draft: str,
        critique: str,
        context: str = "",
    ) -> str:
        """Compatibility wrapper returning the accepted or original draft."""
        return self.revise_chapter_result(draft, critique, context).content
