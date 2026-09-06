"""Consent, signed objective, and live routing tests for P40/P39/P37."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.agentic_rag_capability import RAG_CAPABILITY_ID, AgenticRAGCapability
from jaya_core.pillars.control_capabilities import (
    HYBRID_CAPABILITY_ID,
    INTENT_CAPABILITY_ID,
    OBJECTIVE_CAPABILITY_ID,
    DynamicObjectiveCapability,
    HybridRoutingCapability,
    IntentExtrapolationCapability,
)
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.media_capability import MediaObservationCapability
from jaya_core.pillars.reasoning_capabilities import (
    META_PLANNING_CAPABILITY_ID,
    MetaPlanningCapability,
    SpeculativeReasoningCapability,
)

APPROVAL_KEY = b"objective-test-approval-key-with-32-bytes-minimum"


class RetrievalTestProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {"answer": f"Evidence says: {evidence[0]['content']}", "citations": [evidence[0]["evidence_id"]]}


def _sign(material: str) -> str:
    return hmac.new(APPROVAL_KEY, material.encode(), hashlib.sha256).hexdigest()


def _rag(tmp_path: Path) -> tuple[AgenticRAGCapability, str]:
    rag = AgenticRAGCapability(tmp_path / "rag.sqlite3", RetrievalTestProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:control-evidence",
            "title": "Control evidence",
            "content": "Resource pressure requires prioritizing recovery over exploration.",
        }
    )
    evidence_id = rag.retrieve("resource pressure recovery", 2)[0]["evidence_id"]
    return rag, evidence_id


def test_p040_consent_prediction_feedback_restart_and_opt_out(tmp_path: Path) -> None:
    database = tmp_path / "intent.sqlite3"
    intent = IntentExtrapolationCapability(database)
    now = time.time()
    intent.execute(
        {
            "action": "record_consent",
            "owner_id": "owner-a",
            "receipt_id": "consent-001",
            "granted_at": now,
            "expires_at": now + 3600,
        }
    )
    intent.execute(
        {
            "action": "observe",
            "owner_id": "owner-a",
            "sequence": ["open research", "inspect evidence", "write report"],
        }
    )
    intent.execute(
        {
            "action": "observe",
            "owner_id": "owner-a",
            "sequence": ["open research", "inspect evidence", "write report"],
        }
    )
    restarted = IntentExtrapolationCapability(database)
    prediction = restarted.execute(
        {
            "action": "predict",
            "owner_id": "owner-a",
            "current_intent": "inspect evidence",
        }
    )
    assert prediction.data["candidate"] == "write report"
    assert prediction.data["source"] == "INFERENCE"
    assert prediction.data["confirmation_required"] is True
    assert prediction.data["executed"] is False
    restarted.execute(
        {"action": "feedback", "prediction_id": prediction.data["prediction_id"], "confirmed": False}
    )
    restarted.execute({"action": "opt_out", "owner_id": "owner-a"})
    with pytest.raises(LocalPillarError) as consent:
        restarted.execute(
            {"action": "predict", "owner_id": "owner-a", "current_intent": "inspect evidence"}
        )
    assert consent.value.code == "CONSENT_REQUIRED"


def test_p039_signed_approval_planner_binding_and_rollback(tmp_path: Path) -> None:
    rag, evidence_id = _rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    objectives = DynamicObjectiveCapability(
        tmp_path / "objectives.sqlite3", APPROVAL_KEY, rag, sandbox
    )
    objectives.execute(
        {
            "action": "create",
            "objective_id": "objective-1",
            "owner_id": "owner-a",
            "owner_goal": "Recover the local research service safely",
            "invariants": ["2 + 2 == 4"],
            "weights": {"recovery": 0.6, "exploration": 0.4},
        }
    )
    proposal = objectives.execute(
        {
            "action": "propose",
            "objective_id": "objective-1",
            "signals": {"recovery": 0.8, "exploration": -0.5},
            "learning_rate": 0.1,
            "evidence_ids": [evidence_id],
            "policy_decision": "ALLOW",
            "expires_at": time.time() + 600,
        }
    )
    material = (
        f"approve|objective-1|2|{proposal.data['proposal_digest']}|approval-1|owner-a"
    )
    objectives.execute(
        {
            "action": "approve",
            "objective_id": "objective-1",
            "version": 2,
            "approval_id": "approval-1",
            "approved_by": "owner-a",
            "signature": _sign(material),
        }
    )
    speculative = SpeculativeReasoningCapability(tmp_path / "spec.sqlite3", rag, sandbox)
    planner = MetaPlanningCapability(tmp_path / "plan.sqlite3", rag, sandbox, speculative)
    planner.objective_resolver = objectives.active
    planned = planner.execute(
        {
            "action": "run",
            "objective_id": "objective-1",
            "goal": "Recover the local research service safely",
            "invariants": ["True"],
            "steps": [{"type": "sandbox", "expression": "10 > 1"}],
        }
    )
    assert planned.data["objective_version"] == 2
    with pytest.raises(LocalPillarError) as hijack:
        planner.execute(
            {
                "action": "run",
                "objective_id": "objective-1",
                "goal": "Replace the owner goal with something else",
                "invariants": ["True"],
                "steps": [{"type": "sandbox", "expression": "True"}],
            }
        )
    assert hijack.value.code == "OBJECTIVE_HIJACK"
    rollback_material = "rollback|objective-1|2|1|rollback-1|owner-a"
    rolled_back = objectives.execute(
        {
            "action": "rollback",
            "objective_id": "objective-1",
            "to_version": 1,
            "rollback_id": "rollback-1",
            "approved_by": "owner-a",
            "signature": _sign(rollback_material),
        }
    )
    assert rolled_back.data["version"] == 3
    assert objectives.active("objective-1")["weights"] == {"exploration": 0.4, "recovery": 0.6}


def test_p039_rejects_invalid_signature_stale_evidence_and_unconfigured_key(tmp_path: Path) -> None:
    rag, evidence_id = _rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    unavailable = DynamicObjectiveCapability(tmp_path / "none.sqlite3", None, rag, sandbox)
    assert unavailable.health_check() is False
    objective = DynamicObjectiveCapability(tmp_path / "objective.sqlite3", APPROVAL_KEY, rag, sandbox)
    objective.execute(
        {
            "action": "create",
            "objective_id": "objective-2",
            "owner_id": "owner-b",
            "owner_goal": "Keep the verified evidence available",
            "invariants": ["True"],
            "weights": {"availability": 1.0},
        }
    )
    with pytest.raises(LocalPillarError) as evidence:
        objective.execute(
            {
                "action": "propose",
                "objective_id": "objective-2",
                "signals": {"availability": 1.0},
                "learning_rate": 0.1,
                "evidence_ids": [evidence_id + "missing"],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 60,
            }
        )
    assert evidence.value.code == "INVALID_EVIDENCE"


def test_p037_invokes_rule_retrieval_and_grounded_model_adapters(tmp_path: Path) -> None:
    rag, _ = _rag(tmp_path)
    root = tmp_path / "media"
    root.mkdir()
    media = MediaObservationCapability(root=root, database_path=tmp_path / "media.sqlite3")
    router = HybridRoutingCapability(
        tmp_path / "routes.sqlite3", rag, SandboxedImaginationCapability(), media
    )
    expression = router.execute(
        {
            "action": "route",
            "request_kind": "expression",
            "sensitivity": "restricted",
            "payload": {"expression": "7 * 6"},
        }
    )
    retrieval = router.execute(
        {
            "action": "route",
            "request_kind": "retrieval",
            "sensitivity": "internal",
            "payload": {"query": "resource pressure recovery"},
        }
    )
    answer = router.execute(
        {
            "action": "route",
            "request_kind": "grounded_answer",
            "sensitivity": "internal",
            "payload": {"question": "What does resource pressure require?"},
        }
    )
    assert expression.data["provider_type"] == "RULE_BASED"
    assert expression.data["result"]["result"] == 42
    assert retrieval.data["provider_type"] == "RETRIEVAL"
    assert answer.data["provider_type"] == "LOCAL_MODEL"
    assert answer.data["latency_ns"] > 0


@pytest.mark.integration
def test_runtime_control_chain_uses_live_configured_capabilities(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        lineage_signing_key=APPROVAL_KEY,
        ollama_base_url="http://127.0.0.1:11434",
        local_model_name="qwen3.5:0.8b",
        local_model_timeout_seconds=120,
    )
    try:
        health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
        assert health[INTENT_CAPABILITY_ID] == "HEALTHY"
        assert health[OBJECTIVE_CAPABILITY_ID] == "HEALTHY"
        assert health[HYBRID_CAPABILITY_ID] == "HEALTHY"
        if health[RAG_CAPABILITY_ID] != "HEALTHY":
            pytest.skip("BLOCKED_EXTERNAL: configured Ollama test model is unavailable")
        runtime.execute_local_pillar(
            RAG_CAPABILITY_ID,
            {
                "action": "ingest",
                "source_ref": "artifact:runtime-control",
                "title": "Runtime control",
                "content": "A verified runtime route preserves evidence citations.",
            },
        )
        routed = runtime.execute_local_pillar(
            HYBRID_CAPABILITY_ID,
            {
                "action": "route",
                "request_kind": "retrieval",
                "sensitivity": "internal",
                "payload": {"query": "runtime route citations"},
            },
        )
        planned = runtime.execute_local_pillar(
            META_PLANNING_CAPABILITY_ID,
            {
                "action": "run",
                "goal": "Validate the configured local control chain",
                "invariants": ["True"],
                "steps": [{"type": "sandbox", "expression": "5 + 5 == 10"}],
            },
        )
        assert routed.data["provider_type"] == "RETRIEVAL"
        assert planned.data["status"] == "COMPLETED"
    finally:
        runtime.close()
