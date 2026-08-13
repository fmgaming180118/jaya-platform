"""Fail-closed staging boundary for model-generated experiment code.

This module intentionally does not implement a process sandbox.  A public,
audited isolated runner does not exist in JAYA Research yet, so generated code
can only be exported as an immutable simulation candidate for review.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from optimizer import CandidateProposalError, Optimizer

MAX_CANDIDATE_CHARS = 1_000_000


def contains_unbounded_loop(code: str) -> bool:
    """Return whether *code* contains an obvious unconditional loop."""
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if not isinstance(node, ast.While):
            continue
        if isinstance(node.test, ast.Constant) and bool(node.test.value) is True:
            return True
    return False


class EvolutionSandbox:
    """Compatibility facade that stages code and never executes it."""

    def __init__(
        self,
        playground_dir: str | Path = "src/playground",
        *,
        source_root: str | Path | None = None,
        outbox_dir: str | Path | None = None,
    ) -> None:
        # Retained for callers that display the historic path.  It is not
        # created or used as an execution directory.
        self.playground_dir = Path(playground_dir)
        resolved_source_root = (
            Path(source_root).resolve()
            if source_root is not None
            else Path(__file__).resolve().parents[1]
        )
        self.optimizer = Optimizer(
            source_root=resolved_source_root,
            outbox_dir=outbox_dir,
        )

    @staticmethod
    def _validate_candidate(candidate_name: str, code: str) -> None:
        name = Path(candidate_name)
        if name.name != candidate_name or name.suffix != ".py":
            raise CandidateProposalError(
                "Candidate name must be a plain .py filename"
            )
        if not code.strip():
            raise CandidateProposalError("Candidate code must not be empty")
        if len(code) > MAX_CANDIDATE_CHARS:
            raise CandidateProposalError("Candidate code exceeds the size limit")
        try:
            unbounded = contains_unbounded_loop(code)
        except SyntaxError as exc:
            raise CandidateProposalError(
                f"Candidate is not valid Python: line {exc.lineno}"
            ) from exc
        if unbounded:
            raise CandidateProposalError(
                "Unbounded loop rejected by the candidate policy"
            )

    def stage_candidate(
        self,
        code: str,
        *,
        candidate_name: str = "experiment_candidate.py",
        purpose: str = "review-only experiment proposal",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Export code as a non-executable simulation artifact."""
        self._validate_candidate(candidate_name, code)
        return self.optimizer.propose_candidate(
            original_code="",
            proposed_code=code,
            target_name=candidate_name,
            focus=purpose,
            extra_payload={
                "execution_policy": "BLOCKED_NO_ISOLATED_RUNNER",
                "execution_backend": "UNAVAILABLE",
                "simulation_only": True,
                "empirical_result": False,
                **dict(metadata or {}),
            },
        )

    def write_experiment(self, filename: str, code: str) -> Path:
        """Compatibility method: stage an artifact instead of writing a script."""
        receipt = self.stage_candidate(code, candidate_name=filename)
        return Path(receipt["artifact_path"])

    def run_code(
        self,
        code: str,
        timeout: int = 10,
        *,
        candidate_name: str = "experiment_candidate.py",
    ) -> dict[str, Any]:
        """Stage code for review; execution is deliberately unavailable."""
        try:
            receipt = self.stage_candidate(
                code,
                candidate_name=candidate_name,
                metadata={"requested_timeout_seconds": int(timeout)},
            )
        except (CandidateProposalError, OSError, ValueError) as exc:
            return {
                "status": "CANDIDATE_REJECTED",
                "success": False,
                "output": "",
                "error": str(exc),
                "candidate_executed": False,
                "source_mutated": False,
            }
        return {
            **receipt,
            "success": False,
            "output": "",
            "error": "Execution blocked: no audited isolated runner is available",
        }

    def run_experiment(
        self,
        filename: str,
        timeout: int = 10,
    ) -> tuple[bool, str]:
        """Refuse legacy file execution without reading or importing the file."""
        del filename, timeout
        return (
            False,
            "BLOCKED_NO_ISOLATED_RUNNER: legacy file execution is disabled",
        )

    def cleanup(self, filename: str) -> bool:
        """Compatibility no-op; this boundary never creates executable files."""
        del filename
        return False
