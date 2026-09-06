"""
proactive_loop.py — Phase 4 Proactive Intelligence Loop Orchestrator for JAYA_CORE

Orchestrates all Phase 4 proactive engine components:
- SpontaneityEngine (Pillars 3, 6)
- SpeculativeReasoner (Pillar 36)
- MetaCognitivePlanner (Pillar 38)
- NarrativeContinuity (Pillar 31)
- CollectivePulse (Pillar 32)
- IntentEngine (Pillar 40)
"""

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from jaya_core.brain_v2.engine.collective_pulse import CollectivePulse
from jaya_core.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
from jaya_core.brain_v2.engine.narrative_continuity import NarrativeContinuity
from jaya_core.brain_v2.engine.speculative import SpeculativeEngine
from jaya_core.brain_v2.engine.spontaneity import (
    ExplorationRequest,
    SpontaneityEngine,
    SpontaneousHypothesis,
)


@dataclass
class ProactiveCycleResult:
    """Result snapshot of a single proactive reasoning loop cycle."""
    cycle_id: str
    spontaneous_hypothesis: Optional[SpontaneousHypothesis] = None
    speculative_predictions: List[Dict[str, Any]] = field(default_factory=list)
    narrative_summary: Optional[str] = None
    pulse_metrics: Dict[str, Any] = field(default_factory=dict)
    meta_strategy: Optional[Dict[str, Any]] = field(default_factory=dict)
    exploration_status: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)


class ProactiveLoop:
    """
    Central orchestrator for Phase 4 Proactive Intelligence.
    Coordinates explicitly authorized proactive work. It never treats silence
    or idle time as implicit permission.
    """

    def __init__(
        self,
        spontaneity_engine: Optional[SpontaneityEngine] = None,
        narrative_continuity: Optional[NarrativeContinuity] = None,
    ):
        self.spontaneity_engine = spontaneity_engine
        self.speculative_engine = SpeculativeEngine()
        self.meta_cognitive = MetaCognitivePlanner()
        self.narrative_continuity = narrative_continuity
        self.collective_pulse = CollectivePulse()
        self.cycle_count = 0

    def run_proactive_cycle(
        self,
        current_intent: str = "general_query",
        cpu_load: float = 0.15,
        is_silence_mode: bool = True,
        exploration_request: Optional[ExplorationRequest] = None,
    ) -> ProactiveCycleResult:
        """Executes a single proactive reasoning cycle across all proactive pillars."""
        self.cycle_count += 1
        cycle_id = f"cycle-{self.cycle_count}-{int(time.time())}"

        # 1. Spontaneity requires an explicit, already-gated request.
        hypo = None
        exploration_status: Dict[str, Any] = {
            "ok": False,
            "status": "EXPLICIT_AUTHORIZATION_REQUIRED",
        }
        if self.spontaneity_engine is not None and exploration_request is not None:
            if exploration_request.silence_active != is_silence_mode:
                exploration_status = {
                    "ok": False,
                    "status": "SILENCE_STATE_MISMATCH",
                }
            else:
                exploration_status = self.spontaneity_engine.explore(exploration_request)
                candidates = exploration_status.get("candidates")
                if exploration_status.get("ok") and isinstance(candidates, list) and candidates:
                    first = candidates[0]
                    if isinstance(first, dict):
                        hypo = SpontaneousHypothesis(
                            hypothesis_id=str(first["hypothesis_id"]),
                            topic=str(first["topic"]),
                            hypothesis_text=str(first["hypothesis_text"]),
                            confidence=float(first["confidence"]),
                            suggested_action=str(first["suggested_action"]),
                            metadata=dict(first["metadata"]),
                            created_at=float(first["created_at"]),
                        )

        # No speculative output is fabricated when no real run took place.
        speculative: List[Dict[str, Any]] = []

        # 3. Narrative Continuity (Pillar 31)
        narrative_summary = (
            self.narrative_continuity._summary
            if self.narrative_continuity is not None
            else None
        )

        # 4. Collective Pulse (Pillar 32)
        pulse = self.collective_pulse.pulse()

        # 5. Meta-Cognitive Planning (Pillar 38)
        meta_strategy = {
            "status": "NOT_EXECUTED",
            "reflect_count": self.meta_cognitive._reflect_count,
        }

        return ProactiveCycleResult(
            cycle_id=cycle_id,
            spontaneous_hypothesis=hypo,
            speculative_predictions=speculative,
            narrative_summary=narrative_summary,
            pulse_metrics=pulse,
            meta_strategy=meta_strategy,
            exploration_status=exploration_status,
        )
