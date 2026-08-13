"""Candidate-only compatibility facade for legacy code mutation requests."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from optimizer import CandidateProposalError, Optimizer
from provider_errors import ProviderError


class CodeMutator:
    """Generate review artifacts without writing to the source tree."""

    def __init__(
        self,
        *,
        teacher: Any | None = None,
        source_root: str | Path | None = None,
        outbox_dir: str | Path | None = None,
        optimizer: Optimizer | None = None,
    ) -> None:
        resolved_source_root = (
            Path(source_root).resolve()
            if source_root is not None
            else Path(__file__).resolve().parents[1]
        )
        self.optimizer = optimizer or Optimizer(
            teacher=teacher,
            source_root=resolved_source_root,
            outbox_dir=outbox_dir,
        )

    @staticmethod
    def _normalize_target(target_file: str) -> str:
        path = Path(target_file)
        if path.is_absolute():
            return str(path)
        parts = path.parts
        if parts and parts[0].lower() == "src":
            return str(Path(*parts[1:]))
        return str(path)

    def evolve_file(self, target_file: str, instruction: str) -> dict[str, Any]:
        """Export a candidate or return an explicit unavailable/rejected status."""
        if self.optimizer.teacher is None:
            return {
                "status": "UNAVAILABLE_PROVIDER_MISSING",
                "source_mutated": False,
                "candidate_executed": False,
                "human_review_required": True,
                "error": "A configured Teacher must be explicitly injected",
            }
        if not instruction.strip():
            return {
                "status": "CANDIDATE_REJECTED",
                "source_mutated": False,
                "candidate_executed": False,
                "human_review_required": True,
                "error": "Evolution instruction is required",
            }
        try:
            return self.optimizer.evolve(
                target_file=self._normalize_target(target_file),
                focus=instruction,
            )
        except ProviderError as exc:
            return {
                "status": "PROVIDER_ERROR",
                "source_mutated": False,
                "candidate_executed": False,
                "human_review_required": True,
                "provider_error": exc.to_dict(),
            }
        except (CandidateProposalError, FileExistsError, OSError) as exc:
            return {
                "status": "CANDIDATE_REJECTED",
                "source_mutated": False,
                "candidate_executed": False,
                "human_review_required": True,
                "error": str(exc),
            }

    def _validate_mutation(self, file_path: Path) -> bool:
        """Retained compatibility check using parsing only, never execution."""
        try:
            ast.parse(file_path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeError):
            return False
        return True
