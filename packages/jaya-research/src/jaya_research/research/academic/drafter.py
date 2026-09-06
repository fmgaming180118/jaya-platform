"""Evidence-bound thesis drafting helpers.

Language-model providers are optional and lazy.  Their output is never trusted
to create bibliography entries or citation identifiers.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from typing import Any

from jaya_research.research.academic.contracts import (
    AcademicGenerationResult,
    AcademicGenerationStatus,
    AcademicTextProvider,
    ProviderFactory,
    annotate_unsupported_claims,
    call_provider,
    canonical_bibliography,
    default_provider_factory,
    normalize_evidence_ids,
    safe_provider_error_code,
    strip_generated_bibliography,
    supplied_references,
    unknown_citation_ids,
)


class ThesisDrafter:
    """Draft academic material while keeping evidence provenance explicit."""

    def __init__(
        self,
        writer: AcademicTextProvider | None = None,
        *,
        provider_factory: ProviderFactory | None = None,
    ) -> None:
        self.writer = writer
        self._provider_factory = provider_factory or default_provider_factory

    def _provider(self) -> AcademicTextProvider:
        if self.writer is None:
            self.writer = self._provider_factory()
        return self.writer

    def generate_literature_review_result(
        self,
        topic: str,
        papers: Sequence[dict[str, Any]],
    ) -> AcademicGenerationResult:
        """Return a grounded literature synthesis plus canonical references."""
        normalized_topic = " ".join(topic.split())
        if not normalized_topic:
            raise ValueError("topic must not be empty")

        references = supplied_references(papers)
        evidence_ids = tuple(record.evidence_id for record in references)
        bibliography = canonical_bibliography(references)
        if not references:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.ABSTAINED_INSUFFICIENT_EVIDENCE,
                content=(
                    "## Literature Review\n\n"
                    "[ABSTAINED: no paper with an explicit supplied evidence ID "
                    "and title was available.]"
                ),
            )

        paper_by_id: dict[str, dict[str, str]] = {}
        allowed = set(evidence_ids)
        for paper in papers:
            records = supplied_references((paper,))
            if not records or records[0].evidence_id not in allowed:
                continue
            record = records[0]
            if record.evidence_id in paper_by_id:
                continue
            paper_by_id[record.evidence_id] = {
                "evidence_id": record.evidence_id,
                "title": str(paper.get("title") or ""),
                "published": str(paper.get("published") or paper.get("year") or ""),
                "source": str(paper.get("source") or ""),
                "summary": str(paper.get("summary") or paper.get("abstract") or ""),
            }

        prompt = (
            "Write a literature review in Markdown using ONLY the supplied records. "
            "Every substantive factual claim must end with one or more exact "
            "citation markers from ALLOWED_EVIDENCE_IDS. If a claim cannot be "
            "supported, append [UNSUPPORTED: no supplied evidence ID]. Do not "
            "create a References/Bibliography section, authors, titles, years, "
            "links, identifiers, or publication-readiness claims. Include "
            "Introduction, Thematic Analysis, Gaps Requiring Verification, and "
            "Conclusion. Treat an absent observation as unknown, never as proof.\n\n"
            f"TOPIC: {normalized_topic}\n"
            f"ALLOWED_EVIDENCE_IDS: {json.dumps(evidence_ids)}\n"
            f"RECORDS: {json.dumps(list(paper_by_id.values()), ensure_ascii=False)}"
        )
        try:
            generated = call_provider(self._provider(), prompt)
        except Exception as error:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.PROVIDER_UNAVAILABLE,
                content=(
                    "## Literature Review\n\n"
                    "[PROVIDER_UNAVAILABLE: synthesis was not generated; supplied "
                    "references remain available for human review.]\n\n"
                    f"## References\n\n{bibliography}"
                ),
                evidence_ids=evidence_ids,
                provider_error_code=safe_provider_error_code(error),
            )

        generated = strip_generated_bibliography(generated)
        unknown = unknown_citation_ids(generated, evidence_ids)
        if unknown:
            return AcademicGenerationResult(
                status=AcademicGenerationStatus.INVALID_PROVIDER_OUTPUT,
                content=(
                    "## Literature Review\n\n"
                    "[ABSTAINED: the text provider emitted citation IDs outside "
                    "the supplied evidence set.]\n\n"
                    f"## References\n\n{bibliography}"
                ),
                evidence_ids=evidence_ids,
                provider_error_code="unknown_citation_id",
            )

        grounded, unsupported_count = annotate_unsupported_claims(
            generated,
            evidence_ids,
        )
        content = f"{grounded}\n\n## References\n\n{bibliography}"
        return AcademicGenerationResult(
            status=AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED,
            content=content,
            evidence_ids=evidence_ids,
            unsupported_claim_count=unsupported_count,
        )

    def generate_literature_review(
        self,
        topic: str,
        papers: Sequence[dict[str, Any]],
    ) -> str:
        """Compatibility wrapper returning the bounded Markdown content."""
        return self.generate_literature_review_result(topic, papers).content

    def generate_outline_result(self, topic: str) -> AcademicGenerationResult:
        """Create a deterministic planning scaffold without making claims."""
        normalized_topic = " ".join(topic.split())
        if not normalized_topic:
            raise ValueError("topic must not be empty")
        content = f"""# Thesis Proposal Outline: {normalized_topic}

> Planning scaffold only. It contains no research findings or bibliography and requires human review.

## 1. Introduction

- Define the background using supplied, citable evidence.
- State the problem, objectives, scope, and falsifiable research questions.

## 2. Literature Review

- Synthesize only traceable sources and attach evidence IDs to substantive claims.
- Record unresolved gaps as candidates requiring verification.

## 3. Methodology

- Specify data provenance, license, sampling, controls, metrics, and reproduction protocol.

## 4. Expected Results

- Describe evaluation criteria without asserting an outcome before execution.

## 5. References

- Add only sources verified and supplied by the researcher.
"""
        return AcademicGenerationResult(
            status=AcademicGenerationStatus.COMPLETE_HUMAN_REVIEW_REQUIRED,
            content=content.rstrip(),
        )

    def generate_outline(self, topic: str) -> str:
        return self.generate_outline_result(topic).content

    def export_to_latex(
        self,
        markdown_content: str,
        title: str = "Thesis Draft",
    ) -> str:
        """Convert basic Markdown headings into a review-labelled LaTeX draft."""
        lines: list[str] = []
        for line in markdown_content.splitlines():
            stripped = line.strip()
            if stripped.startswith("### "):
                lines.append(f"\\subsection{{{stripped[4:]}}}")
            elif stripped.startswith("## "):
                lines.append(f"\\section{{{stripped[3:]}}}")
            elif stripped.startswith("# "):
                lines.append(f"\\chapter{{{stripped[2:]}}}")
            else:
                lines.append(line)
        latex_body = "\n".join(lines)
        return rf"""
\documentclass[12pt, a4paper]{{report}}
\usepackage{{hyperref}}
\usepackage[utf8]{{inputenc}}
\title{{{title}}}
\author{{JAYA Research automated draft -- human authorship review required}}
\date{{\today}}
\begin{{document}}
\maketitle
\textbf{{Status: Human scientific review required; not publication-ready.}}
\tableofcontents
{latex_body}
\end{{document}}
""".strip()

    def generate_system_design_chapter(
        self,
        topic: str,
        system_spec: str,
        diagram_types: Sequence[str] = ("usecase", "class"),
        *,
        evidence_ids: Sequence[str] = (),
        uml_factory: Callable[[], Any] | None = None,
    ) -> str:
        """Generate diagrams while clearly labelling unsupported explanations."""
        from jaya_research.research.uml_generator import UMLGenerator

        allowed_ids = normalize_evidence_ids(evidence_ids)
        uml_generator = (uml_factory or UMLGenerator)()
        chapter = (
            "# Bab III: Analisis dan Perancangan Sistem\n\n"
            "## 3.1 Deskripsi Umum Sistem\n\n"
            f"Topik Penelitian: {topic}\n\nSpesifikasi Kebutuhan Sistem:\n{system_spec}"
        )
        if not allowed_ids:
            chapter += "\n\n[UNSUPPORTED: no supplied evidence ID]"

        for diagram_type in diagram_types:
            type_label = {
                "usecase": "Use Case Diagram",
                "class": "Class Diagram",
                "sequence": "Sequence Diagram",
                "activity": "Activity Diagram",
            }.get(diagram_type, "UML Diagram")
            chapter += f"\n\n## {type_label}\n\n"
            try:
                code, url = uml_generator.generate_diagram(system_spec, diagram_type)
            except Exception as error:
                chapter += (
                    "[DIAGRAM_UNAVAILABLE: generation failed; no diagram claim was "
                    f"accepted. Error type: {type(error).__name__}]"
                )
                continue

            chapter += f"![{type_label}]({url})\n\n```plantuml\n{code}\n```"
            if not allowed_ids:
                chapter += "\n\n[UNSUPPORTED: no supplied evidence ID]"
                continue
            prompt = (
                "Explain this supplied system diagram in Indonesian academic prose. "
                "Use only these exact evidence markers and add one to every factual "
                f"claim: {list(allowed_ids)}. Do not add references.\n\n"
                f"SPECIFICATION:\n{system_spec}\n\nPLANTUML:\n{code}"
            )
            try:
                explanation = strip_generated_bibliography(
                    call_provider(self._provider(), prompt)
                )
            except Exception:
                chapter += "\n\n[PROVIDER_UNAVAILABLE: explanation was not generated.]"
                continue
            if unknown_citation_ids(explanation, allowed_ids):
                chapter += "\n\n[ABSTAINED: explanation contained an unknown citation ID.]"
                continue
            explanation, _ = annotate_unsupported_claims(explanation, allowed_ids)
            chapter += f"\n\n### Penjelasan {type_label}\n\n{explanation}"
        return chapter
