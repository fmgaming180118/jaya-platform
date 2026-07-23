"""Pillar 6 — Stochastic Spontaneity.

Injects entropy-driven curiosity bursts into the twin's task queue when
the planner is empty and the brain has been idle for too long.  Random
seed is drawn from ``os.urandom`` so it is physically non-deterministic.

The generated exploration code is a small mathematical / logical
experiment whose score measures something novel — keeping the brain
from settling into a fixed attractor.
"""

import logging
import os
import struct
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("Spontaneity")

# Curiosity code templates; one is chosen based on entropy seed.
_CURIOSITY_TEMPLATES: List[str] = [
    # Logistic-map chaotic exploration
    "r={r:.4f}; x={x:.4f}\nfor _ in range(20): x = r*x*(1-x)\nscore = x",
    # Shannon entropy of a random byte distribution
    (
        "import math, collections\n"
        "data = {data!r}\n"
        "freq = collections.Counter(data)\n"
        "n = len(data)\n"
        "score = -sum((c/n)*math.log2(c/n) for c in freq.values()) / 8.0"
    ),
    # Fibonacci-ratio convergence test
    (
        "a, b = 1, 1\n"
        "for _ in range({steps}):\n"
        "    a, b = b, a + b\n"
        "score = abs(b/a - 1.6180339887) < 1e-6 and 0.9 or 0.5"
    ),
    # Prime density near a random number
    (
        "n = {n}\n"
        "primes = [x for x in range(max(2,n-50), n+50)\n"
        "          if all(x % d != 0 for d in range(2, int(x**0.5)+1))]\n"
        "score = len(primes) / 100.0"
    ),
]


def _entropy_seed() -> int:
    """Return a non-deterministic 32-bit integer from OS entropy."""
    return struct.unpack(">I", os.urandom(4))[0]


def _build_curiosity_code() -> str:
    seed = _entropy_seed()
    template_idx = seed % len(_CURIOSITY_TEMPLATES)
    tpl = _CURIOSITY_TEMPLATES[template_idx]

    # Fill in template-specific parameters from entropy
    seed2 = _entropy_seed()
    if template_idx == 0:
        r_val = 3.5 + (seed2 % 5000) / (5000.0 / 0.499)  # range 3.5–3.999
        x_val = (seed2 % 900 + 50) / 1000.0               # range 0.05–0.94
        return tpl.format(r=r_val, x=x_val)
    elif template_idx == 1:
        byte_data = list(os.urandom(32))
        return tpl.format(data=byte_data)
    elif template_idx == 2:
        steps = 15 + seed2 % 20
        return tpl.format(steps=steps)
    else:
        n = 1000 + seed2 % 8000
        return tpl.format(n=n)


class EntropySpark:
    """Injects stochastic curiosity tasks when the twin is idle.

    Parameters
    ----------
    idle_threshold:
        Seconds of planner-empty time before a curiosity task fires.
    cooldown:
        Minimum seconds between two consecutive sparks.
    """

    def __init__(self,
                 idle_threshold: float = 15.0,
                 cooldown: float = 30.0):
        self.idle_threshold = idle_threshold
        self.cooldown       = cooldown
        self._idle_since:  Optional[float] = None
        self._last_spark:  float = 0.0
        self._spark_count: int   = 0

    def tick(self, twin: Any) -> None:
        """Call each cycle.  Fires a curiosity task when idle long enough."""
        from src.brain_v2.extensions.twin.task_planner import Priority, Task

        now = time.time()

        if len(twin.planner) > 0:
            # reset idle timer whenever there is queued work
            self._idle_since = None
            return

        if self._idle_since is None:
            self._idle_since = now
            return

        idle_duration = now - self._idle_since
        since_last    = now - self._last_spark

        if idle_duration >= self.idle_threshold and since_last >= self.cooldown:
            code = _build_curiosity_code()
            self._spark_count += 1
            logger.info("[Spontaneity spark #%d] injecting curiosity task",
                        self._spark_count)
            twin.planner.push(Task(
                priority=int(Priority.LOW),
                label="EXPLORE",
                code=code,
                score_hint=0.3,
                meta={"source": "entropy_spark", "spark": self._spark_count},
            ))
            self._last_spark = now
            self._idle_since = None   # reset after spark

    def status(self) -> Dict[str, Any]:
        return {
            "sparks":          self._spark_count,
            "idle_threshold":  self.idle_threshold,
            "cooldown":        self.cooldown,
        }
