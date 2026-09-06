"""Research-guided, candidate-only compiler exploration."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from digital_twin_compiler import DigitalTwinCompiler
from jaya_research.optimizer import CandidateProposalError


class ResearchGuidedTwin(DigitalTwinCompiler):
    """Use injected research context to produce bounded review candidates."""

    def __init__(
        self,
        *,
        research_provider: Callable[[str], str] | None = None,
        research_enabled: bool = True,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.research_enabled = research_enabled
        self.research_provider = research_provider
        self.research_cache: dict[str, str] = {}

    def conduct_research(self, topic: str) -> str:
        if not self.research_enabled:
            raise CandidateProposalError("Research context is disabled")
        if self.research_provider is None:
            raise CandidateProposalError(
                "A provenance-aware research provider must be injected"
            )
        if topic not in self.research_cache:
            report = self.research_provider(topic)
            if not isinstance(report, str) or not report.strip():
                raise CandidateProposalError("Research provider returned no evidence")
            self.research_cache[topic] = report
        return self.research_cache[topic]

    def run_evolution_loop(
        self,
        generations: int = 1,
        forever: bool = False,
        research_interval: int = 1,
    ) -> list[dict[str, Any]]:
        if forever:
            raise CandidateProposalError("Unbounded evolution loops are disabled")
        if not 1 <= generations <= 20:
            raise CandidateProposalError("generations must be between 1 and 20")
        if research_interval < 1:
            raise CandidateProposalError("research_interval must be positive")

        _, original_code = self.read_target()
        syntax = "JAYA-Native syntax is not yet empirically validated."
        compiler = original_code
        receipts = []
        research_context: str | None = None
        for generation in range(1, generations + 1):
            if (
                self.research_enabled
                and self.research_provider is not None
                and (generation - 1) % research_interval == 0
            ):
                research_context = self.conduct_research(
                    "compiler optimization with reproducible evidence"
                )
            proposed_syntax = self.evolve_syntax(syntax)
            proposed_compiler = self.evolve_compiler(
                proposed_syntax,
                compiler,
                research_context=research_context,
            )
            receipts.append(
                self.propose_candidate(
                    original_code=original_code,
                    proposed_code=proposed_compiler,
                    target_name=self.default_target,
                    focus="research-guided compiler proposal",
                    extra_payload={
                        "generation": generation,
                        "syntax_proposal": proposed_syntax,
                        "research_context_supplied": research_context is not None,
                        "research_context_verified": False,
                    },
                )
            )
            syntax = proposed_syntax
            compiler = proposed_compiler
        return receipts


if __name__ == "__main__":
    raise SystemExit(
        "Research-guided source mutation is disabled. Use injected dependencies "
        "to export bounded, non-executable candidates."
    )
