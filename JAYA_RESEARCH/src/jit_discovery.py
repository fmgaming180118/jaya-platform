"""Candidate-only native/JIT optimization proposals."""

from __future__ import annotations

import hashlib
from typing import Any

from optimizer import CandidateProposalError, Optimizer


class NativeDiscovery(Optimizer):
    """Export native optimization candidates without compiling or applying them."""

    def __init__(self, target_file: str = "engine.py", **kwargs: Any) -> None:
        super().__init__(target_file, **kwargs)

    def suggest_native_optimization(
        self,
        code_snippet: str,
        *,
        epoch: int = 1,
    ) -> str:
        if self.teacher is None:
            raise CandidateProposalError("Teacher dependency is not configured")
        proposal_id = hashlib.sha256(
            f"native\x00{epoch}\x00{code_snippet}".encode("utf-8")
        ).hexdigest()[:16]
        prompt = (
            "Propose a complete optional Numba/LLVM-compatible candidate while "
            "preserving a pure-Python fallback. Do not claim measured speed, "
            "correctness, or hardware compatibility.\n"
            f"Proposal id: {proposal_id}\nSource:\n{code_snippet}"
        )
        return self.teacher.suggest_optimization(
            prompt,
            focus="review-only native optimization",
        )

    def run_ascension(self, max_epochs: int = 1) -> list[dict[str, Any]]:
        if not 1 <= max_epochs <= 20:
            raise CandidateProposalError("max_epochs must be between 1 and 20")
        target, original_code = self.read_target()
        receipts = []
        for epoch in range(1, max_epochs + 1):
            proposal = self.suggest_native_optimization(
                original_code,
                epoch=epoch,
            )
            receipts.append(
                self.propose_candidate(
                    original_code=original_code,
                    proposed_code=proposal,
                    target_name=target.name,
                    focus="native optimization proposal",
                    extra_payload={"epoch": epoch},
                )
            )
        return receipts


if __name__ == "__main__":
    raise SystemExit(
        "Direct JIT mutation is disabled. Export a review candidate with an "
        "explicitly injected provider."
    )
