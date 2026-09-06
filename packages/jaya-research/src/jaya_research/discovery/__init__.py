"""Candidate-only scientific source optimization proposals."""

from __future__ import annotations

import hashlib
from typing import Any

from jaya_research.optimizer import CandidateProposalError, Optimizer


class ScientificDiscovery(Optimizer):
    """Propose, but never apply or execute, model-generated source changes."""

    def __init__(self, target_file: str = "engine.py", **kwargs: Any) -> None:
        super().__init__(target_file, **kwargs)

    def suggest_novelty(self, code_snippet: str, *, epoch: int = 1) -> str:
        if self.teacher is None:
            raise CandidateProposalError("Teacher dependency is not configured")
        proposal_id = hashlib.sha256(
            f"{epoch}\x00{code_snippet}".encode("utf-8")
        ).hexdigest()[:16]
        prompt = (
            "Propose a maintainable optimization candidate. Preserve semantics, "
            "label assumptions, and do not claim speed or accuracy without a "
            "benchmark receipt.\n"
            f"Proposal id: {proposal_id}\nSource:\n{code_snippet}"
        )
        return self.teacher.suggest_optimization(
            prompt,
            focus="review-only source optimization",
        )

    def run_discovery_loop(self, max_epochs: int = 1) -> list[dict[str, Any]]:
        if not 1 <= max_epochs <= 20:
            raise CandidateProposalError("max_epochs must be between 1 and 20")
        target, original_code = self.read_target()
        receipts = []
        for epoch in range(1, max_epochs + 1):
            proposal = self.suggest_novelty(original_code, epoch=epoch)
            receipts.append(
                self.propose_candidate(
                    original_code=original_code,
                    proposed_code=proposal,
                    target_name=target.name,
                    focus="scientific optimization proposal",
                    extra_payload={"epoch": epoch},
                )
            )
        return receipts


if __name__ == "__main__":
    raise SystemExit(
        "Direct discovery loops are disabled. Export candidates through the "
        "Research outbox with an explicitly injected provider."
    )
