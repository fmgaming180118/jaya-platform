"""Canonical integration coverage for regulation pillars P6/P7/P10/P17."""

from __future__ import annotations

from pathlib import Path

import pytest
import requests

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.regulation_capabilities import (
    AFFECTIVE_CAPABILITY_ID,
    SILENCE_CAPABILITY_ID,
)

OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_MODEL = "qwen3.5:0.8b"


def _runtime(root: Path, *, with_model: bool = False) -> JayaCoreRuntime:
    return JayaCoreRuntime(
        db_path=root / "core.sqlite3",
        local_pillar_data_dir=root / "pillars",
        node_id="regulation-test-node",
        ollama_base_url=OLLAMA_URL if with_model else None,
        local_model_name=OLLAMA_MODEL if with_model else None,
        local_model_timeout_seconds=90.0,
    )


def _cycle_request(suffix: str = "1") -> dict[str, object]:
    claim = "The candidate remains an unverified research hypothesis."
    return {
        "source_ref": f"artifact:regulation-evidence-{suffix}",
        "title": "Battery measurement constraints",
        "content": (
            "Repeated battery degradation measurements require bounded sampling, "
            "explicit uncertainty, and independent empirical review before adoption."
        ),
        "topic": "bounded battery degradation exploration",
        "exploration_request_id": f"exploration-{suffix}",
        "decision_id": f"decision-{suffix}",
        "signal": {
            "source": "TASK",
            "caution_delta": 0.2,
            "signal_id": f"signal-{suffix}",
        },
        "risk": 0.8,
        "uncertainty": 0.8,
        "novelty": 0.8,
        "impact": 0.8,
        "claim": claim,
        "facts": ["evidence.present"],
        "rules": [
            {
                "id": "evidence-supports-review",
                "if": ["evidence.present"],
                "then": "action.supported",
            }
        ],
        "evidence_query": "battery degradation measurements uncertainty",
        "logic_query": "action.supported",
        "seed": 17,
    }


def _ollama_ready() -> bool:
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        response.raise_for_status()
        return any(item.get("name") == OLLAMA_MODEL for item in response.json()["models"])
    except (KeyError, TypeError, ValueError, requests.RequestException):
        return False


def test_cognitive_silence_and_affective_control_use_canonical_runtime_and_restart(
    tmp_path: Path,
) -> None:
    first = _runtime(tmp_path)
    entered = first.execute_local_pillar(
        SILENCE_CAPABILITY_ID,
        {
            "action": "enter",
            "reason": "OWNER_STOP",
            "checkpoint": {"request": "owner pause"},
            "request_id": "owner-stop-1",
        },
    )
    affected = first.execute_local_pillar(
        AFFECTIVE_CAPABILITY_ID,
        {
            "action": "apply",
            "source": "TASK",
            "caution_delta": 0.2,
            "signal_id": "caution-1",
        },
    )
    assert entered.data["active"] is True
    assert affected.data["decision"]["authority_changed"] is False
    first.close()

    restarted = _runtime(tmp_path)
    try:
        status = restarted.execute_local_pillar(
            SILENCE_CAPABILITY_ID, {"action": "status"}
        )
        assert status.data["active"] is True
        exited = restarted.execute_local_pillar(
            SILENCE_CAPABILITY_ID,
            {
                "action": "exit",
                "wake_source": "OWNER_REQUEST",
                "request_id": "owner-wake-1",
            },
        )
        assert exited.data["active"] is False
    finally:
        restarted.close()


def test_cognitive_silence_rejects_wrong_wake_source(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    try:
        runtime.execute_local_pillar(
            SILENCE_CAPABILITY_ID,
            {
                "action": "enter",
                "reason": "OWNER_STOP",
                "checkpoint": {},
                "request_id": "owner-stop-2",
            },
        )
        with pytest.raises(LocalPillarError) as denied:
            runtime.execute_local_pillar(
                SILENCE_CAPABILITY_ID,
                {
                    "action": "exit",
                    "wake_source": "RESOURCE_RECOVERED",
                    "request_id": "wrong-wake-2",
                },
            )
        assert denied.value.code == "WAKE_SOURCE_DENIED"
        with pytest.raises(LocalPillarError) as invalid_boolean:
            runtime.execute_local_pillar(
                AFFECTIVE_CAPABILITY_ID,
                {
                    "action": "apply",
                    "source": "USER_CONFIRMED",
                    "signal_id": "invalid-confirmation",
                    "user_state_confirmed": "true",
                },
            )
        assert invalid_boolean.value.code == "INVALID_INPUT"
        first_signal = {
            "action": "apply",
            "source": "SAFETY",
            "signal_id": "bound-signal",
            "caution_delta": 0.2,
        }
        runtime.execute_local_pillar(AFFECTIVE_CAPABILITY_ID, first_signal)
        replay = runtime.execute_local_pillar(AFFECTIVE_CAPABILITY_ID, first_signal)
        assert replay.data["changed"] is False
        with pytest.raises(LocalPillarError) as conflict:
            runtime.execute_local_pillar(
                AFFECTIVE_CAPABILITY_ID,
                {**first_signal, "caution_delta": -0.2},
            )
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"
    finally:
        runtime.close()


@pytest.mark.skipif(not _ollama_ready(), reason="BLOCKED_EXTERNAL: Ollama model unavailable")
def test_live_ollama_regulation_cycle_is_grounded_persistent_and_restart_safe(
    tmp_path: Path,
) -> None:
    first = _runtime(tmp_path, with_model=True)
    request = _cycle_request()
    try:
        result = first.execute_integrated_regulation_cycle(request)
        assert result["status"] == "INTEGRATED_REGULATION_CYCLE_COMPLETED"
        assert result["pillars"] == ["P006", "P007", "P010", "P017"]
        assert result["exploration"]["status"] == "UNVERIFIED"
        assert result["socratic_review"]["receipt"]["review"]["status"] == "ALLOWED"
        assert result["socratic_review"]["receipt"]["review"]["proof"]["status"] == "PROVED"
    finally:
        first.close()

    restarted = _runtime(tmp_path, with_model=True)
    try:
        replayed = restarted.execute_integrated_regulation_cycle(request)
        assert replayed["exploration"]["status"] == "REPLAYED_RECEIPT"
        assert replayed["socratic_review"]["status"] == "REPLAYED_REVIEW"
    finally:
        restarted.close()
