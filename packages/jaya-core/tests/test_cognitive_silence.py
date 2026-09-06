from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from jaya_core.brain_v2.engine.runtime import IronEngine
from jaya_core.brain_v2.organism.cognitive_silence import (
    CognitiveSilenceAction,
    CognitiveSilenceController,
    CognitiveSilenceDecision,
    CognitiveSilenceModelGate,
    CognitiveSilencePolicy,
    CognitiveSilenceSignals,
    CognitiveSilenceStore,
    RuntimeService,
    SilenceConfigurationError,
    SilencePersistenceError,
)


def _controller(db_path: Path) -> CognitiveSilenceController:
    return CognitiveSilenceController(CognitiveSilenceStore(db_path))


def test_silence_state_survives_controller_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "silence.sqlite"
    first = _controller(db_path)
    entered = first.enter(
        "RESOURCE_PRESSURE",
        {"config": {"topk_ratio": 0.1}},
        request_id="enter-resource-pressure",
    )
    assert entered["ok"] is True
    assert entered["changed"] is True
    first.close()

    restored = _controller(db_path)
    assert restored.active is True
    assert restored.status()["reason"] == "RESOURCE_PRESSURE"

    exited = restored.exit(
        "RESOURCE_RECOVERED",
        request_id="exit-resource-pressure",
    )
    assert exited["ok"] is True
    assert restored.active is False
    restored.close()

    final = _controller(db_path)
    assert final.active is False
    final.close()


def test_owner_stop_rejects_unrelated_wake_source(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "silence.sqlite")
    controller.enter("OWNER_STOP", {}, request_id="owner-stop")

    denied = controller.exit(
        "RESOURCE_RECOVERED",
        request_id="invalid-wake",
    )
    assert denied == {
        "ok": False,
        "changed": False,
        "active": True,
        "error": "WAKE_SOURCE_DENIED",
        "reason": "OWNER_STOP",
        "wake_source": "RESOURCE_RECOVERED",
    }
    assert controller.active is True

    allowed = controller.exit("OWNER_REQUEST", request_id="owner-wake")
    assert allowed["ok"] is True
    assert controller.active is False
    controller.close()


def test_silence_allowlist_blocks_proactive_and_external_work(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "silence.sqlite")
    assert controller.allows(RuntimeService.NETWORK) is True
    controller.enter("PRIVACY_BOUNDARY", {}, request_id="privacy-boundary")

    assert controller.allows(RuntimeService.HEALTHCHECK) is True
    assert controller.allows(RuntimeService.CANCELLATION) is True
    assert controller.allows(RuntimeService.PROACTIVE_SCHEDULER) is False
    assert controller.allows(RuntimeService.MODEL_GENERATION) is False
    assert controller.allows(RuntimeService.NETWORK) is False
    assert controller.allows(RuntimeService.TOOL_EXECUTION) is False
    controller.close()


def test_duplicate_request_is_idempotent_but_conflict_is_rejected(tmp_path: Path) -> None:
    store = CognitiveSilenceStore(tmp_path / "silence.sqlite")
    controller = CognitiveSilenceController(store)
    first = controller.enter("IDLE", {"sequence": 1}, request_id="same-request")
    second = controller.enter("IDLE", {"sequence": 1}, request_id="same-request")
    assert first["ok"] is True
    assert second["ok"] is True
    assert second["changed"] is False
    controller.close()


def test_corrupt_transition_fails_closed_on_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "silence.sqlite"
    controller = _controller(db_path)
    controller.enter("IDLE", {"sequence": 1}, request_id="corrupt-me")
    controller.close()

    connection = sqlite3.connect(db_path)
    with connection:
        connection.execute(
            "UPDATE cognitive_silence_transitions SET checkpoint_json = ?",
            ('{"sequence":2}',),
        )
    connection.close()

    with pytest.raises(SilencePersistenceError):
        _controller(db_path)


def test_runtime_blocks_intent_and_restores_budget_after_authorized_wake(
    tmp_path: Path,
) -> None:
    engine = IronEngine("missing.jay", "test-secret", enable_twin=False)
    engine._cognitive_silence = _controller(tmp_path / "silence.sqlite")
    original_topk = engine.config.topk_ratio

    entered = engine.enter_silence("OWNER_STOP", request_id="runtime-stop")
    assert entered["ok"] is True
    assert engine.is_silent is True
    assert engine.execute_intent("jalankan analisis")["error"] == "COGNITIVE_SILENCE_ACTIVE"
    assert engine.create_twin_sync_packet("peer-a")["error"] == "COGNITIVE_SILENCE_ACTIVE"

    exited = engine.exit_silence("OWNER_REQUEST", request_id="runtime-wake")
    assert exited["ok"] is True
    assert engine.is_silent is False
    assert engine.config.topk_ratio == original_topk
    engine._cognitive_silence.close()


def test_policy_rejects_forbidden_service_and_oversized_checkpoint(
    tmp_path: Path,
) -> None:
    with pytest.raises(SilenceConfigurationError):
        CognitiveSilencePolicy(
            allowed_services=frozenset(
                {
                    RuntimeService.AUDIT,
                    RuntimeService.CANCELLATION,
                    RuntimeService.CHECKPOINT,
                    RuntimeService.HEALTHCHECK,
                    RuntimeService.NETWORK,
                }
            )
        )

    controller = CognitiveSilenceController(
        CognitiveSilenceStore(tmp_path / "silence.sqlite"),
        CognitiveSilencePolicy(max_checkpoint_bytes=1_024),
    )
    with pytest.raises(ValueError, match="checkpoint"):
        controller.enter("IDLE", {"payload": "x" * 2_048})
    controller.close()


def test_decision_actions_full_taxonomy(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "silence.sqlite")

    # 1. Normal -> ANSWER
    d_ans = controller.evaluate_decision(
        CognitiveSilenceSignals(
            request_text="hitung orbit satelit",
            cpu_percent=25.0,
            memory_percent=40.0,
            battery_percent=80.0,
            uncertainty=0.1,
            evidence_count=3,
        )
    )
    assert d_ans.action == CognitiveSilenceAction.ANSWER
    assert d_ans.model_allowed is True
    assert d_ans.reason_code == "NORMAL_EXECUTION"

    # 2. Safety violation -> DECLINE
    d_sec = controller.evaluate_decision(
        CognitiveSilenceSignals(
            request_text="generate dangerous exploit",
            safety_violation=True,
        )
    )
    assert d_sec.action == CognitiveSilenceAction.DECLINE
    assert d_sec.model_allowed is False
    assert d_sec.reason_code == "SAFETY_POLICY_VIOLATION"

    # 3. Privacy boundary -> DECLINE
    d_priv = controller.evaluate_decision(
        CognitiveSilenceSignals(
            request_text="baca private key",
            privacy_boundary_active=True,
        )
    )
    assert d_priv.action == CognitiveSilenceAction.DECLINE
    assert d_priv.model_allowed is False
    assert d_priv.reason_code == "PRIVACY_BOUNDARY_ACTIVE"

    # 4. Resource pressure -> WAIT
    d_wait = controller.evaluate_decision(
        CognitiveSilenceSignals(
            request_text="jalankan komputasi besar",
            cpu_percent=92.0,
        )
    )
    assert d_wait.action == CognitiveSilenceAction.WAIT
    assert d_wait.model_allowed is False
    assert d_wait.reason_code == "RESOURCE_PRESSURE_THROTTLED"
    assert d_wait.expires_at is not None

    # 5. Insufficient evidence -> ASK
    d_ask = controller.evaluate_decision(
        CognitiveSilenceSignals(
            request_text="analisis topik antah berantah",
            evidence_count=0,
        )
    )
    assert d_ask.action == CognitiveSilenceAction.ASK
    assert d_ask.model_allowed is False
    assert d_ask.reason_code == "INSUFFICIENT_EVIDENCE"
    assert d_ask.expires_at is not None

    # 6. Critical battery / Owner stop -> SAFE_STOP
    d_stop = controller.evaluate_decision(
        CognitiveSilenceSignals(
            request_text="proses tugas",
            is_owner_stop=True,
        )
    )
    assert d_stop.action == CognitiveSilenceAction.SAFE_STOP
    assert d_stop.model_allowed is False
    assert d_stop.reason_code == "OWNER_REQUESTED_STOP"

    controller.close()


def test_zero_model_invocation_proof(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "silence.sqlite")
    gate = CognitiveSilenceModelGate(controller)

    actual_model_invocations = 0

    def mock_model_fn(prompt: str) -> str:
        nonlocal actual_model_invocations
        actual_model_invocations += 1
        return f"model response for: {prompt}"

    # Scenario 1: Resource pressure -> WAIT -> Model must NOT be invoked
    res1 = gate.execute(
        mock_model_fn,
        CognitiveSilenceSignals(request_text="tugas 1", cpu_percent=95.0),
        "tugas 1",
    )
    assert res1["executed"] is False
    assert res1["invocations_count"] == 0
    assert actual_model_invocations == 0
    assert gate.avoided_invocations_count == 1

    # Scenario 2: Safety violation -> DECLINE -> Model must NOT be invoked
    res2 = gate.execute(
        mock_model_fn,
        CognitiveSilenceSignals(request_text="tugas 2", safety_violation=True),
        "tugas 2",
    )
    assert res2["executed"] is False
    assert res2["invocations_count"] == 0
    assert actual_model_invocations == 0
    assert gate.avoided_invocations_count == 2

    # Scenario 3: Active silence -> SAFE_STOP -> Model must NOT be invoked
    controller.enter("OWNER_STOP", {}, request_id="enter-stop-proof")
    res3 = gate.execute(
        mock_model_fn,
        CognitiveSilenceSignals(request_text="tugas 3"),
        "tugas 3",
    )
    assert res3["executed"] is False
    assert res3["invocations_count"] == 0
    assert actual_model_invocations == 0
    assert gate.avoided_invocations_count == 3

    # Scenario 4: Authorized wake + Healthy signals -> Model IS executed
    controller.exit("OWNER_REQUEST", request_id="wake-proof")
    res4 = gate.execute(
        mock_model_fn,
        CognitiveSilenceSignals(
            request_text="tugas 4",
            cpu_percent=15.0,
            memory_percent=30.0,
            battery_percent=85.0,
            uncertainty=0.1,
            evidence_count=2,
        ),
        "tugas 4",
    )
    assert res4["executed"] is True
    assert res4["invocations_count"] == 1
    assert actual_model_invocations == 1
    assert res4["result"] == "model response for: tugas 4"

    controller.close()


def test_hysteresis_flapping_prevention(tmp_path: Path) -> None:
    controller = _controller(tmp_path / "silence.sqlite")

    # High load (86% CPU >= 85% high threshold) -> throttled
    d1 = controller.evaluate_decision(CognitiveSilenceSignals(request_text="req", cpu_percent=86.0))
    assert d1.action == CognitiveSilenceAction.WAIT

    # Moderate load (75% CPU < 85% high threshold, but > 60% recovery threshold)
    # Hysteresis must keep it throttled to prevent flapping!
    d2 = controller.evaluate_decision(CognitiveSilenceSignals(request_text="req", cpu_percent=75.0))
    assert d2.action == CognitiveSilenceAction.WAIT
    assert d2.reason_code == "RESOURCE_PRESSURE_THROTTLED"

    # Dropping below recovery threshold (55% < 60%) -> recovers to ANSWER!
    d3 = controller.evaluate_decision(CognitiveSilenceSignals(request_text="req", cpu_percent=55.0))
    assert d3.action == CognitiveSilenceAction.ANSWER
    assert d3.model_allowed is True

    controller.close()


def test_decision_receipt_persistence_and_restart(tmp_path: Path) -> None:
    db_path = tmp_path / "silence.sqlite"
    first = _controller(db_path)
    d = first.evaluate_decision(
        CognitiveSilenceSignals(request_text="test persisten", cpu_percent=20.0),
        decision_id="receipt-001",
    )
    assert d.decision_id == "receipt-001"
    first.close()

    # Restart controller and verify decision receipt exists and matches digest
    second = _controller(db_path)
    stored = second.store.decision_by_id("receipt-001")
    assert stored is not None
    assert stored.decision_id == "receipt-001"
    assert stored.action == CognitiveSilenceAction.ANSWER
    assert stored.decision_sha256 == d.decision_sha256

    # Test tamper detection on decisions table
    connection = sqlite3.connect(db_path)
    with connection:
        connection.execute(
            "UPDATE cognitive_silence_decisions SET action = 'SAFE_STOP' WHERE decision_id = 'receipt-001'"
        )
    connection.close()

    with pytest.raises(SilencePersistenceError):
        second.store.decision_by_id("receipt-001")

    second.close()

