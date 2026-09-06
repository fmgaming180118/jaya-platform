"""
test_phase4_proactive.py — Integration tests for Phase 4 Proactive Intelligence in JAYA_CORE
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jaya_core.brain_v2.engine.spontaneity import (
    ExplorationError,
    ExplorationReceiptStore,
    SpontaneityEngine,
)
from jaya_core.brain_v2.engine.speculative import SpeculativeEngine
from jaya_core.brain_v2.engine.collective_pulse import CollectivePulse
from jaya_core.brain_v2.engine.narrative_continuity import NarrativeContinuity
from jaya_core.brain_v2.engine.meta_cognitive import MetaCognitivePlanner
from jaya_core.brain_v2.engine.proactive_loop import ProactiveLoop, ProactiveCycleResult
from narrative_test_support import TestNarrativeSigner


def test_spontaneity_engine_fails_closed_without_authorization(tmp_path):
    """Idle/silence never authorizes hypothesis generation."""
    engine = SpontaneityEngine(ExplorationReceiptStore(tmp_path / "spontaneity.db"))
    assert not engine.is_idle_trigger(
        cpu_load=0.10,
        is_silence_mode=True,
        authorized=False,
    )
    with pytest.raises(ExplorationError) as exc_info:
        engine.generate_hypothesis(topic="quantum_compiler_optimization")
    assert exc_info.value.code == "PERMISSION_DENIED"
    engine.close()


def test_speculative_engine():
    """Test SpeculativeEngine instance initialization."""
    engine = SpeculativeEngine()
    assert engine.n_paths > 0


def test_meta_cognitive_planner():
    """Test MetaCognitivePlanner initialization."""
    meta = MetaCognitivePlanner()
    assert meta.reflect_interval > 0.0


def test_narrative_continuity(tmp_path):
    """Test NarrativeContinuity thread and event logging."""
    narrative = NarrativeContinuity(
        tmp_path / "narrative.sqlite3", TestNarrativeSigner()
    )
    narrative.remember_turn("user input", response_text="Testing Phase 4 Narrative")
    assert len(narrative._events) > 0
    narrative.close()


def test_collective_pulse():
    """Test CollectivePulse multi-agent health snapshot."""
    pulse = CollectivePulse()
    snapshot = pulse.pulse()
    assert isinstance(snapshot, dict)


def test_proactive_loop_does_not_fabricate_unexecuted_results():
    """No request means no spontaneous or speculative output."""
    loop = ProactiveLoop()
    res = loop.run_proactive_cycle(current_intent="open_dashboard", cpu_load=0.10, is_silence_mode=True)
    
    assert isinstance(res, ProactiveCycleResult)
    assert res.cycle_id.startswith("cycle-1-")
    assert res.spontaneous_hypothesis is None
    assert res.speculative_predictions == []
    assert res.exploration_status["status"] == "EXPLICIT_AUTHORIZATION_REQUIRED"
    assert res.pulse_metrics is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
