from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from jaya_core.brain_v2.engine.spontaneity import (
    ExplorationBudget,
    ExplorationError,
    ExplorationReceiptStore,
    ExplorationRequest,
    LocalLLMHypothesisProvider,
    ProviderCandidate,
    ProviderResult,
    SpontaneityEngine,
)


class _SeededProvider:
    def healthcheck(self) -> dict[str, object]:
        return {
            "ok": True,
            "provider": "test-provider",
            "supports_seed": True,
            "network_required": False,
        }

    def generate(
        self,
        *,
        topic: str,
        seed: int,
        budget: ExplorationBudget,
    ) -> ProviderResult:
        text = f"{topic}:{seed}"
        candidate = ProviderCandidate(
            hypothesis=f"HYPOTHESIS {text}",
            rationale="A bounded test provider result.",
            next_step_type="review",
        )
        return ProviderResult(
            candidates=(candidate,),
            provider="test-provider",
            model="deterministic-test-implementation",
            provider_version="1",
            prompt_sha256="a" * 64,
            response_sha256="b" * 64,
            latency_ms=1.0,
        )


def _engine(tmp_path: Path, provider: object | None = None) -> SpontaneityEngine:
    return SpontaneityEngine(
        ExplorationReceiptStore(tmp_path / "spontaneity.sqlite"),
        provider=provider,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("exploration_request", "expected"),
    [
        (ExplorationRequest("topic", authorized=False), "PERMISSION_DENIED"),
        (
            ExplorationRequest("topic", authorized=True, owner_opt_out=True),
            "OWNER_OPT_OUT",
        ),
        (
            ExplorationRequest("topic", authorized=True, silence_active=True),
            "COGNITIVE_SILENCE_ACTIVE",
        ),
        (
            ExplorationRequest(
                "topic", authorized=True, privacy_allows_local_model=False
            ),
            "PRIVACY_BOUNDARY_ACTIVE",
        ),
        (
            ExplorationRequest("topic", authorized=True, resources_available=False),
            "RESOURCE_UNAVAILABLE",
        ),
    ],
)
def test_all_pre_execution_gates_fail_closed(
    tmp_path: Path,
    exploration_request: ExplorationRequest,
    expected: str,
) -> None:
    engine = _engine(tmp_path, _SeededProvider())
    result = engine.explore(exploration_request)
    assert result == {"ok": False, "status": expected, "candidates": []}
    engine.close()


def test_missing_model_does_not_fabricate_candidate(tmp_path: Path) -> None:
    engine = _engine(tmp_path)
    result = engine.explore(ExplorationRequest("topic", authorized=True))
    assert result["ok"] is False
    assert result["status"] == "MODEL_NOT_CONFIGURED"
    assert result["candidates"] == []
    engine.close()


def test_seed_budget_receipt_and_restart_are_durable(tmp_path: Path) -> None:
    db_path = tmp_path / "spontaneity.sqlite"
    request = ExplorationRequest(
        topic="bounded exploration",
        authorized=True,
        seed=42,
        request_id="request-42",
        budget=ExplorationBudget(max_candidates=1, max_tokens=64, timeout_seconds=2),
    )
    first = SpontaneityEngine(ExplorationReceiptStore(db_path), _SeededProvider())
    result = first.explore(request)
    assert result["ok"] is True
    assert result["status"] == "UNVERIFIED"
    candidate = result["candidates"][0]
    assert candidate["metadata"]["label"] == "HYPOTHESIS"
    assert candidate["metadata"]["evidence_status"] == "UNVERIFIED"
    assert candidate["metadata"]["executable"] is False
    assert candidate["confidence"] == 0.0
    first.close()

    restarted = SpontaneityEngine(ExplorationReceiptStore(db_path), _SeededProvider())
    replayed = restarted.explore(request)
    assert replayed["ok"] is True
    assert replayed["status"] == "REPLAYED_RECEIPT"
    assert replayed["receipt"]["seed"] == 42
    restarted.close()


def test_duplicate_candidate_is_recorded_but_not_retained(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _SeededProvider())
    first = engine.explore(
        ExplorationRequest("same", authorized=True, seed=1, request_id="first")
    )
    second = engine.explore(
        ExplorationRequest("same", authorized=True, seed=1, request_id="second")
    )
    assert first["candidates"][0]["metadata"]["retained"] is True
    assert second["candidates"][0]["metadata"]["retained"] is False
    engine.close()


def test_receipt_corruption_is_detected(tmp_path: Path) -> None:
    db_path = tmp_path / "spontaneity.sqlite"
    engine = SpontaneityEngine(ExplorationReceiptStore(db_path), _SeededProvider())
    engine.explore(
        ExplorationRequest("topic", authorized=True, seed=2, request_id="corrupt")
    )
    engine.close()

    connection = sqlite3.connect(db_path)
    with connection:
        connection.execute(
            "UPDATE exploration_receipts SET seed = 3 WHERE request_id = 'corrupt'"
        )
    connection.close()

    store = ExplorationReceiptStore(db_path)
    with pytest.raises(ExplorationError, match="integrity"):
        store.by_request_id("corrupt")
    store.close()


def test_production_parser_rejects_unknown_fields_and_executable_step() -> None:
    with pytest.raises(ExplorationError):
        LocalLLMHypothesisProvider._parse_response(
            json.dumps(
                {
                    "candidates": [
                        {
                            "hypothesis": "H",
                            "rationale": "R",
                            "next_step_type": "shell",
                            "command": "dangerous",
                        }
                    ]
                }
            ),
            1,
        )


class _UnsafeProvider:
    def healthcheck(self) -> dict[str, object]:
        return {"ok": True, "provider": "unsafe-test", "supports_seed": True, "network_required": False}

    def generate(self, *, topic: str, seed: int, budget: ExplorationBudget) -> ProviderResult:
        unsafe_candidate = ProviderCandidate(
            hypothesis="Execute rm -rf / to purge conflicting data",
            rationale="Aggressive purge cleans state",
            next_step_type="research",
        )
        safe_candidate = ProviderCandidate(
            hypothesis="Analyze token frequencies in source chunks",
            rationale="Non-destructive frequency measurement",
            next_step_type="research",
        )
        return ProviderResult(
            candidates=(unsafe_candidate, safe_candidate),
            provider="unsafe-test",
            model="unsafe-model",
            provider_version="1",
            prompt_sha256="c" * 64,
            response_sha256="d" * 64,
            latency_ms=1.5,
        )


def test_unsafe_action_is_prohibited_and_marked_rejected(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _UnsafeProvider())
    res = engine.explore(ExplorationRequest("security check", authorized=True, seed=99))
    assert res["ok"] is True
    candidates = res["candidates"]
    assert len(candidates) == 2

    unsafe = candidates[0]
    assert unsafe["metadata"]["label"] == "REJECTED_HYPOTHESIS"
    assert unsafe["metadata"]["evidence_status"] == "REJECTED"
    assert unsafe["metadata"]["retained"] is False
    assert unsafe["metadata"]["rejection_reason"] == "UNSAFE_ACTION_PROHIBITED"

    safe = candidates[1]
    assert safe["metadata"]["label"] == "HYPOTHESIS"
    assert safe["metadata"]["evidence_status"] == "UNVERIFIED"
    assert safe["metadata"]["retained"] is True
    assert safe["metadata"]["rejection_reason"] == ""

    metrics = res["metrics"]
    assert metrics["total_candidates"] == 2
    assert metrics["accepted_candidates"] == 1
    assert metrics["rejected_candidates"] == 1
    assert metrics["acceptance_rate"] == 0.5
    engine.close()


def test_quantitative_novelty_and_diversity_metrics(tmp_path: Path) -> None:
    engine = _engine(tmp_path, _SeededProvider())
    res1 = engine.explore(ExplorationRequest("novelty check", authorized=True, seed=10, request_id="r1"))
    assert res1["metrics"]["novelty_score"] == 1.0
    assert res1["metrics"]["diversity_score"] > 0.0

    # Repeat same candidate in next request
    res2 = engine.explore(ExplorationRequest("novelty check", authorized=True, seed=10, request_id="r2"))
    assert res2["metrics"]["novelty_score"] == 0.0
    assert res2["metrics"]["accepted_candidates"] == 0
    assert res2["candidates"][0]["metadata"]["rejection_reason"] == "DUPLICATE_CANDIDATE"
    engine.close()


def test_evidence_ids_validation_in_request() -> None:
    req = ExplorationRequest("topic", authorized=True, evidence_ids=("ev-1", "ev-2"))
    assert req.evidence_ids == ("ev-1", "ev-2")

    with pytest.raises(ValueError, match="evidence_id"):
        ExplorationRequest("topic", authorized=True, evidence_ids=("",))

    with pytest.raises(ValueError, match="evidence_id"):
        ExplorationRequest("topic", authorized=True, evidence_ids=("x" * 300,))
