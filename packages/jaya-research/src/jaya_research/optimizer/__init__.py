"""Candidate-only optimization workflow for JAYA Research.

Research may propose source changes, but it must never overwrite a running
module or execute model-generated code. A separate Core-side review and
installation boundary owns every promotion.
"""

from __future__ import annotations

import ast
import hashlib
from pathlib import Path
from typing import Any

from jaya_research.research.research_artifact import (
    EvidenceKind,
    ResearchArtifactOutbox,
    build_research_artifact,
)


class CandidateProposalError(RuntimeError):
    """Raised when a source candidate cannot be prepared safely."""


def _static_risks(tree: ast.AST) -> list[str]:
    risky_calls = {"compile", "eval", "exec", "open", "__import__"}
    risky_imports = {"ctypes", "os", "pathlib", "shutil", "socket", "subprocess"}
    findings: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else [str(node.module or "")]
            )
            for name in names:
                root_name = name.partition(".")[0]
                if root_name in risky_imports:
                    findings.add(f"risky_import:{root_name}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in risky_calls:
                findings.add(f"risky_call:{node.func.id}")
    return sorted(findings)


class Optimizer:
    """Read source and export a non-executable candidate for human review."""

    def __init__(
        self,
        target_file: str = "engine.py",
        *,
        teacher: Any | None = None,
        source_root: str | Path | None = None,
        outbox_dir: str | Path | None = None,
    ) -> None:
        self.default_target = target_file
        self.teacher = teacher
        self.source_root = Path(
            source_root or Path(__file__).resolve().parent
        ).resolve()
        default_outbox = self.source_root.parent / "data" / "artifact_outbox"
        self.outbox = ResearchArtifactOutbox(outbox_dir or default_outbox)

    def _resolve_target(self, target_file: str | None = None) -> Path:
        raw_target = str(target_file or self.default_target)
        candidate = (self.source_root / raw_target).resolve()
        try:
            candidate.relative_to(self.source_root)
        except ValueError as exc:
            raise CandidateProposalError(
                "Optimization target must stay inside the Research source root"
            ) from exc
        if not candidate.is_file():
            raise CandidateProposalError(
                f"Optimization target does not exist: {raw_target}"
            )
        return candidate

    def read_target(self, target_file: str | None = None) -> tuple[Path, str]:
        target = self._resolve_target(target_file)
        return target, target.read_text(encoding="utf-8")

    def propose_candidate(
        self,
        *,
        original_code: str,
        proposed_code: str,
        target_name: str,
        focus: str,
        extra_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Publish a syntax-checked, non-executable simulation candidate."""
        if not proposed_code.strip():
            raise CandidateProposalError("Provider returned an empty candidate")
        try:
            tree = ast.parse(proposed_code)
        except SyntaxError as exc:
            raise CandidateProposalError(
                f"Candidate is not valid Python: line {exc.lineno}"
            ) from exc

        source_sha256 = hashlib.sha256(
            original_code.encode("utf-8")
        ).hexdigest()
        proposal_sha256 = hashlib.sha256(
            proposed_code.encode("utf-8")
        ).hexdigest()
        finding_id = f"optimization-{proposal_sha256[:20]}"
        artifact = build_research_artifact(
            artifact_id=f"candidate-{proposal_sha256[:24]}",
            artifact_type="source_change_proposal",
            finding_id=finding_id,
            evidence_kind=EvidenceKind.SIMULATION,
            subject=f"Candidate optimization for {Path(target_name).name}",
            payload={
                "target_name": Path(target_name).name,
                "focus": focus,
                "proposal_text": proposed_code,
                "proposal_sha256": proposal_sha256,
                "static_risks": _static_risks(tree),
                "syntax_valid": True,
                "executable": False,
                **dict(extra_payload or {}),
            },
            provenance={
                "source_hashes": [source_sha256],
                "dataset_sha256": "",
            },
            reproducibility={
                "reproduced": False,
                "run_count": 0,
            },
            license_info={"id": "UNVERIFIED-PROPOSAL"},
            confidence=0.0,
        )
        artifact_path = self.outbox.publish(artifact)
        return {
            "status": "SIMULATION_CANDIDATE_EXPORTED",
            "artifact_id": artifact.artifact_id,
            "artifact_path": str(artifact_path),
            "proposal_sha256": proposal_sha256,
            "source_mutated": False,
            "candidate_executed": False,
            "human_review_required": True,
        }

    def evolve(
        self,
        target_file: str | None = None,
        focus: str = "performance and maintainability",
    ) -> dict[str, Any]:
        """Ask an explicitly configured provider for a review-only candidate."""
        if self.teacher is None:
            raise CandidateProposalError(
                "A configured Teacher must be injected before proposing evolution"
            )
        target, original_code = self.read_target(target_file)
        proposed_code = self.teacher.suggest_optimization(
            original_code,
            focus=focus,
        )
        return self.propose_candidate(
            original_code=original_code,
            proposed_code=proposed_code,
            target_name=target.name,
            focus=focus,
        )


if __name__ == "__main__":
    raise SystemExit(
        "Candidate generation requires an explicitly configured provider. "
        "Import Optimizer and inject Teacher; direct source evolution is disabled."
    )
