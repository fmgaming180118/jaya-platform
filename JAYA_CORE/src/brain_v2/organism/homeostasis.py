"""Pillar 5 — Logical Homeostasis.

Periodically audits the brain's cognitive health by scanning
ExperimentMemory.  When degradation is detected (average score drops
below a threshold, or error-rate spikes), a high-priority REPAIR task
is injected into the twin's planner so the brain self-corrects.
"""

import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger("Homeostasis")


class HomeostasisAudit:
    """Logical Homeostasis monitor.

    Parameters
    ----------
    check_interval:
        Seconds between health audits.
    min_avg_score:
        If rolling average score drops below this, emit a REPAIR task.
    max_error_rate:
        If error ratio exceeds this (0–1), emit a REPAIR task.
    window:
        How many recent records to evaluate.
    """

    def __init__(self,
                 check_interval: float = 60.0,
                 min_avg_score: float = 0.40,
                 max_error_rate: float = 0.30,
                 window: int = 20):
        self.check_interval  = check_interval
        self.min_avg_score   = min_avg_score
        self.max_error_rate  = max_error_rate
        self.window          = window
        self._last_check: float = time.time()
        self._alert_count: int  = 0

    # ------------------------------------------------------------------

    def tick(self, twin: Any) -> None:
        """Call this every cycle from the twin (or engine).

        Runs an audit when the interval elapses and queues repair tasks
        as needed.
        """
        now = time.time()
        if now - self._last_check < self.check_interval:
            return
        self._last_check = now
        self._audit(twin)

    # ------------------------------------------------------------------

    def _audit(self, twin: Any) -> None:
        from src.brain_v2.extensions.twin.task_planner import Task, Priority

        recent = twin.memory.recent(self.window)
        if not recent:
            return

        total: int   = len(recent)
        errors: int  = sum(1 for r in recent if r.label == "ERROR")
        avg_score: float = sum(r.score for r in recent) / total
        error_rate: float = errors / total

        issues: List[str] = []
        if avg_score < self.min_avg_score:
            issues.append(f"avg_score={avg_score:.3f} < {self.min_avg_score}")
        if error_rate > self.max_error_rate:
            issues.append(f"error_rate={error_rate:.2f} > {self.max_error_rate}")

        if issues:
            self._alert_count += 1
            reason = "; ".join(issues)
            logger.warning("[Homeostasis Alert #%d] %s — injecting REPAIR",
                           self._alert_count, reason)
            # V18: smart REPAIR based on severity
            if avg_score < self.min_avg_score and error_rate > self.max_error_rate:
                # Both degraded: evolve weights + meta-reflect
                repair_code = (
                    "from src.brain_v2.education.live_evolver import LiveEvolver\n"
                    "evolver = LiveEvolver(engine, max_steps=300)\n"
                    "result = evolver.run_evolution(300)\n"
                    "score = min(1.0, 0.4 + result['delta_fitness'] * 2)\n"
                )
            elif error_rate > self.max_error_rate:
                # High error rate: curriculum self-study
                repair_code = (
                    "from src.brain_v2.engine.self_bootstrap import SelfBootstrap\n"
                    "sb = SelfBootstrap()\n"
                    "tasks = sb.generate_curriculum(twin)\n"
                    "score = 0.6 if tasks else 0.4\n"
                )
            else:
                # Low score: light weight evolution
                repair_code = (
                    "from src.brain_v2.education.live_evolver import LiveEvolver\n"
                    "evolver = LiveEvolver(engine, max_steps=150)\n"
                    "result = evolver.run_evolution(150)\n"
                    "score = min(1.0, 0.5 + result['delta_fitness'])\n"
                )
            twin.planner.push(Task(
                priority=int(Priority.CRITICAL),
                label="REPAIR",
                code=repair_code,
                meta={"reason": reason, "alert": self._alert_count},
            ))
        else:
            logger.debug("[Homeostasis] brain healthy | avg=%.3f errors=%d/%d",
                         avg_score, errors, total)

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {
            "alerts":          self._alert_count,
            "check_interval":  self.check_interval,
            "min_avg_score":   self.min_avg_score,
            "max_error_rate":  self.max_error_rate,
        }
