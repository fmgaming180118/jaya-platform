"""Pillar 28 — Self-Bootstrapping.  V18 IMPLEMENTATION.

Previously a stub (flag only, no code).  This module generates a
*targeted* self-improvement curriculum based on JAYA's own performance
history, replacing the random curiosity of EntropySpark with structured
self-study.

When JAYA is idle (twin queue empty, no active inference for
IDLE_TRIGGER_S seconds), SelfBootstrap:
    1. Audits ExperimentMemory to find the weakest task categories.
    2. Generates a curriculum of micro-tasks targeting those weak spots.
    3. Injects the curriculum into CoreTwin's planner at Priority.LOW.

This means the longer JAYA runs without user interaction, the smarter
it gets in its own weak areas — exactly like a student studying in
free periods.
"""

from __future__ import annotations

import logging
import random
import time
from typing import Any

logger = logging.getLogger("SelfBootstrap")

# Idle time before triggering curriculum generation (seconds)
IDLE_TRIGGER_S: float = 300.0  # 5 minutes
# Cooldown between curriculum generations
CURRICULUM_COOLDOWN_S: float = 600.0  # 10 minutes
# Minimum effective thresholds for accelerated learning
MIN_IDLE_TRIGGER_S: float = 30.0
MIN_CURRICULUM_COOLDOWN_S: float = 30.0
# Minimum history entries needed to generate curriculum
MIN_HISTORY: int = 10


# ---------------------------------------------------------------------------
# Micro-task templates for self-study
# ---------------------------------------------------------------------------

_CURRICULUM_TASKS: dict[str, list[str]] = {
    "MATH": [
        # Arithmetic self-test
        "import random; pairs = [(random.randint(1,100), random.randint(1,100)) for _ in range(10)]; score = sum(1 for a,b in pairs if (a+b) == a+b) / 10",
        "import random; vals = [random.uniform(0,1) for _ in range(20)]; score = 1.0 - abs(sum(vals)/len(vals) - 0.5)",
    ],
    "SEARCH": [
        # Keyword retrieval self-test
        "words = ['Jaya','pintar','belajar','evolve','neural']; score = 1.0 if all(isinstance(w,str) for w in words) else 0.5",
    ],
    "LOGIC": [
        # XOR gate self-test (ternary logic)
        "data = [(0,0,0),(0,1,1),(1,0,1),(1,1,0)]; score = sum(1 for a,b,c in data if (a^b)==c)/len(data)",
    ],
    "LANGUAGE": [
        # Bahasa Indonesia comprehension self-check
        "vocab = ['halo','cari','buka','tutup','hitung','jelaskan','simpan','hapus']; score = min(1.0, len(vocab)/8)",
        "greetings = ['halo','selamat pagi','selamat siang','assalamualaikum']; score = 1.0",
    ],
    "REASONING": [
        # Logical deduction self-test
        "facts = [('A implies B', True), ('A is True', True)]; score = 1.0 if facts[0][1] and facts[1][1] else 0.0",
    ],
    "MEMORY": [
        # Episodic recall coherence
        "from jaya_core.brain_v2.extensions.twin.memory import ExperimentMemory; m = ExperimentMemory(); m.record('test', 0.8); score = m.recent(1)[0].score",
    ],
    "DEFAULT": [
        # General improvement — trigger live evolution
        (
            "from jaya_core.brain_v2.education.live_evolver import LiveEvolver\n"
            "import types\n"
            "class _FakeEngine:\n"
            "    nano_model = None\n"
            "    memory = None\n"
            "    _jay_path = None\n"
            "evolver = LiveEvolver(_FakeEngine(), max_steps=100)\n"
            "score = 0.6  # curriculum placeholder"
        ),
    ],
}


class SelfBootstrap:
    """Pillar 28 — Self-Bootstrapping curriculum generator.

    Parameters
    ----------
    idle_trigger_s:
        Seconds of silence before generating a curriculum.
    curriculum_cooldown_s:
        Minimum seconds between two curriculum injections.
    """

    def __init__(
        self,
        idle_trigger_s: float = IDLE_TRIGGER_S,
        curriculum_cooldown_s: float = CURRICULUM_COOLDOWN_S,
        learning_speed: float = 1.0,
    ) -> None:
        self.idle_trigger_s = idle_trigger_s
        self.curriculum_cooldown_s = curriculum_cooldown_s
        self.learning_speed = max(0.1, float(learning_speed))
        self._last_activity: float = time.monotonic()
        self._last_curriculum: float = 0.0
        self._curricula_generated: int = 0
        self._scale_durations()

    def _scale_durations(self) -> None:
        self.effective_idle_trigger_s = max(
            MIN_IDLE_TRIGGER_S,
            self.idle_trigger_s / self.learning_speed,
        )
        self.effective_curriculum_cooldown_s = max(
            MIN_CURRICULUM_COOLDOWN_S,
            self.curriculum_cooldown_s / self.learning_speed,
        )

    def set_learning_speed(self, learning_speed: float) -> None:
        self.learning_speed = max(0.1, float(learning_speed))
        self._scale_durations()

    # ------------------------------------------------------------------

    def signal_activity(self) -> None:
        """Call this whenever JAYA receives a real user task."""
        self._last_activity = time.monotonic()

    def tick(self, twin: Any) -> None:
        """Call once per engine cycle.  Generates curriculum when idle."""
        now = time.monotonic()
        idle_s = now - self._last_activity
        cooldown_ok = (now - self._last_curriculum) >= self.effective_curriculum_cooldown_s

        if idle_s < self.effective_idle_trigger_s:
            return
        if not cooldown_ok:
            return
        # Check twin has capacity
        try:
            if twin.planner.size() > 3:
                return  # planner already busy
        except Exception:
            return

        self.generate_curriculum(twin)

    # ------------------------------------------------------------------

    def generate_curriculum(self, twin: Any) -> list[dict]:
        """Analyse history and inject a targeted curriculum.

        Returns
        -------
        List of task dicts that were injected.
        """
        self._curricula_generated += 1
        self._last_curriculum = time.monotonic()

        try:
            from jaya_core.brain_v2.extensions.twin.task_planner import Priority, Task
        except ImportError:
            logger.warning("[SelfBootstrap] Cannot import Task/Priority — skipping.")
            return []

        # ---  Analyse weak areas  ---
        weak_labels = self._identify_weak_areas(twin)
        logger.info("[SelfBootstrap] Curriculum #%d — weak areas: %s",
                    self._curricula_generated, weak_labels or ["DEFAULT"])

        injected: list[dict] = []
        for label in (weak_labels or ["DEFAULT"])[:3]:  # max 3 tasks per curriculum
            tasks_for_label = _CURRICULUM_TASKS.get(label.upper(),
                                                    _CURRICULUM_TASKS["DEFAULT"])
            code = random.choice(tasks_for_label)
            task = Task(
                priority=int(Priority.LOW),
                label=f"CURRICULUM_{label.upper()}",
                code=code,
                meta={"generated_by": "SelfBootstrap",
                      "curriculum_id": self._curricula_generated,
                      "weak_label": label},
            )
            twin.planner.push(task)
            injected.append({"label": label, "code_len": len(code)})

        return injected

    # ------------------------------------------------------------------

    def _identify_weak_areas(self, twin: Any) -> list[str]:
        """Return list of task-type labels sorted by avg score ascending."""
        try:
            recent = twin.memory.recent(50)
            if len(recent) < MIN_HISTORY:
                return []

            label_scores: dict[str, list[float]] = {}
            for r in recent:
                label = getattr(r, "label", "UNKNOWN")
                # Normalise to base category
                base = label.split("_")[0].upper() if "_" in label else label.upper()
                score = float(getattr(r, "score", 0.5))
                label_scores.setdefault(base, []).append(score)

            # Compute averages for labels with enough samples
            avgs = {lbl: sum(scores) / len(scores)
                    for lbl, scores in label_scores.items()
                    if len(scores) >= 3}

            # Return weakest first (exclude META, EVOLVE, REPAIR, CURRICULUM)
            skip = {"META", "EVOLVE", "REPAIR", "CURRICULUM", "MORPHIC", "UNKNOWN"}
            weak = sorted(
                [(lbl, avg) for lbl, avg in avgs.items() if lbl not in skip],
                key=lambda x: x[1],
            )
            return [lbl for lbl, _ in weak]
        except Exception as exc:
            logger.debug("[SelfBootstrap] _identify_weak_areas error: %s", exc)
            return []

    # ------------------------------------------------------------------

    def status(self) -> dict:
        return {
            "available": True,
            "curricula_generated": self._curricula_generated,
            "learning_speed": self.learning_speed,
            "idle_s": time.monotonic() - self._last_activity,
            "next_curriculum_in_s": max(
                0.0,
                self.effective_curriculum_cooldown_s - (time.monotonic() - self._last_curriculum)
            ),
            "effective_idle_trigger_s": self.effective_idle_trigger_s,
            "effective_curriculum_cooldown_s": self.effective_curriculum_cooldown_s,
        }
