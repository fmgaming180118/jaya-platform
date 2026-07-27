"""Evidence-bound scientific draft writer with no fabricated references."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _render_reference(reference: Any, index: int) -> str:
    if isinstance(reference, str):
        return f"[{index}] {reference}"
    if isinstance(reference, dict):
        title = str(reference.get("title") or "Untitled source")
        locator = str(reference.get("uri") or reference.get("path") or "")
        source_hash = str(reference.get("sha256") or "")
        suffix = f" — {locator}" if locator else ""
        if source_hash:
            suffix += f" (sha256: {source_hash})"
        return f"[{index}] {title}{suffix}"
    raise ValueError("References must be strings or mappings")


class ScientificWriter:
    """Draft reports from supplied evidence while preserving its limitations."""

    def generate_paper(
        self,
        hypothesis: dict[str, Any],
        experiment_design: dict[str, Any],
        run_result: dict[str, Any],
        learning_analysis: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Build an IMRAD-shaped draft with explicit evidence status."""
        analysis = dict(learning_analysis or {})
        topic = str(hypothesis.get("topic") or "Research topic")
        statement = str(
            hypothesis.get("statement") or "No hypothesis statement was supplied."
        )
        evidence_kind = str(run_result.get("evidence_kind") or "UNVERIFIED")
        run_status = str(run_result.get("status") or "UNKNOWN")
        reproduction = dict(run_result.get("reproduction") or {})
        reproduced = (
            reproduction.get("reproduced") is True
            and int(reproduction.get("run_count") or 0) >= 2
        )
        references_raw = list(
            hypothesis.get("references")
            or experiment_design.get("references")
            or run_result.get("references")
            or []
        )
        references = [
            _render_reference(reference, index)
            for index, reference in enumerate(references_raw, start=1)
        ]

        if evidence_kind == "SIMULATION":
            paper_status = "SIMULATION_REPORT"
            evidence_label = "deterministic synthetic simulation"
        elif evidence_kind == "EMPIRICAL" and reproduced:
            paper_status = "EMPIRICAL_DRAFT"
            evidence_label = "reproduced empirical observations"
        elif evidence_kind == "EMPIRICAL":
            paper_status = "REPRODUCTION_REQUIRED"
            evidence_label = "single empirical run awaiting independent reproduction"
        else:
            paper_status = "EVIDENCE_INCOMPLETE"
            evidence_label = "unverified evidence"

        variables = dict(experiment_design.get("variables") or {})
        independent = ", ".join(variables.get("independent") or ["unspecified"])
        dependent = ", ".join(variables.get("dependent") or ["unspecified"])
        control = ", ".join(variables.get("control") or ["unspecified"])
        method = str(run_result.get("method") or "not executed")
        p_value = run_result.get("p_value")
        metrics = dict(run_result.get("metrics") or {})
        recommendation = str(analysis.get("recommendation") or "HOLD")
        analysis_summary = str(
            analysis.get("analysis_summary")
            or analysis.get("summary")
            or "No evidence interpretation was supplied."
        )

        title_prefix = (
            "Simulation Report"
            if paper_status == "SIMULATION_REPORT"
            else "Research Report"
        )
        title = f"{title_prefix}: {topic}"
        abstract = (
            f"This automated draft evaluates the hypothesis '{statement}' using "
            f"{evidence_label}. The run status is {run_status}. "
            f"The recommendation is {recommendation}. This document is not "
            "publication-ready until a human verifies the data, method, claims, "
            "references, and limitations."
        )
        introduction = (
            "## 1. Introduction\n\n"
            f"**Topic:** {topic}\n\n"
            f"**Hypothesis:** {statement}\n\n"
            f"**Knowledge gap:** {hypothesis.get('knowledge_gap', 'Not supplied.')}\n\n"
            f"**Evidence sources supplied:** {len(references)}."
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
            f"- **Reproduced:** {reproduced}\n\n"
            f"### Procedure\n\n{procedure}"
        )
        results = (
            "## 3. Results\n\n"
            f"- **Run status:** {run_status}\n"
            f"- **Evidence kind:** {evidence_kind}\n"
            f"- **p-value:** {p_value if p_value is not None else 'not available'}\n"
            f"- **Mean delta:** {metrics.get('mean_delta', 'not available')}\n"
            f"- **Cohen d:** {metrics.get('effect_size_cohen_d', 'not available')}\n"
            f"- **Promotion eligible:** {run_result.get('promotion_eligible', False)}\n\n"
            f"{run_result.get('outcome_summary', 'No outcome summary supplied.')}"
        )
        discussion = (
            "## 4. Discussion and Limitations\n\n"
            f"{analysis_summary}\n\n"
            "The result must be interpreted within the supplied provenance, sample "
            "size, statistical assumptions, and reproduction status. Simulation "
            "results are engineering evidence only and cannot establish an empirical "
            "scientific claim."
        )
        authors = list(
            hypothesis.get("authors")
            or ["JAYA Research automated draft — human review required"]
        )
        publication_ready = (
            paper_status == "EMPIRICAL_DRAFT"
            and bool(references)
            and recommendation in {"ACCEPT_HYPOTHESIS", "REJECT_HYPOTHESIS"}
        )
        return {
            "paper_id": (
                "PAPER-"
                + datetime.now(timezone.utc).strftime("%Y%m%d")
                + "-"
                + str(hypothesis.get("hypothesis_id") or "UNKNOWN")[-8:]
            ),
            "paper_status": paper_status,
            "publication_ready": publication_ready,
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
            "limitations": [
                "Automated draft; human scientific review is mandatory.",
                "Claims are limited to supplied evidence and provenance.",
                "Simulation is not empirical evidence.",
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
        """Render a minimal LaTeX research draft."""
        sections = paper.get("sections") or {}
        references = paper.get("references") or []
        latex_authors = " \\and ".join(paper.get("authors", []))
        bibliography = "\n".join(
            f"\\bibitem{{ref{index}}} {reference}"
            for index, reference in enumerate(references, start=1)
        )
        content = f"""\\documentclass[11pt,a4paper]{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage{{hyperref}}
\\title{{{paper.get("title", "Research Report")}}}
\\author{{{latex_authors}}}
\\date{{\\today}}
\\begin{{document}}
\\maketitle
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
\\begin{{thebibliography}}{{99}}
{bibliography}
\\end{{thebibliography}}
\\end{{document}}
"""
        if output_path is not None:
            target = Path(output_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        return content
