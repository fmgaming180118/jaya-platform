"""Pillar 27 — Temporal Weighting.

Memory records decay in relevance over time via exponential decay:

    weighted_score = score * exp( -λ * Δt )

where Δt = now − record.timestamp and λ controls how fast memories fade.

The module provides:
* ``TemporalWeighter`` — per-instance weighter with configurable λ.
* ``best_recent(memory, n)`` — drop-in replacement for ``memory.best()``
  that respects recency bias.
* ``score_with_decay(record)`` — utility for external callers.
"""

import math
import time
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from jaya_core.brain_v2.extensions.twin.experiment_memory import (
        ExperimentMemory,
        ExperimentRecord,
    )


class TemporalWeighter:
    """Exponential time-decay scorer for experiment records.

    Parameters
    ----------
    decay_rate:
        λ in ``exp(-λ * Δt_hours)``.  Default 0.1 means a record loses
        ~10 % of its relevance per hour; after 24 h it retains ~9 %.
    """

    def __init__(self, decay_rate: float = 0.1):
        self.decay_rate = decay_rate

    # ------------------------------------------------------------------

    def weighted_score(self, record: "ExperimentRecord",
                       now: float = 0.0) -> float:
        """Return the time-decayed score for *record*."""
        t = now or time.time()
        delta_hours = (t - record.timestamp) / 3600.0
        return record.score * math.exp(-self.decay_rate * delta_hours)

    def rerank(self, records: "List[ExperimentRecord]",
               top_n: int = 5) -> "List[ExperimentRecord]":
        """Return top-*n* records reranked by time-decayed score."""
        now = time.time()
        return sorted(records,
                      key=lambda r: self.weighted_score(r, now),
                      reverse=True)[:top_n]

    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        return {"decay_rate": self.decay_rate}


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

_default_weighter = TemporalWeighter()


def best_recent(memory: "ExperimentMemory",
                n: int = 5,
                decay_rate: float = 0.1) -> "List[ExperimentRecord]":
    """Return the *n* most relevant records weighted by recency and score."""
    weighter = TemporalWeighter(decay_rate=decay_rate)
    return weighter.rerank(memory.records, top_n=n)


def score_with_decay(record: "ExperimentRecord",
                     decay_rate: float = 0.1) -> float:
    """Convenient single-record decayed score."""
    return TemporalWeighter(decay_rate=decay_rate).weighted_score(record)
