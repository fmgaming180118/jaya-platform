from __future__ import annotations

import pytest

from jaya_core.brain_v2.engine.runtime import IronEngine
from jaya_core.brain_v2.organism.affective_metabolism import (
    AffectiveControlPolicy,
    AffectiveMetabolismController,
    AffectiveSignal,
    AffectiveSignalConflict,
    ControlSignalSource,
)
from jaya_core.brain_v2.soul.indonesian_responder import IndonesianResponder


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_user_state_requires_explicit_confirmation() -> None:
    with pytest.raises(ValueError, match="confirmation"):
        AffectiveSignal(
            source=ControlSignalSource.USER_CONFIRMED,
            urgency_delta=0.1,
            user_state_confirmed=False,
        )


def test_control_state_is_bounded_and_cannot_relax_safety() -> None:
    controller = AffectiveMetabolismController()
    result = controller.apply(
        AffectiveSignal(
            source=ControlSignalSource.SAFETY,
            urgency_delta=100,
            caution_delta=-100,
            patience_delta=-100,
            escalation_delta=100,
            signal_id="bounded-safety-signal",
        )
    )
    state = result["state"]
    assert isinstance(state, dict)
    assert all(0.0 <= float(state[key]) <= 1.0 for key in (
        "urgency", "caution", "patience", "escalation"
    ))
    assert float(state["caution"]) >= controller.policy.baseline_caution
    decision = result["decision"]
    assert isinstance(decision, dict)
    assert decision["authority_changed"] is False
    assert decision["safety_relaxed"] is False
    assert decision["factual_content_changed"] is False


def test_signal_is_idempotent_and_history_is_bounded() -> None:
    policy = AffectiveControlPolicy(max_signal_history=2)
    controller = AffectiveMetabolismController(policy)
    signal = AffectiveSignal(
        source=ControlSignalSource.TASK,
        urgency_delta=0.2,
        signal_id="same",
    )
    first = controller.apply(signal)
    second = controller.apply(signal)
    assert first["changed"] is True
    assert second["changed"] is False
    assert first["state"] == second["state"]
    with pytest.raises(AffectiveSignalConflict):
        controller.apply(
            AffectiveSignal(
                source=ControlSignalSource.TASK,
                urgency_delta=-0.2,
                signal_id="same",
            )
        )

    controller.apply(AffectiveSignal(ControlSignalSource.TASK, signal_id="next"))
    controller.apply(AffectiveSignal(ControlSignalSource.TASK, signal_id="last"))
    replay = controller.apply(signal)
    assert replay["changed"] is True


def test_state_decays_toward_baseline() -> None:
    clock = _Clock()
    policy = AffectiveControlPolicy(decay_half_life_seconds=10.0)
    controller = AffectiveMetabolismController(policy, monotonic_clock=clock)
    controller.apply(
        AffectiveSignal(
            source=ControlSignalSource.TASK,
            urgency_delta=0.2,
            signal_id="decay",
        )
    )
    clock.value = 10.0
    state = controller.status()["state"]
    assert isinstance(state, dict)
    assert float(state["urgency"]) == pytest.approx(0.30)


def test_runtime_exposes_task_control_without_executing_action() -> None:
    engine = IronEngine("missing.jay", "test-secret", enable_twin=False)
    engine._affective_metabolism = AffectiveMetabolismController()
    engine._lingua = None
    engine._jaya_ir_exec = None

    result = engine.execute_intent("hapus file sementara")
    assert result["ok"] is True
    assert result["result"]["execution_status"] == "NOT_EXECUTED"
    assert result["confirmation_recommended"] is True
    assert result["planner_priority"] in {"normal", "high", "critical"}


def test_responder_adds_control_notice_without_changing_fact() -> None:
    responder = IndonesianResponder()
    result = responder.respond(
        ("QUERY", "QUERY_DEF", "jaya"),
        rag_facts=[{"content": "JAYA adalah runtime lokal."}],
        control_policy={
            "confirmation_recommended": True,
            "interaction_mode": "measured",
        },
    )
    assert "konfirmasi disarankan" in result
    assert "JAYA adalah runtime lokal." in result
