"""Bounded, candidate-only language/compiler exploration."""

from __future__ import annotations

import ast
import hashlib
from typing import Any

from optimizer import CandidateProposalError, Optimizer


class DigitalTwinCompiler(Optimizer):
    """Generate compiler proposals without executing or installing them."""

    def __init__(self, target_file: str = "engine.py", **kwargs: Any) -> None:
        super().__init__(target_file, **kwargs)

    @staticmethod
    def _seed(*values: str) -> str:
        digest = hashlib.sha256("\x00".join(values).encode("utf-8")).hexdigest()
        return digest[:16]

    def evolve_syntax(
        self,
        current_syntax_spec: str,
        mode: str = "Optimization",
    ) -> str:
        if self.teacher is None:
            raise CandidateProposalError("Teacher dependency is not configured")
        seed = self._seed(current_syntax_spec, mode, "syntax")
        prompt = (
            "Propose a concise JAYA-Native syntax specification. Label every "
            "unverified performance claim and do not claim benchmark results.\n"
            f"Mode: {mode}\nDeterministic proposal id: {seed}\n"
            f"Current syntax:\n{current_syntax_spec}"
        )
        return self.teacher.suggest_optimization(
            prompt,
            focus="language design candidate",
        )

    def evolve_compiler(
        self,
        syntax_spec: str,
        current_compiler_code: str,
        mode: str = "Optimization",
        research_context: str | None = None,
    ) -> str:
        if self.teacher is None:
            raise CandidateProposalError("Teacher dependency is not configured")
        seed = self._seed(syntax_spec, current_compiler_code, mode)
        context = (
            f"\nSupplied research context (unverified):\n{research_context}"
            if research_context
            else ""
        )
        prompt = (
            "Return a complete Python compiler candidate defining compile_jaya. "
            "Do not execute it and do not claim correctness or performance.\n"
            f"Mode: {mode}\nDeterministic proposal id: {seed}\n"
            f"Syntax:\n{syntax_spec}\nCurrent compiler:\n{current_compiler_code}"
            f"{context}"
        )
        return self.teacher.suggest_optimization(
            prompt,
            focus="compiler candidate",
        )

    @staticmethod
    def check_correctness(compiler_code: str) -> bool:
        """Perform syntax/shape validation only; this is not a correctness claim."""
        try:
            tree = ast.parse(compiler_code)
        except SyntaxError:
            return False
        functions = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "compile_jaya"
        ]
        return len(functions) == 1 and any(
            isinstance(node, ast.Return) for node in ast.walk(functions[0])
        )

    def evaluate_variant(self, syntax: str, compiler: str) -> float:
        """Return a static triage score, never an empirical benchmark."""
        if not syntax.strip() or not self.check_correctness(compiler):
            return 0.0
        return round(1.0 / (1.0 + len(syntax) + len(compiler)), 12)

    def run_evolution_loop(
        self,
        generations: int = 1,
        forever: bool = False,
    ) -> list[dict[str, Any]]:
        """Export a bounded set of simulation candidates."""
        if forever:
            raise CandidateProposalError("Unbounded evolution loops are disabled")
        if not 1 <= generations <= 20:
            raise CandidateProposalError("generations must be between 1 and 20")

        _, original_code = self.read_target()
        syntax = "JAYA-Native syntax is not yet empirically validated."
        compiler = original_code
        receipts: list[dict[str, Any]] = []
        for generation in range(1, generations + 1):
            proposed_syntax = self.evolve_syntax(syntax)
            proposed_compiler = self.evolve_compiler(
                proposed_syntax,
                compiler,
            )
            receipt = self.propose_candidate(
                original_code=original_code,
                proposed_code=proposed_compiler,
                target_name=self.default_target,
                focus="compiler exploration",
                extra_payload={
                    "generation": generation,
                    "syntax_proposal": proposed_syntax,
                    "static_triage_score": self.evaluate_variant(
                        proposed_syntax,
                        proposed_compiler,
                    ),
                    "score_kind": "STATIC_TRIAGE_NOT_BENCHMARK",
                },
            )
            receipts.append(receipt)
            syntax = proposed_syntax
            compiler = proposed_compiler
        return receipts


if __name__ == "__main__":
    raise SystemExit(
        "Direct compiler evolution is disabled. Use an injected provider to "
        "export a bounded review candidate."
    )
