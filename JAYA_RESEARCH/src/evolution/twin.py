"""Bounded, candidate-only Digital Twin compatibility layer.

The legacy twin remains available to callers, but it cannot mutate source,
execute generated code, start an unbounded loop, or initialize a model provider
implicitly.  Actual research runs belong to the durable Research job API.
"""

from __future__ import annotations

import asyncio
from enum import Enum
from pathlib import Path
from typing import Any

from evolution.crucible import Crucible
from evolution.memory import EvolutionMemory
from evolution.mutator import CodeMutator
from evolution.sandbox import EvolutionSandbox
from provider_errors import ProviderError

MAX_LOOP_CYCLES = 100
MAX_CYCLE_INTERVAL_SECONDS = 60.0


class TwinLoopPolicyError(ValueError):
    """Raised when a caller requests an unbounded autonomous loop."""


class TwinState(str, Enum):
    IDLE = "idle"
    DREAMING = "dreaming"
    PLANNING = "planning"
    CODING = "coding"
    TESTING = "testing"
    RESEARCHING = "researching"


class ResearchMode(str, Enum):
    EXPLORATION = "exploration"
    THESIS = "thesis"


class DigitalTwin:
    """A fail-closed coordinator that exports candidates for review."""

    def __init__(
        self,
        *,
        teacher: Any | None = None,
        source_root: str | Path | None = None,
        outbox_dir: str | Path | None = None,
        memory: EvolutionMemory | None = None,
        cycle_interval_seconds: float = 5.0,
    ) -> None:
        if not 0.0 <= float(cycle_interval_seconds) <= MAX_CYCLE_INTERVAL_SECONDS:
            raise TwinLoopPolicyError(
                "Cycle interval must be finite and between 0 and 60 seconds"
            )
        self.state = TwinState.IDLE
        self.teacher = teacher
        self.memory = memory or EvolutionMemory()
        self.sandbox = EvolutionSandbox(
            source_root=source_root,
            outbox_dir=outbox_dir,
        )
        self.mutator = CodeMutator(
            teacher=teacher,
            source_root=source_root,
            outbox_dir=outbox_dir,
        )
        self.cycle_interval_seconds = float(cycle_interval_seconds)
        self.night_mode = False
        self.mode = ResearchMode.EXPLORATION
        self.current_task: dict[str, Any] | None = None
        self.running = False
        self.completed_cycles = 0

    def _log(
        self,
        content: str,
        *,
        mood: str = "neutral",
        context: dict[str, Any] | None = None,
    ) -> None:
        self.memory.log_thought(content, mood=mood, context=context)

    @staticmethod
    def _validate_cycle_bound(max_cycles: int | None) -> int:
        if (
            isinstance(max_cycles, bool)
            or not isinstance(max_cycles, int)
            or not 1 <= max_cycles <= MAX_LOOP_CYCLES
        ):
            raise TwinLoopPolicyError(
                "Unbounded loop rejected; max_cycles must be an integer "
                f"between 1 and {MAX_LOOP_CYCLES}"
            )
        return max_cycles

    @staticmethod
    def _provider_failure(exc: ProviderError) -> dict[str, Any]:
        return {
            "status": "PROVIDER_ERROR",
            "provider_error": exc.to_dict(),
            "action_dispatched": False,
            "candidate_executed": False,
            "source_mutated": False,
            "novelty_status": "NOT_ASSESSED",
        }

    def toggle_night_mode(self, enabled: bool) -> dict[str, Any]:
        self.night_mode = bool(enabled)
        self._log(
            f"Candidate review scheduling mode set to "
            f"{'night' if self.night_mode else 'day'}.",
            mood="neutral",
        )
        return {
            "status": "CONFIGURED_CANDIDATE_ONLY",
            "night_mode": self.night_mode,
        }

    async def start_loop(
        self,
        max_cycles: int | None = None,
        *,
        enabled: bool = False,
    ) -> dict[str, Any]:
        """Run a finite, explicitly enabled no-op coordination batch."""
        if not enabled:
            return {
                "status": "DISABLED_BY_DEFAULT",
                "running": False,
                "completed_cycles": self.completed_cycles,
            }
        bound = self._validate_cycle_bound(max_cycles)
        self.running = True
        self._log(
            f"Starting bounded candidate coordination batch ({bound} cycles).",
            mood="neutral",
        )
        completed = 0
        try:
            for index in range(bound):
                if not self.running:
                    break
                await self.cycle()
                completed += 1
                self.completed_cycles += 1
                if (
                    index + 1 < bound
                    and self.running
                    and self.cycle_interval_seconds > 0
                ):
                    await asyncio.sleep(self.cycle_interval_seconds)
        finally:
            self.running = False
            self.state = TwinState.IDLE
        return {
            "status": "BOUNDED_BATCH_COMPLETED",
            "running": False,
            "completed_cycles": completed,
        }

    async def cycle(self) -> dict[str, Any]:
        """Perform one bounded coordination tick without autonomous action."""
        if self.current_task is None:
            return {
                "status": "IDLE_NO_AUTONOMOUS_ACTION",
                "provider_called": False,
                "source_mutated": False,
            }
        return await self.execute_plan()

    async def think(self) -> dict[str, Any]:
        """Request at most an untrusted suggestion and never dispatch it."""
        if self.teacher is None:
            return {
                "status": "UNAVAILABLE_PROVIDER_MISSING",
                "action_dispatched": False,
                "source_mutated": False,
            }
        ask = getattr(self.teacher, "ask", None)
        if not callable(ask):
            return {
                "status": "UNAVAILABLE_PROVIDER_INCOMPATIBLE",
                "action_dispatched": False,
                "source_mutated": False,
            }
        self.state = TwinState.DREAMING
        try:
            suggestion = str(
                ask(
                    "Propose one review-only Research improvement. Do not claim "
                    "execution, benchmarking, novelty, or deployment.",
                    system_instruction=(
                        "Return an unverified suggestion only; it will not run."
                    ),
                )
            )
            self._log(
                "An unverified provider suggestion was received but not "
                "dispatched.",
                mood="neutral",
                context={"suggestion_length": len(suggestion)},
            )
            return {
                "status": "UNVERIFIED_SUGGESTION_NOT_DISPATCHED",
                "action_dispatched": False,
                "source_mutated": False,
            }
        except ProviderError as exc:
            return self._provider_failure(exc)
        finally:
            self.state = TwinState.IDLE

    async def run_research(
        self,
        topic: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        """Redirect legacy autonomous research to the durable job boundary."""
        del topic, workspace_id
        return {
            "status": "UNAVAILABLE_USE_DURABLE_RESEARCH_JOB",
            "research_executed": False,
            "message": (
                "Submit research through POST /research/autonomous with an "
                "Idempotency-Key"
            ),
        }

    async def invent_novel_concept(
        self,
        domain1: str,
        domain2: str,
        workspace_id: str,
    ) -> dict[str, Any]:
        """Stage an unverified simulation candidate without novelty claims."""
        if self.teacher is None:
            return {
                "status": "UNAVAILABLE_PROVIDER_MISSING",
                "candidate_executed": False,
                "novelty_status": "NOT_ASSESSED",
            }
        ask = getattr(self.teacher, "ask", None)
        if not callable(ask):
            return {
                "status": "UNAVAILABLE_PROVIDER_INCOMPATIBLE",
                "candidate_executed": False,
                "novelty_status": "NOT_ASSESSED",
            }
        self.state = TwinState.RESEARCHING
        try:
            code = str(
                ask(
                    "Create Python code for an unverified simulation proposal "
                    f"about the intersection of {domain1} and {domain2}.",
                    system_instruction=(
                        "Return code only. It will be reviewed, not executed."
                    ),
                )
            )
            crucible = Crucible(
                workspace_id,
                source_root=self.mutator.optimizer.source_root,
                outbox_dir=self.mutator.optimizer.outbox.outbox_dir,
            )
            _, message, receipt = crucible.run_experiment(
                f"Unverified intersection proposal: {domain1} / {domain2}",
                code,
            )
            return {
                **receipt,
                "message": message,
                "novelty_status": "NOT_ASSESSED",
                "empirical_claimed": False,
            }
        except ProviderError as exc:
            return self._provider_failure(exc)
        finally:
            self.state = TwinState.IDLE

    def set_mode(self, mode_str: str) -> bool:
        try:
            self.mode = ResearchMode(mode_str.lower())
        except ValueError:
            return False
        self._log(
            f"Candidate output mode set to {self.mode.value}.",
            mood="neutral",
        )
        return True

    async def evolve(
        self,
        target_file: str,
        instruction: str,
    ) -> dict[str, Any]:
        """Export a source-change candidate; never apply it."""
        self.state = TwinState.CODING
        try:
            receipt = self.mutator.evolve_file(target_file, instruction)
            self._log(
                f"Evolution request ended with {receipt['status']}.",
                mood="neutral",
                context={
                    "source_mutated": False,
                    "candidate_executed": False,
                },
            )
            return receipt
        except ProviderError as exc:
            return self._provider_failure(exc)
        finally:
            self.state = TwinState.IDLE

    async def plan(self, goal: str) -> dict[str, Any]:
        """Convert provider-generated code into a review-only artifact."""
        if self.teacher is None:
            return {
                "status": "UNAVAILABLE_PROVIDER_MISSING",
                "candidate_executed": False,
            }
        ask = getattr(self.teacher, "ask", None)
        if not callable(ask):
            return {
                "status": "UNAVAILABLE_PROVIDER_INCOMPATIBLE",
                "candidate_executed": False,
            }
        self.state = TwinState.PLANNING
        try:
            code = str(
                ask(
                    f"Draft review-only Python for this goal: {goal}",
                    system_instruction=(
                        "Return code only. It must not be described as executed."
                    ),
                )
            )
            receipt = self.sandbox.run_code(
                code,
                candidate_name="planned_experiment.py",
            )
            self.current_task = {
                "type": "staged_candidate",
                "receipt": receipt,
            }
            return receipt
        except ProviderError as exc:
            return self._provider_failure(exc)
        finally:
            self.state = TwinState.IDLE

    async def experiment(self, code: str) -> dict[str, Any]:
        """Stage experiment code without executing it."""
        self.state = TwinState.TESTING
        try:
            receipt = self.sandbox.run_code(code)
            self._log(
                f"Experiment request ended with {receipt['status']}.",
                mood="neutral",
                context={"candidate_executed": False},
            )
            return receipt
        except ProviderError as exc:
            return self._provider_failure(exc)
        finally:
            self.state = TwinState.IDLE

    async def execute_plan(self) -> dict[str, Any]:
        """Acknowledge an already staged plan; never execute it."""
        if self.current_task is None:
            return {
                "status": "NO_PENDING_PLAN",
                "candidate_executed": False,
            }
        task = self.current_task
        self.current_task = None
        receipt = dict(task.get("receipt") or {})
        return {
            **receipt,
            "status": "PLAN_STAGED_AWAITING_REVIEW",
            "candidate_executed": False,
            "source_mutated": False,
        }

    def runtime_status(self) -> dict[str, Any]:
        return {
            "status": "RUNNING_BOUNDED" if self.running else "IDLE",
            "state": self.state.value,
            "provider_configured": self.teacher is not None,
            "candidate_only": True,
            "source_mutation_enabled": False,
            "generated_code_execution_enabled": False,
            "completed_cycles": self.completed_cycles,
        }

    def stop(self) -> dict[str, Any]:
        self.running = False
        self._log("Bounded candidate coordination batch stopped.", mood="neutral")
        return {"status": "STOPPED", "running": False}
