"""CoreTwin — Lightweight Digital Twin for JAYA_CORE AGI Brain.

Architecture
============
The twin runs as an async background loop alongside the IronEngine.
Each cycle it:

  1. Checks the TaskPlanner for queued work.
  2. If idle long enough, performs self-reflection to auto-generate tasks.
  3. Picks the next task, executes it in an isolated Python namespace.
  4. Scores the result and records it in ExperimentMemory.
  5. Reports high-scoring outcomes to the engine for potential application.

This "digital-digital" simulation is the core mechanism that allows JAYA
to continuously improve its own parameters without human intervention.
"""

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from src.brain_v2.extensions.twin.experiment_memory import ExperimentMemory, ExperimentRecord
from src.brain_v2.extensions.twin.task_planner import Task, TaskPlanner, Priority

if TYPE_CHECKING:
    from src.brain_v2.engine.runtime import IronEngine

logger = logging.getLogger("CoreTwin")


# ---------------------------------------------------------------------------
# Scoring helper
# ---------------------------------------------------------------------------

def _compute_score(outcome: Dict[str, Any]) -> float:
    """Derive a numeric score from an experiment's output namespace.

    Looks for a 'score' or 'fitness' key in the output dict.  Falls
    back to 1.0 on clean execution, 0.0 on error.
    """
    if "__error__" in outcome:
        return 0.0
    for key in ("score", "fitness", "reward", "value"):
        if key in outcome:
            try:
                return float(outcome[key])
            except (TypeError, ValueError):
                pass
    return 1.0   # clean run = baseline positive score


# ---------------------------------------------------------------------------
# CoreTwin
# ---------------------------------------------------------------------------

class CoreTwin:
    """Lightweight digital twin for the JAYA_CORE AGI brain.

    Parameters
    ----------
    engine:
        Reference to the owning IronEngine.  May be *None* in tests.
    omniverse_enabled:
        Whether the Omniverse SDK was successfully initialised (currently
        always False — see ``extensions/twin/omniverse.py``).
    reflection_interval:
        Seconds between autonomous self-reflection cycles.
    """

    def __init__(self,
                 engine: Optional["IronEngine"],
                 omniverse_enabled: bool = False,
                 reflection_interval: float = 30.0,
                 memory: Optional[ExperimentMemory] = None):
        self.engine: Optional["IronEngine"] = engine
        self.omniverse_enabled = omniverse_enabled
        self.running           = False
        self._async_task: Optional[asyncio.Task[None]] = None

        # Core sub-systems
        self.memory  = memory if memory is not None else ExperimentMemory()
        self.planner = TaskPlanner()

        # Timing  — initialise to now so first reflection waits a full interval
        self.reflection_interval = reflection_interval
        self._last_reflection: float = time.time()

        # Statistics
        self.cycles_completed = 0
        self.experiments_run  = 0

        # Public log (backwards-compat alias)
        self.log: List[ExperimentRecord] = self.memory.records

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the background consciousness loop."""
        if self.running:
            return
        self.running = True
        logger.info("CoreTwin awakened (omniverse=%s)", self.omniverse_enabled)
        self._async_task = asyncio.create_task(self._loop())

    async def stop(self):
        """Gracefully stop the loop."""
        self.running = False
        if self._async_task and not self._async_task.done():
            self._async_task.cancel()
            try:
                await self._async_task
            except asyncio.CancelledError:
                pass
        logger.info("CoreTwin hibernating | cycles=%d experiments=%d",
                    self.cycles_completed, self.experiments_run)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _loop(self):
        """One tick every 0.5 s; reflection every ``reflection_interval``."""
        while self.running:
            try:
                await self._cycle()
            except Exception as exc:
                logger.error("Cycle error: %s", exc)
            await asyncio.sleep(0.5)

    async def _cycle(self):
        self.cycles_completed += 1
        now = time.time()

        # 1. Auto-suggest a repair task if there are recent errors
        repair = self.planner.suggest_from_memory(self.memory)
        if repair:
            self.planner.push(repair)

        # 2. Self-reflection → generate exploration tasks
        if now - self._last_reflection >= self.reflection_interval:
            await self._reflect()
            self._last_reflection = now

        # 3. Execute the next queued task
        task = self.planner.pop()
        if task:
            await self._execute_task(task)

    # ------------------------------------------------------------------
    # Self-reflection
    # ------------------------------------------------------------------

    async def _reflect(self) -> None:
        """Analyse memory and auto-generate new experiment tasks."""
        summary: Dict[str, Any] = self.memory.summary()
        logger.info("[Reflect] memory=%s", summary)

        ideas: List[Task] = _generate_ideas(summary, self.memory.recent(5))
        for idea in ideas:
            self.planner.push(idea)
            logger.info("[Reflect] queued task: %r priority=%d",
                        idea.label, int(idea.priority))

    # ------------------------------------------------------------------
    # Experiment execution
    # ------------------------------------------------------------------

    async def _execute_task(self, task: Task) -> None:
        """Run ``task.code`` and surface notable results to the engine."""
        result: Dict[str, Any] = await self.run_experiment(
            task.code, label=task.label, score_hint=float(task.score_hint)
        )
        # notify engine if result has a meaningful score
        fb_score: float = float(result.get("score") or result.get("fitness") or 0.0)
        if fb_score and self.engine is not None:
            self.engine.receive_twin_feedback(
                {"task": task.label, "code": task.code, "result": result}
            )

    # ------------------------------------------------------------------
    # Core experiment API (used directly from engine / tests)
    # ------------------------------------------------------------------

    async def run_experiment(self,
                             code: str,
                             label: str = "EXPLORE",
                             score_hint: float = 0.0) -> Dict[str, Any]:
        """Execute *code* in an isolated namespace and return locals."""
        namespace: Dict[str, Any] = {}
        try:
            exec(code, {"__builtins__": __builtins__}, namespace)
            self.experiments_run += 1
        except Exception as exc:
            logger.warning("Experiment error: %s", exc)
            namespace["__error__"] = str(exc)
            label = "ERROR"

        score = max(score_hint, _compute_score(namespace))
        self.memory.record(code=code, outcome=namespace.copy(),
                           score=score, label=label)
        return namespace

    # ------------------------------------------------------------------
    # Engine-facing helpers
    # ------------------------------------------------------------------

    def report(self, metrics: Dict[str, Any]):
        """Receive feedback from engine or external simulation."""
        self.memory.record(code="<external_report>",
                           outcome=metrics,
                           score=float(metrics.get("score", 0.0)),
                           label="REPORT")

    def queue_task(self, code: str,
                   label: str = "OPTIMIZE",
                   priority: int = int(Priority.HIGH)) -> None:
        """Enqueue a task directly from external code."""
        self.planner.push(Task(priority=priority, label=label, code=code))

    def status(self) -> Dict[str, Any]:
        """Return a lightweight status snapshot."""
        mem_summary: Dict[str, Any] = self.memory.summary()
        return {
            "running":      self.running,
            "cycles":       self.cycles_completed,
            "experiments":  self.experiments_run,
            "queue_depth":  len(self.planner),
            "memory":       mem_summary,
            "omniverse":    self.omniverse_enabled,
        }


# ---------------------------------------------------------------------------
# Rule-based idea generator (no LLM — stays lightweight)
# ---------------------------------------------------------------------------

def _generate_ideas(summary: Dict[str, Any],
                    recent: List[ExperimentRecord]) -> List[Task]:
    """Create a small list of Tasks driven by observed memory state."""
    ideas: List[Task] = []

    total: int  = int(summary.get("total") or 0)
    errors: int = int(summary.get("errors") or 0)

    # If error rate > 20 % → schedule a repair
    if total > 0 and (errors / total) > 0.20:
        ideas.append(Task(
            priority=int(Priority.HIGH),
            label="REPAIR",
            code="# placeholder: inspect last failure and patch\npass",
            meta={"reason": "high_error_rate",
                  "error_rate": round(errors / total, 3)},
        ))

    # Always push an EXPLORE task so the brain stays curious
    ideas.append(Task(
        priority=int(Priority.LOW),
        label="EXPLORE",
        code=(
            "import math\n"
            "score = math.log1p(1.0)  # curiosity benchmark\n"
        ),
        score_hint=0.5,
    ))

    return ideas

