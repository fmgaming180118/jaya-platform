"""Recursive research loop for JAYA Research.

This module turns a topic into an iterative discovery cycle:
topic -> hypothesis -> novelty check -> research -> meta-synthesis -> new hypothesis.
It stays fully inside JAYA_RESEARCH.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from jaya_research.memory import DiscoveryMemory
from jaya_research.research.agent import ResearchAgent
from jaya_research.research.academic.journal_processor import JournalProcessor
from jaya_research.research.academic.novelty_checker import NoveltyChecker
from jaya_research.research.meta_analysis import MetaAnalyst
from jaya_research.research.workspace_manager import WorkspaceManager
from jaya_research.teacher import Teacher

logger = logging.getLogger("RecursiveResearch")


@dataclass
class RecursiveStepResult:
    iteration: int
    seed: str
    hypothesis: str
    is_novel: bool
    confidence: float
    reasoning: str
    report_path: str
    meta_report_path: Optional[str] = None
    next_seed: Optional[str] = None


@dataclass
class RecursiveResearchResult:
    topic: str
    workspace: str
    iterations: int
    stopped_reason: str
    steps: List[RecursiveStepResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "workspace": self.workspace,
            "iterations": self.iterations,
            "stopped_reason": self.stopped_reason,
            "steps": [step.__dict__ for step in self.steps],
        }

    def to_markdown(self) -> str:
        lines = [
            f"# Recursive Research Report",
            f"- Topic: {self.topic}",
            f"- Workspace: {self.workspace}",
            f"- Iterations: {self.iterations}",
            f"- Stopped: {self.stopped_reason}",
            "",
            "## Steps",
        ]
        for step in self.steps:
            lines.extend([
                f"### Iteration {step.iteration}",
                f"- Seed: {step.seed}",
                f"- Hypothesis: {step.hypothesis}",
                f"- Novel: {step.is_novel}",
                f"- Confidence: {step.confidence:.3f}",
                f"- Reasoning: {step.reasoning}",
                f"- Report: {step.report_path}",
                f"- Meta Report: {step.meta_report_path or 'N/A'}",
                f"- Next Seed: {step.next_seed or 'N/A'}",
                "",
            ])
        return "\n".join(lines).strip() + "\n"

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


class RecursiveResearchLoop:
    """Recursive discovery engine for new research directions."""

    def __init__(self, workspace: str = "default") -> None:
        self.workspace = workspace
        self.workspace_manager = WorkspaceManager()
        self.teacher = Teacher()
        self.journal = JournalProcessor()
        self.novelty_checker = NoveltyChecker()
        self.meta_analyst = MetaAnalyst()
        self.memory = DiscoveryMemory()

    def seed_from_journals(self, topic: str, max_papers: int = 2) -> str:
        """Create a better recursive seed using free journal search."""
        try:
            result = self.journal.process_query(topic, max_papers=max_papers)
        except Exception as exc:
            logger.warning("[Recursive] Journal seeding failed: %s", exc)
            return topic

        papers = result.get("papers", [])
        if not papers:
            return topic

        bullets = []
        for paper in papers[:max_papers]:
            meta = paper.get("metadata", {})
            title = meta.get("title", "Unknown Title")
            insight = (paper.get("insight") or "")[:500]
            bullets.append(f"- {title}: {insight}")

        prompt = f"""
You are a recursive research strategist.
Given the following free journal findings, produce one stronger seed phrase for the next discovery loop.

Topic: {topic}

Findings:
{chr(10).join(bullets)}

Return only a short seed phrase, 3-8 words.
"""
        response = self.teacher.ask(prompt, system_instruction="You are a concise research strategist.")
        seed = response.strip().splitlines()[0].strip() if response.strip() else topic
        return seed or topic

    def _build_hypothesis(self, topic: str, prior_report: Optional[str], iteration: int) -> str:
        prompt = f"""
You are a recursive research planner.
Generate one concrete, testable hypothesis that extends the topic below.

Topic: {topic}
Iteration: {iteration}

Recent report summary:
{(prior_report or 'No prior report')[:3000]}

Rules:
- Produce a single hypothesis sentence.
- Make it specific and falsifiable.
- Prefer new mechanism, new workflow, or new combination.
"""
        response = self.teacher.ask(prompt, system_instruction="You are a rigorous scientific hypothesis generator.")
        cleaned = response.strip().splitlines()[0].strip() if response.strip() else topic
        return cleaned or topic

    def _build_next_seed(self, topic: str, report: str, meta_report: Optional[str], iteration: int) -> str:
        prompt = f"""
Given the topic and the latest research results, produce the next seed phrase for deeper exploration.

Topic: {topic}
Iteration: {iteration}

Report:
{report[:2000]}

Meta report:
{(meta_report or 'None')[:2000]}

Return only a short search seed, ideally 3-8 words.
"""
        response = self.teacher.ask(prompt, system_instruction="You are a concise research strategist.")
        seed = response.strip().splitlines()[0].strip() if response.strip() else topic
        return seed or topic

    def run(self, topic: str, max_iterations: int = 3, novelty_threshold: float = 0.65, human_in_loop: bool = False) -> RecursiveResearchResult:
        safe_workspace = self.workspace
        steps: List[RecursiveStepResult] = []
        stopped_reason = "max_iterations"
        current_seed = topic
        previous_report: Optional[str] = None
        previous_meta_report: Optional[str] = None

        for iteration in range(1, max_iterations + 1):
            logger.info("[Recursive] Iteration %s seed=%s", iteration, current_seed)
            hypothesis = self._build_hypothesis(topic=current_seed, prior_report=previous_report, iteration=iteration)

            novelty = self.novelty_checker.verify_novelty(hypothesis)
            if hasattr(novelty, "__await__"):
                import asyncio
                novelty = asyncio.run(novelty)

            is_novel = bool(novelty.get("is_novel", False))
            confidence = float(novelty.get("confidence", 0.0) or 0.0)
            reasoning = str(novelty.get("reasoning", ""))

            if not is_novel or confidence < novelty_threshold:
                stopped_reason = "novelty_below_threshold"
                step = RecursiveStepResult(
                    iteration=iteration,
                    seed=current_seed,
                    hypothesis=hypothesis,
                    is_novel=is_novel,
                    confidence=confidence,
                    reasoning=reasoning,
                    report_path="",
                    meta_report_path=None,
                    next_seed=None,
                )
                steps.append(step)
                self.memory.add_experience(
                    code=hypothesis,
                    result="RECURSIVE_HYPOTHESIS_REJECTED",
                    score=confidence,
                    metadata={
                        "topic": topic,
                        "workspace": safe_workspace,
                        "iteration": iteration,
                        "reasoning": reasoning,
                        "hypothesis": hypothesis,
                        "timestamp": time.time(),
                    },
                )
                break

            agent = ResearchAgent(topic=hypothesis, focus_areas=f"Recursive research on {topic}", workspace=safe_workspace)
            report = agent.run(human_in_loop=human_in_loop)
            report_path = agent.get_report_path()

            meta_report = self.meta_analyst.run_meta_analysis(hypothesis, lookback_days=30)
            meta_path = str(Path(report_path).with_name(f"META_{iteration}.md"))
            with open(meta_path, "w", encoding="utf-8") as f:
                f.write(meta_report)

            next_seed = self._build_next_seed(topic=hypothesis, report=report or "", meta_report=meta_report, iteration=iteration)
            step = RecursiveStepResult(
                iteration=iteration,
                seed=current_seed,
                hypothesis=hypothesis,
                is_novel=True,
                confidence=confidence,
                reasoning=reasoning,
                report_path=report_path,
                meta_report_path=meta_path,
                next_seed=next_seed,
            )
            steps.append(step)

            self.memory.add_experience(
                code=hypothesis,
                result="RECURSIVE_HYPOTHESIS_ACCEPTED",
                score=confidence,
                metadata={
                    "topic": topic,
                    "workspace": safe_workspace,
                    "iteration": iteration,
                    "report_path": report_path,
                    "meta_report_path": meta_path,
                    "next_seed": next_seed,
                    "timestamp": time.time(),
                },
            )

            previous_report = report
            previous_meta_report = meta_report
            current_seed = next_seed

        return RecursiveResearchResult(
            topic=topic,
            workspace=safe_workspace,
            iterations=len(steps),
            stopped_reason=stopped_reason,
            steps=steps,
        )

    def save_result(self, result: RecursiveResearchResult, output_dir: Optional[str] = None) -> Dict[str, str]:
        target_dir = Path(output_dir) if output_dir else self.workspace_manager.get_or_create_paths(self.workspace)["root"]
        target_dir.mkdir(parents=True, exist_ok=True)

        json_path = target_dir / "recursive_result.json"
        md_path = target_dir / "recursive_result.md"

        json_path.write_text(result.to_json(), encoding="utf-8")
        md_path.write_text(result.to_markdown(), encoding="utf-8")

        return {"json": str(json_path), "markdown": str(md_path)}
