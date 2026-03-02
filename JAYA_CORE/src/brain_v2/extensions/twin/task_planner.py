"""Task queue and planner for the digital twin.

Tasks represent ideas the twin wants to try. They are stored in a
priority queue; the twin dequeues one task per cycle and runs it as
an experiment.
"""
import heapq
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.brain_v2.extensions.twin.experiment_memory import ExperimentMemory


class Priority(IntEnum):
    CRITICAL = 0   # repair a known failure
    HIGH     = 1   # engine-requested optimization
    MEDIUM   = 2   # self-generated improvement idea
    LOW      = 3   # exploratory / curiosity-driven


@dataclass(order=True)
class Task:
    """A unit of work for the digital twin to experiment with."""
    priority: int           = field(compare=True)
    created:  float         = field(compare=False, default_factory=time.time)
    label:    str           = field(compare=False, default="EXPLORE")
    code:     str           = field(compare=False, default="")
    score_hint: float       = field(compare=False, default=0.0)
    meta:     Dict[str, Any] = field(compare=False, default_factory=lambda: {})  # type: ignore[misc]


class TaskPlanner:
    """Maintains a priority heap of tasks for the twin to work through.

    Usage::

        planner = TaskPlanner()
        planner.push(Task(Priority.HIGH, label="OPTIMIZE",
                          code="result = best_sparsity(weights)"))
        task = planner.pop()   # returns highest-priority task
    """

    def __init__(self, max_size: int = 200):
        self._heap: List[Task] = []
        self.max_size = max_size

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def push(self, task: Task):
        """Enqueue a task, dropping the lowest-priority item if at capacity."""
        if len(self._heap) >= self.max_size:
            # drop the lowest-priority (highest int) item
            self._heap.sort()
            self._heap.pop()
        heapq.heappush(self._heap, task)

    def pop(self) -> Optional[Task]:
        """Dequeue the highest-priority task, or None if empty."""
        if not self._heap:
            return None
        return heapq.heappop(self._heap)

    def peek(self) -> Optional[Task]:
        """Inspect the next task without removing it."""
        return self._heap[0] if self._heap else None

    def __len__(self) -> int:
        return len(self._heap)

    def suggest_from_memory(self, memory: "ExperimentMemory") -> Optional[Task]:
        """Auto-generate a repair task if the memory has recent errors."""
        failed_recs = memory.failed(n=1)
        if not failed_recs:
            return None
        last_fail = failed_recs[-1]
        repair_code = f"# auto-repair attempt for: {last_fail.code[:60]!r}\npass"
        task = Task(priority=int(Priority.CRITICAL), label="REPAIR",
                    code=repair_code,
                    meta={"origin": "auto_suggest", "src_ts": float(last_fail.timestamp)})
        return task
