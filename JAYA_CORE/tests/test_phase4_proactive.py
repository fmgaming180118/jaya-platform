"""
test_phase4_proactive.py — Integration tests for Phase 4 Proactive Intelligence in JAYA_CORE
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.brain_v2.engine.spontaneity import SpontaneityEngine, SpontaneousHypothesis
from src.brain_v2.engine.speculative import SpeculativeEngine
from src.brain_v2.engine.collective_pulse import CollectivePulse
from src.brain_v2.engine.narrative_continuity import NarrativeContinuity
from src.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
from src.brain_v2.engine.proactive_loop import ProactiveLoop, ProactiveCycleResult


def test_spontaneity_engine():
    """Test SpontaneityEngine active dreaming and hypothesis generation."""
    engine = SpontaneityEngine()
    assert engine.is_idle_trigger(cpu_load=0.10, is_silence_mode=True)
    
    hypo = engine.generate_hypothesis(topic="quantum_compiler_optimization")
    assert isinstance(hypo, SpontaneousHypothesis)
    assert hypo.topic == "quantum_compiler_optimization"
    assert hypo.confidence > 0.0
    assert len(engine.get_dream_history()) == 1


def test_speculative_engine():
    """Test SpeculativeEngine instance initialization."""
    engine = SpeculativeEngine()
    assert engine.n_paths > 0


def test_meta_cognitive_planner():
    """Test MetaCognitivePlanner initialization."""
    meta = MetaCognitivePlanner()
    assert meta.reflect_interval > 0.0


def test_narrative_continuity():
    """Test NarrativeContinuity thread and event logging."""
    narrative = NarrativeContinuity()
    narrative.remember_turn("user input", response_text="Testing Phase 4 Narrative")
    assert len(narrative._events) > 0


def test_collective_pulse():
    """Test CollectivePulse multi-agent health snapshot."""
    pulse = CollectivePulse()
    snapshot = pulse.pulse()
    assert isinstance(snapshot, dict)


def test_proactive_loop_end_to_end():
    """Test end-to-end ProactiveLoop cycle execution across all Phase 4 pillars."""
    loop = ProactiveLoop()
    res = loop.run_proactive_cycle(current_intent="open_dashboard", cpu_load=0.10, is_silence_mode=True)
    
    assert isinstance(res, ProactiveCycleResult)
    assert res.cycle_id.startswith("cycle-1-")
    assert res.spontaneous_hypothesis is not None
    assert len(res.speculative_predictions) > 0
    assert res.pulse_metrics is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
