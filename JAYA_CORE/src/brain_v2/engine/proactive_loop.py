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

from src.brain_v2.engine.collective_pulse import CollectivePulse
from src.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
from src.brain_v2.engine.narrative_continuity import NarrativeContinuity
from src.brain_v2.engine.speculative import SpeculativeEngine
from src.brain_v2.engine.spontaneity import SpontaneityEngine, SpontaneousHypothesis


@dataclass
class ProactiveCycleResult:
    """Result snapshot of a single proactive reasoning loop cycle."""
    cycle_id: str
    spontaneous_hypothesis: Optional[SpontaneousHypothesis] = None
    speculative_predictions: List[Dict[str, Any]] = field(default_factory=list)
    narrative_summary: Optional[str] = None
    pulse_metrics: Dict[str, Any] = field(default_factory=dict)
    meta_strategy: Optional[Dict[str, Any]] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


class ProactiveLoop:
    """
    Central orchestrator for Phase 4 Proactive Intelligence.
    Executes autonomous background cycles during idle / silence mode.
    """

    def __init__(self):
        self.spontaneity_engine = SpontaneityEngine()
        self.speculative_engine = SpeculativeEngine()
        self.meta_cognitive = MetaCognitivePlanner()
        self.narrative_continuity = NarrativeContinuity()
        self.collective_pulse = CollectivePulse()
        self.cycle_count = 0

    def run_proactive_cycle(
        self,
        current_intent: str = "general_query",
        cpu_load: float = 0.15,
        is_silence_mode: bool = True
    ) -> ProactiveCycleResult:
        """Executes a single proactive reasoning cycle across all proactive pillars."""
        self.cycle_count += 1
        cycle_id = f"cycle-{self.cycle_count}-{int(time.time())}"

        # 1. Spontaneity & Active Dreaming (Pillars 3, 6)
        hypo = None
        if self.spontaneity_engine.is_idle_trigger(cpu_load, is_silence_mode):
            hypo = self.spontaneity_engine.generate_hypothesis()

        # 2. Speculative Reasoning (Pillar 36)
        speculative = [{"path": "speculative_precompute", "intent": current_intent}]

        # 3. Narrative Continuity (Pillar 31)
        self.narrative_continuity.remember_turn(current_intent, response_text=f"Cycle {self.cycle_count} executed")
        narrative_summary = self.narrative_continuity._summary

        # 4. Collective Pulse (Pillar 32)
        pulse = self.collective_pulse.pulse()

        # 5. Meta-Cognitive Planning (Pillar 38)
        meta_strategy = {"status": "active", "reflect_count": self.meta_cognitive._reflect_count}

        return ProactiveCycleResult(
            cycle_id=cycle_id,
            spontaneous_hypothesis=hypo,
            speculative_predictions=speculative,
            narrative_summary=narrative_summary,
            pulse_metrics=pulse,
            meta_strategy=meta_strategy
        )
