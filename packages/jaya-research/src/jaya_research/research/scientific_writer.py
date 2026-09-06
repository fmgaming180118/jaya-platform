"""Evidence-bound scientific draft writer with no fabricated references."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jaya_research.research.academic.contracts import (
    UNSUPPORTED_MARKER,
    normalize_evidence_ids,
    normalize_reference,
    supplied_references,
)


def _render_reference(reference: Any, index: int | None = None) -> str:
    """Render a supplied reference; ``index`` remains for legacy callers only."""
    del index
    record = normalize_reference(reference)
    if record is None:
        raise ValueError("reference requires an explicit evidence ID and title")
    return f"[{record.evidence_id}] {record.citation}"


def _raw_references(*sources: Mapping[str, Any]) -> list[object]:
    combined: list[object] = []
    for source in sources:
        values = source.get("references")
        if isinstance(values, Sequence) and not isinstance(values, str):
            combined.extend(values)
    return combined


def _source_evidence_ids(source: Mapping[str, Any]) -> tuple[str, ...]:
    identifiers: list[object] = []
    raw_ids = source.get("evidence_ids")
    if isinstance(raw_ids, Sequence) and not isinstance(raw_ids, str):
        identifiers.extend(raw_ids)
    elif raw_ids:
        identifiers.append(raw_ids)
    for key in ("dataset_sha256", "result_sha256"):
        if source.get(key):
            identifiers.append(source[key])
    return normalize_evidence_ids(identifiers)


def _claim_evidence_ids(
    source: Mapping[str, Any],
    claim_name: str,
    allowed_ids: Sequence[str],
) -> tuple[str, ...]:
    mapping = source.get("claim_evidence_ids")
    claim_values: object = None
    if isinstance(mapping, Mapping):
        claim_values = mapping.get(claim_name)
    if claim_values is None:
        claim_values = source.get(f"{claim_name}_evidence_ids")
    explicit = normalize_evidence_ids(claim_values)
    if not explicit:
        explicit = _source_evidence_ids(source)
    allowed = set(allowed_ids)
    return tuple(identifier for identifier in explicit if identifier in allowed)


def _render_claim(text: object, evidence_ids: Sequence[str]) -> tuple[str, bool]:
    normalized = str(text or "").strip()
    if not normalized:
        return "Not supplied.", False
    if evidence_ids:
        citations = " ".join(f"[{identifier}]" for identifier in evidence_ids)
        return f"{normalized} {citations}", True
    return f"{normalized} {UNSUPPORTED_MARKER}", False


class ScientificWriter:
    """Draft reports from supplied evidence while preserving its limitations."""

    def generate_paper(
        self,
        hypothesis: dict[str, Any],
        experiment_design: dict[str, Any],
        run_result: dict[str, Any],
        learning_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an IMRAD draft; publication approval is always a human decision."""
        analysis = dict(learning_analysis or {})
        topic = str(hypothesis.get("topic") or "Research topic")
        evidence_kind = str(run_result.get("evidence_kind") or "UNVERIFIED").upper()
        run_status = str(run_result.get("status") or "UNKNOWN")
        reproduction = dict(run_result.get("reproduction") or {})
        reproduced = (
            reproduction.get("reproduced") is True
            and int(reproduction.get("run_count") or 0) >= 2
        )

        reference_records = supplied_references(
            _raw_references(hypothesis, experiment_design, run_result, analysis)
        )
        references = [
            f"[{record.evidence_id}] {record.citation}"
            for record in reference_records
        ]
        evidence_ids = normalize_evidence_ids(
            (
                *(record.evidence_id for record in reference_records),
                *_source_evidence_ids(hypothesis),
                *_source_evidence_ids(experiment_design),
                *_source_evidence_ids(run_result),
                *_source_evidence_ids(analysis),
            )
        )

        if evidence_kind == "SIMULATION":
            paper_status = "SIMULATION_REPORT"
            evidence_label = "deterministic synthetic simulation (non-empirical)"
        elif evidence_kind == "EMPIRICAL" and reproduced:
            paper_status = "EMPIRICAL_DRAFT"
            evidence_label = "reproduced empirical observations requiring human review"
        elif evidence_kind == "EMPIRICAL":
            paper_status = "REPRODUCTION_REQUIRED"
            evidence_label = "single empirical run awaiting independent reproduction"
        else:
            paper_status = "EVIDENCE_INCOMPLETE"
            evidence_label = "unverified evidence"

        claim_specs = (
            ("hypothesis", hypothesis, "statement", hypothesis.get("statement")),
            (
                "knowledge_gap",
                hypothesis,
                "knowledge_gap",
                hypothesis.get("knowledge_gap"),
            ),
            (
                "outcome_summary",
                run_result,
                "outcome_summary",
                run_result.get("outcome_summary"),
            ),
            (
                "analysis_summary",
                analysis,
                "analysis_summary",
                analysis.get("analysis_summary") or analysis.get("summary"),
            ),
            (
                "recommendation",
                analysis,
                "recommendation",
                analysis.get("recommendation"),
            ),
        )
        rendered_claims: dict[str, str] = {}
        claim_support: dict[str, list[str]] = {}
        unsupported_claims: list[str] = []
        supplied_claim_count = 0
        for output_name, source, claim_name, value in claim_specs:
            ids = _claim_evidence_ids(source, claim_name, evidence_ids)
            rendered, supported = _render_claim(value, ids)
            rendered_claims[output_name] = rendered
            claim_support[output_name] = list(ids)
            if str(value or "").strip():
                supplied_claim_count += 1
                if not supported:
                    unsupported_claims.append(output_name)

        supported_claim_count = supplied_claim_count - len(unsupported_claims)
        if evidence_kind not in {"SIMULATION", "EMPIRICAL"} or supported_claim_count == 0:
            synthesis_status = "ABSTAINED_INSUFFICIENT_EVIDENCE"
        elif evidence_kind == "SIMULATION":
            synthesis_status = "SIMULATION_NON_EMPIRICAL_HUMAN_REVIEW_REQUIRED"
        elif unsupported_claims:
            synthesis_status = "PARTIAL_UNSUPPORTED_CLAIMS_HUMAN_REVIEW_REQUIRED"
        else:
            synthesis_status = "HUMAN_REVIEW_REQUIRED"

        variables = dict(experiment_design.get("variables") or {})
        independent = ", ".join(variables.get("independent") or ["unspecified"])
        dependent = ", ".join(variables.get("dependent") or ["unspecified"])
        control = ", ".join(variables.get("control") or ["unspecified"])
        method = str(run_result.get("method") or "not executed")
        p_value = run_result.get("p_value")
        metrics = dict(run_result.get("metrics") or {})
        run_ids = _source_evidence_ids(run_result)
        run_citations = " ".join(f"[{identifier}]" for identifier in run_ids)
        if not run_citations:
            run_citations = UNSUPPORTED_MARKER

        title_prefix = (
            "Simulation Report"
            if paper_status == "SIMULATION_REPORT"
            else "Research Report"
        )
        title = f"{title_prefix}: {topic}"
        abstract = (
            f"This automated draft evaluates this hypothesis: "
            f"{rendered_claims['hypothesis']} The evidence category is "
            f"{evidence_label}. The run status is {run_status} {run_citations}. "
            f"The recommendation is {rendered_claims['recommendation']} This "
            "document is not publication-ready. Human verification of data, "
            "method, claims, references, ethics, and limitations is mandatory."
        )
        introduction = (
            "## 1. Introduction\n\n"
            f"**Topic:** {topic}\n\n"
            f"**Hypothesis:** {rendered_claims['hypothesis']}\n\n"
            f"**Knowledge gap candidate:** {rendered_claims['knowledge_gap']}\n\n"
            f"**Traceable references supplied:** {len(references)}."
        )
        procedure = (
            "\n".join(
                f"{index}. {step}"
                for index, step in enumerate(
                    experiment_design.get("procedure_steps") or [],
                    start=1,
                )
            )
            or "No procedure steps supplied."
        )
        methods = (
            "## 2. Materials and Methods\n\n"
            f"- **Evidence kind:** {evidence_kind}\n"
            f"- **Execution mode:** {experiment_design.get('execution_mode', 'UNKNOWN')}\n"
            f"- **Statistical method:** {method}\n"
            f"- **Independent variable(s):** {independent}\n"
            f"- **Dependent variable(s):** {dependent}\n"
            f"- **Control parameter(s):** {control}\n"
            f"- **Dataset SHA-256:** {run_result.get('dataset_sha256', 'not supplied')}\n"
            f"- **Run evidence IDs:** {run_citations}\n"
            f"- **Reproduced:** {reproduced}\n\n"
            f"### Procedure\n\n{procedure}"
        )
        results = (
            "## 3. Results\n\n"
            f"- **Run status:** {run_status}\n"
            f"- **Evidence kind:** {evidence_kind}\n"
            f"- **p-value:** {p_value if p_value is not None else 'not available'} "
            f"{run_citations}\n"
            f"- **Mean delta:** {metrics.get('mean_delta', 'not available')} "
            f"{run_citations}\n"
            f"- **Cohen d:** {metrics.get('effect_size_cohen_d', 'not available')} "
            f"{run_citations}\n"
            f"- **Promotion eligible:** {run_result.get('promotion_eligible', False)}\n"
            f"- **Result support:** {run_citations}\n\n"
            f"{rendered_claims['outcome_summary']}"
        )
        discussion = (
            "## 4. Discussion and Limitations\n\n"
            f"{rendered_claims['analysis_summary']}\n\n"
            "The result must be interpreted within supplied provenance, sample "
            "size, statistical assumptions, and reproduction status. Simulation "
            "results are engineering evidence only and cannot establish an "
            "empirical scientific claim. Reproduced empirical output still "
            "requires independent human and domain-expert review."
        )
        authors = list(
            hypothesis.get("authors")
            or ["JAYA Research automated draft -- human authorship review required"]
        )
        coverage = (
            supported_claim_count / supplied_claim_count
            if supplied_claim_count
            else 0.0
        )
        return {
            "paper_id": (
                "PAPER-"
                + datetime.now(timezone.utc).strftime("%Y%m%d")
                + "-"
                + str(hypothesis.get("hypothesis_id") or "UNKNOWN")[-8:]
            ),
            "paper_status": paper_status,
            "synthesis_status": synthesis_status,
            "publication_ready": False,
            "human_review_required": True,
            "evidence_kind": evidence_kind,
            "title": title,
            "authors": authors,
            "abstract": abstract,
            "sections": {
                "introduction": introduction,
                "methods": methods,
                "results": results,
                "discussion": discussion,
            },
            "references": references,
            "evidence_ids": list(evidence_ids),
            "claim_evidence_ids": claim_support,
            "unsupported_claims": unsupported_claims,
            "citation_coverage": {
                "supported_claims": supported_claim_count,
                "supplied_claims": supplied_claim_count,
                "ratio": round(coverage, 4),
            },
            "limitations": [
                "Automated draft; human scientific review is mandatory.",
                "Claims are limited to explicitly supplied evidence IDs.",
                "Unsupported claims are labelled and must not be treated as findings.",
                "Simulation is not empirical evidence.",
                "Reproduction does not grant publication readiness.",
            ],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def export_markdown(
        self,
        paper: dict[str, Any],
        output_path: Path | None = None,
    ) -> str:
        """Render a paper dictionary into Markdown."""
        content = "\n\n".join(
            [
                f"# {paper.get('title', 'Research Report')}",
                f"**Status:** {paper.get('paper_status', 'UNKNOWN')}",
                "**Publication ready:** No -- human scientific review required.",
                f"**Authors:** {', '.join(paper.get('authors', []))}",
                f"**Date:** {str(paper.get('timestamp', ''))[:10]}",
                "---",
                "## Abstract",
                str(paper.get("abstract") or ""),
                "---",
                str(paper.get("sections", {}).get("introduction") or ""),
                str(paper.get("sections", {}).get("methods") or ""),
                str(paper.get("sections", {}).get("results") or ""),
                str(paper.get("sections", {}).get("discussion") or ""),
                "---",
                "## References",
                "\n".join(paper.get("references") or []) or "No references supplied.",
                "## Limitations",
                "\n".join(f"- {item}" for item in paper.get("limitations") or []),
            ]
        )
        if output_path is not None:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return content

    def export_latex(
        self,
        paper: dict[str, Any],
        output_path: Path | None = None,
    ) -> str:
        """Render a minimal LaTeX research draft without adding references."""
        sections = paper.get("sections") or {}
        references = paper.get("references") or []
        latex_authors = " \\and ".join(paper.get("authors", []))
        bibliography = "\n".join(
            f"\\bibitem{{supplied{index}}} {reference}"
            for index, reference in enumerate(references, start=1)
        )
        bibliography_block = (
            "\\begin{thebibliography}{99}\n"
            + bibliography
            + "\n\\end{thebibliography}"
            if bibliography
            else "% No references supplied."
        )
        content = f"""\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{hyperref}}
\\title{{{paper.get("title", "Research Report")}}}
\\author{{{latex_authors}}}
\\date{{\\today}}
\\begin{{document}}
\\maketitle
\\textbf{{Not publication-ready; human scientific review required.}}
\\begin{{abstract}}
{paper.get("abstract", "")}
\\end{{abstract}}
\\section{{Introduction}}
{str(sections.get("introduction") or "").replace("## 1. Introduction", "").strip()}
\\section{{Materials and Methods}}
{str(sections.get("methods") or "").replace("## 2. Materials and Methods", "").strip()}
\\section{{Results}}
{str(sections.get("results") or "").replace("## 3. Results", "").strip()}
\\section{{Discussion and Limitations}}
{str(sections.get("discussion") or "").replace("## 4. Discussion and Limitations", "").strip()}
{bibliography_block}
\\end{{document}}
"""
        if output_path is not None:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return content
