"""Evidence-first deep research workflow.

The agent plans bounded questions, retrieves source material, and renders a
traceable report.  Model prose is optional and remains explicitly unverified;
it is never written back into the evidence store or knowledge graph as fact.
"""

from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from jaya_research.config import config
from jaya_research.provider_errors import ProviderError
from jaya_research.research.config import ResearchConfig, get_config
from jaya_research.research.enhanced_rag import EnhancedRAGClient as RAGClient
from jaya_research.research.retrieval_evidence import (
    AnswerStatus,
    build_grounded_response,
    enrich_chunk_metadata,
)


class ResearchWorkflowError(RuntimeError):
    """A stable, actionable failure in the deep-research workflow."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


_AUTO_TEACHER = object()
_AUTO_WEB = object()


class ResearchAgent:
    """Run bounded research without converting generated prose into evidence."""

    def __init__(
        self,
        topic: str,
        focus_areas: str = "",
        workspace: str = "default",
        *,
        teacher: Any = _AUTO_TEACHER,
        rag: Any | None = None,
        web_search: Any = _AUTO_WEB,
        graph_rag: Any | None = None,
        research_config: ResearchConfig | None = None,
        plan_questions: Sequence[str] | None = None,
        memory_path: str | os.PathLike[str] | None = None,
        run_id: str | None = None,
        clock: Any = time.time,
    ) -> None:
        self.topic = " ".join(topic.split())
        if not self.topic:
            raise ValueError("topic must not be empty")
        self.focus_areas = " ".join(focus_areas.split()) or "General research"
        self.workspace = workspace
        self.config = research_config or get_config()
        self._clock = clock
        self._memory_path = Path(memory_path).resolve() if memory_path else None
        self._run_id = self._normalize_run_id(run_id or uuid.uuid4().hex)
        if isinstance(plan_questions, (str, bytes)):
            raise TypeError("plan_questions must be a sequence of questions")
        self._supplied_plan = self._normalize_questions(plan_questions or [])
        self._teacher_mode = (
            "AUTO"
            if teacher is _AUTO_TEACHER
            else ("DISABLED" if teacher is None else "INJECTED")
        )
        self.teacher = None if teacher is _AUTO_TEACHER else teacher

        if rag is None:
            from jaya_research.research.workspace_manager import WorkspaceManager

            paths = WorkspaceManager().get_or_create_paths(workspace)
            rag = RAGClient(
                vector_store_path=paths["vector_store"],
                workspace_id=workspace,
            )
        self.rag = rag

        if web_search is _AUTO_WEB:
            try:
                from jaya_research.research.web_search import WebSearchClient

                web_search = WebSearchClient()
            except ImportError:
                web_search = None
        self.web_search = web_search
        # Retained as an injected read-only adapter for compatibility. Generated
        # model output is never sent to this graph.
        self.graph_rag = graph_rag

        self.plan: dict[str, Any] | None = None
        self.queries: list[str] = []
        self.findings: list[dict[str, Any]] = []
        self.attempt_history: list[dict[str, Any]] = []
        self.report: str | None = None
        self.iteration = 0

    def run(self, human_in_loop: bool = True) -> str:
        """Execute a bounded plan, retrieval, review, and report cycle."""
        self.plan = self.generate_plan()
        if human_in_loop:
            approval = input(
                "Proceed with the evidence retrieval plan? [Y/n]: "
            ).strip()
            if approval.casefold() == "n":
                raise ResearchWorkflowError(
                    "RESEARCH_CANCELED",
                    "Research plan was canceled by the user",
                )

        self.findings = self.execute_queries()
        self.attempt_history.extend(self.findings)
        self.report = self.write_report()
        gaps = self.review_report()
        max_iterations = self.config.max_iterations
        while gaps and self.iteration < max_iterations:
            retry_findings = self.execute_queries(gaps)
            self.attempt_history.extend(retry_findings)
            self.findings = self._merge_latest_findings(
                self.findings,
                retry_findings,
            )
            self.report = self.write_report()
            self.iteration += 1
            new_gaps = self.review_report()
            if new_gaps == gaps:
                break
            gaps = new_gaps
        self.save_report()
        return self.report

    def generate_plan(self) -> dict[str, Any]:
        """Create a plan or reject malformed planner output without templates."""
        if self._supplied_plan:
            questions = self._supplied_plan
            plan_source = "CALLER_SUPPLIED"
        else:
            prompt_name = (
                "agi_research_plan"
                if any(
                    keyword in self.topic.casefold()
                    for keyword in (
                        "agi",
                        "self-improvement",
                        "compiler",
                        "recursive",
                        "evolution",
                    )
                )
                else "research_plan"
            )
            prompt = self.config.get_prompt(
                prompt_name,
                topic=self.topic,
                focus_areas=self.focus_areas,
            )
            teacher = self._get_teacher(required=True)
            response = teacher.ask(
                prompt,
                system_instruction=(
                    "Return only a numbered list of specific, source-searchable "
                    "research questions. Do not answer them."
                ),
            )
            questions = self._parse_numbered_questions(response)
            plan_source = "INJECTED_MODEL"

        if not questions:
            raise ResearchWorkflowError(
                "PLAN_INVALID",
                "Planner produced no valid research questions",
            )
        self.queries = questions[: self.config.max_queries]
        return {
            "topic": self.topic,
            "focus": self.focus_areas,
            "queries": list(self.queries),
            "plan_source": plan_source,
            "bounded": True,
        }

    def execute_queries(
        self,
        queries: Sequence[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve and ground each question; never synthesize without evidence."""
        selected = self._normalize_questions(queries or self.queries)
        if not selected:
            raise ResearchWorkflowError("QUERY_SET_EMPTY", "No research queries supplied")
        configured_limit = int(
            getattr(getattr(self, "config", None), "max_queries", len(selected))
        )

        findings: list[dict[str, Any]] = []
        for query in selected[:configured_limit]:
            local_results = self._search_local(query)
            web_results: list[dict[str, Any]] = []
            has_confident_local = any(
                float(item.get("score") or 0.0) >= 0.55 for item in local_results
            )
            if not has_confident_local and self._web_available():
                web_results = self._search_web(query)

            grounded = build_grounded_response(local_results, web_results)
            citations = list(grounded.get("citations") or [])
            model_synthesis = ""
            citation_coverage = 0.0
            model_synthesis_status = "NOT_USED"
            if grounded["status"] == AnswerStatus.ANSWERED.value:
                (
                    model_synthesis,
                    citation_coverage,
                    model_synthesis_status,
                ) = self._optional_synthesis(query, grounded)

            findings.append(
                {
                    "query": query,
                    "status": grounded["status"],
                    "answer": grounded["answer"],
                    "claims": list(grounded.get("claims") or []),
                    "citations": citations,
                    "sources": self._source_labels(local_results + web_results),
                    "source_count": len(local_results) + len(web_results),
                    "evidence_quality": grounded.get(
                        "evidence_quality",
                        "INSUFFICIENT_EVIDENCE",
                    ),
                    "promotion_eligible": False,
                    "model_synthesis": model_synthesis,
                    "model_synthesis_status": model_synthesis_status,
                    "model_citation_coverage": citation_coverage,
                }
            )
        return findings

    def write_report(self) -> str:
        """Render only grounded claims and explicit limitations to Markdown."""
        if not self.findings:
            raise ResearchWorkflowError(
                "NO_FINDINGS",
                "A report cannot be created without retrieval findings",
            )
        lines = [
            f"# Research Evidence Report: {self.topic}",
            "",
            "**Status:** UNVERIFIED_RESEARCH_REPORT",
            "**Promotion eligible:** false",
            "",
            (
                "This report contains extractive retrieval claims only. Optional "
                "model prose is excluded from the evidence section and must be "
                "reviewed separately."
            ),
            "",
        ]
        for index, finding in enumerate(self.findings, start=1):
            lines.extend(
                [
                    f"## {index}. {finding['query']}",
                    "",
                    f"**Evidence status:** {finding['status']}",
                    f"**Evidence quality:** {finding['evidence_quality']}",
                    "",
                    str(finding["answer"]),
                    "",
                ]
            )
            if finding["citations"]:
                lines.append("### Citations")
                for citation in finding["citations"]:
                    lines.append(
                        "- [{citation_id}] {source_uri} | page={page} | "
                        "sha256={digest} | license={license_id}".format(
                            citation_id=citation["citation_id"],
                            source_uri=citation["source_uri"],
                            page=citation["page_number"],
                            digest=citation["chunk_sha256"],
                            license_id=citation["license_id"],
                        )
                    )
                lines.append("")

        abstained = sum(
            str(finding["status"]).startswith("ABSTAINED")
            for finding in self.findings
        )
        incomplete = sum(
            finding["evidence_quality"] != "COMPLETE_PROVENANCE"
            for finding in self.findings
        )
        lines.extend(
            [
                "## Limitations",
                "",
                f"- Questions abstained: {abstained}/{len(self.findings)}.",
                f"- Findings with incomplete provenance: {incomplete}/{len(self.findings)}.",
                "- Human/domain review is required before scientific use.",
                "- This report is not empirical evidence and is never auto-promoted.",
            ]
        )
        return "\n".join(lines).strip() + "\n"

    def review_report(self) -> list[str]:
        """Return unresolved questions based on typed evidence status."""
        return list(
            dict.fromkeys(
                str(finding["query"])
                for finding in self.findings
                if finding["status"] != AnswerStatus.ANSWERED.value
                or finding["evidence_quality"] != "COMPLETE_PROVENANCE"
            )
        )

    def save_report(self) -> None:
        """Atomically persist the draft and record it as non-evidence memory."""
        if not isinstance(self.report, str) or not self.report.strip():
            raise ResearchWorkflowError("REPORT_EMPTY", "Research report is empty")
        report_path = Path(self.get_report_path()).resolve()
        reports_root = Path(self.config.reports_dir).resolve()
        try:
            report_path.relative_to(reports_root)
        except ValueError as exc:
            raise ResearchWorkflowError(
                "REPORT_PATH_ESCAPE",
                "Report path escaped the configured report directory",
            ) from exc
        report_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_report_once(report_path, self.report)

        try:
            from jaya_research.memory import DiscoveryMemory

            memory_path = getattr(self, "_memory_path", None)
            if memory_path is None:
                configured_paths = getattr(config, "paths", {})
                memory_path = configured_paths.get("DISCOVERY_MEMORY_PATH")
            memory = DiscoveryMemory(str(memory_path) if memory_path else None)
            memory.add_experience(
                code=self.report,
                result="UNVERIFIED_RESEARCH_REPORT",
                score=None,
                metadata={
                    "topic": self.topic,
                    "focus_areas": self.focus_areas,
                    "queries_count": len(self.queries),
                    "findings_count": len(self.findings),
                    "report_path": str(report_path),
                    "report_sha256": hashlib.sha256(
                        self.report.encode("utf-8")
                    ).hexdigest(),
                    "evidence_kind": "SYNTHESIS_DRAFT",
                    "promotion_eligible": False,
                    "timestamp": getattr(self, "_clock", time.time)(),
                },
            )
        except (OSError, ValueError, TypeError) as exc:
            raise ResearchWorkflowError(
                "REPORT_MEMORY_FAILED",
                "Report was written but its audit record could not be persisted",
            ) from exc

    def get_report_path(self) -> str:
        reports_dir = Path(self.config.reports_dir)
        safe_topic = re.sub(r"[^A-Za-z0-9_-]+", "_", self.topic).strip("_")[:50]
        if not safe_topic:
            safe_topic = "research"
        run_id = getattr(self, "_run_id", None)
        if run_id is None:
            run_id = uuid.uuid4().hex
            self._run_id = run_id
        filename = (
            f"{safe_topic}_{int(getattr(self, '_clock', time.time)())}_"
            f"{run_id}.md"
        )
        return str(reports_dir / filename)

    @staticmethod
    def _write_report_once(report_path: Path, report: str) -> None:
        """Create an immutable report without replacing an existing artifact."""
        descriptor: int | None = None
        try:
            descriptor = os.open(
                report_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = None
                handle.write(report)
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError as exc:
            raise ResearchWorkflowError(
                "REPORT_ALREADY_EXISTS",
                "The immutable report path already exists",
            ) from exc
        except OSError:
            if descriptor is not None:
                os.close(descriptor)
            try:
                report_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def _search_local(self, query: str) -> list[dict[str, Any]]:
        try:
            raw = self.rag.search(query, top_k=3)
        except ProviderError:
            raise
        except Exception as exc:
            raise ResearchWorkflowError(
                "LOCAL_RETRIEVAL_FAILED",
                f"Local retrieval failed with {type(exc).__name__}",
            ) from exc
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ResearchWorkflowError(
                "LOCAL_RETRIEVAL_INVALID",
                "Local retriever returned an invalid result collection",
            )
        return [
            normalized
            for item in raw
            if (normalized := self._normalize_result(item, source_kind="LOCAL"))
            is not None
        ]

    def _search_web(self, query: str) -> list[dict[str, Any]]:
        try:
            raw = self.web_search.search(query, max_results=3)
        except ProviderError:
            raise
        except Exception as exc:
            raise ResearchWorkflowError(
                "WEB_RETRIEVAL_FAILED",
                f"Web retrieval failed with {type(exc).__name__}",
            ) from exc
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
            raise ResearchWorkflowError(
                "WEB_RETRIEVAL_INVALID",
                "Web retriever returned an invalid result collection",
            )
        return [
            normalized
            for item in raw
            if (normalized := self._normalize_result(item, source_kind="WEB"))
            is not None
        ]

    @staticmethod
    def _normalize_result(item: Any, *, source_kind: str) -> dict[str, Any] | None:
        if not isinstance(item, Mapping):
            return None
        content = str(item.get("content") or item.get("snippet") or "").strip()
        if not content:
            return None
        document = item.get("document")
        metadata = dict(document) if isinstance(document, Mapping) else {}
        if isinstance(item.get("metadata"), Mapping):
            metadata.update(item["metadata"])
        metadata.setdefault("source_id", item.get("source_id"))
        metadata.setdefault("source_uri", item.get("url"))
        metadata.setdefault("title", item.get("title"))
        source_label = item.get("source") or metadata.get("file_name")
        if source_label and not metadata.get("source"):
            metadata["source"] = source_label
        metadata = enrich_chunk_metadata(content, metadata)
        normalized: dict[str, Any] = {
            "content": content,
            "snippet": content,
            "metadata": metadata,
            "document": metadata,
            "source_kind": source_kind,
        }
        if source_kind == "LOCAL":
            score = item.get("score")
            try:
                normalized["score"] = float(score)
            except (TypeError, ValueError):
                normalized["score"] = 0.0
        elif item.get("score") is not None:
            try:
                normalized["score"] = float(item["score"])
            except (TypeError, ValueError):
                pass
        return normalized

    def _optional_synthesis(
        self,
        query: str,
        grounded: Mapping[str, Any],
    ) -> tuple[str, float, str]:
        citations = list(grounded.get("citations") or [])
        if not citations:
            return "", 0.0, "NOT_USED"
        try:
            teacher = self._get_teacher(required=False)
        except ProviderError:
            return "", 0.0, "PROVIDER_UNAVAILABLE"
        if teacher is None:
            return "", 0.0, "PROVIDER_DISABLED"
        context = "\n".join(
            f"[{citation['citation_id']}] {citation['snippet']}"
            for citation in citations
        )
        try:
            response = teacher.ask(
                (
                    f"Question: {query}\n\nEvidence:\n{context}\n\n"
                    "Draft a concise answer using only this evidence. Every sentence "
                    "must include at least one supplied citation ID."
                ),
                system_instruction=(
                    "You are a precise Research Assistant. Use only the provided "
                    "context; do not add internal knowledge."
                ),
            )
        except ProviderError:
            return "", 0.0, "PROVIDER_UNAVAILABLE"
        if not isinstance(response, str) or not response.strip():
            return "", 0.0, "INVALID_PROVIDER_OUTPUT"
        used = {
            citation["citation_id"]
            for citation in citations
            if f"[{citation['citation_id']}]" in response
        }
        coverage = len(used) / len(citations)
        if not used:
            return "", 0.0, "INVALID_PROVIDER_OUTPUT"
        return response.strip(), round(coverage, 6), "UNVERIFIED_CITED_DRAFT"

    def _get_teacher(self, *, required: bool) -> Any | None:
        teacher = getattr(self, "teacher", None)
        if teacher is not None:
            return teacher
        mode = getattr(self, "_teacher_mode", "AUTO")
        if mode == "DISABLED":
            if required:
                raise ResearchWorkflowError(
                    "PLANNER_PROVIDER_REQUIRED",
                    "A planner provider or caller-supplied plan is required",
                )
            return None
        from jaya_research.teacher import Teacher

        teacher = Teacher(model_type="reasoning")
        self.teacher = teacher
        self._teacher_mode = "INJECTED"
        return teacher

    @staticmethod
    def _merge_latest_findings(
        existing: Sequence[Mapping[str, Any]],
        replacements: Sequence[Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        """Replace the latest state per query while preserving plan order."""
        latest = {str(item.get("query")): dict(item) for item in replacements}
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in existing:
            query = str(item.get("query"))
            merged.append(latest.get(query, dict(item)))
            seen.add(query)
        merged.extend(
            dict(item)
            for item in replacements
            if str(item.get("query")) not in seen
        )
        return merged

    @staticmethod
    def _normalize_run_id(value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", normalized):
            raise ValueError(
                "run_id must contain 8-64 letters, numbers, underscores, or hyphens"
            )
        return normalized

    def _web_available(self) -> bool:
        if not hasattr(self, "web_search"):
            try:
                from jaya_research.research.web_search import WebSearchClient

                self.web_search = WebSearchClient()
            except ImportError:
                self.web_search = None
        if self.web_search is None:
            return False
        check = getattr(self.web_search, "is_available", None)
        if not callable(check):
            return True
        try:
            return check() is True
        except Exception:
            return False

    @staticmethod
    def _source_labels(results: Sequence[Mapping[str, Any]]) -> list[str]:
        labels: list[str] = []
        for result in results:
            metadata = result.get("metadata")
            if not isinstance(metadata, Mapping):
                continue
            label = str(
                metadata.get("file_name")
                or metadata.get("title")
                or metadata.get("source_uri")
                or metadata.get("source_id")
                or ""
            )
            if label and label not in labels:
                labels.append(label)
        return labels

    @staticmethod
    def _parse_numbered_questions(response: Any) -> list[str]:
        if not isinstance(response, str):
            return []
        candidates: list[str] = []
        for line in response.splitlines():
            match = re.match(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$", line)
            if match:
                candidates.append(match.group(1))
        return ResearchAgent._normalize_questions(candidates)

    @staticmethod
    def _normalize_questions(values: Sequence[Any]) -> list[str]:
        questions: list[str] = []
        for value in values:
            question = " ".join(str(value).split())
            if 5 <= len(question) <= 500 and question not in questions:
                questions.append(question)
        return questions


if __name__ == "__main__":
    import sys

    selected_topic = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "Meta-Learning for Neural Compilation"
    )
    print(ResearchAgent(topic=selected_topic).run(human_in_loop=True))
