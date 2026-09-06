"""Real local generation, verification, and plan execution tests for P3/P36/P38."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.agentic_rag_capability import RAG_CAPABILITY_ID, AgenticRAGCapability
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.reasoning_capabilities import (
    DREAM_CAPABILITY_ID,
    META_PLANNING_CAPABILITY_ID,
    SPECULATIVE_CAPABILITY_ID,
    ActiveDreamingCapability,
    DeterministicCounterfactualProvider,
    MetaPlanningCapability,
    SpeculativeReasoningCapability,
)


class RetrievalTestProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {"answer": question, "citations": [evidence[0]["evidence_id"]]}


class HypothesisTestProvider:
    provider_type = "TEST_IMPLEMENTATION"
    provider_name = "bounded-test-generator"

    def health_check(self) -> bool:
        return True

    def generate(
        self,
        topic: str,
        evidence: Sequence[Mapping[str, Any]],
        candidate_limit: int,
        seed: int,
    ) -> Sequence[Mapping[str, Any]]:
        return [
            {
                "statement": f"If the timing policy changes, {topic} may rank differently.",
                "evidence_id": evidence[0]["evidence_id"],
                "falsification_test": "Compare ranking on a held-out timestamp sequence.",
            }
        ]


def _rag(tmp_path: Path) -> AgenticRAGCapability:
    rag = AgenticRAGCapability(tmp_path / "rag.sqlite3", RetrievalTestProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:reasoning-source",
            "title": "Temporal evidence",
            "content": "Temporal weighting changes memory ranking using observed timestamps.",
        }
    )
    return rag


def test_p003_persists_reproducible_unverified_hypothesis_artifact(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    database = tmp_path / "dream.sqlite3"
    dream = ActiveDreamingCapability(database, rag, sandbox, HypothesisTestProvider())
    created = dream.execute(
        {
            "action": "dream",
            "topic": "memory ranking",
            "query": "temporal weighting timestamps",
            "constraints": ["2 + 2 == 4"],
            "candidate_limit": 2,
            "seed": 17,
        }
    )
    restarted = ActiveDreamingCapability(database, rag, sandbox, HypothesisTestProvider())
    replay = restarted.execute({"action": "get", "dream_id": created.data["dream_id"]})

    assert replay.data["seed"] == 17
    assert replay.data["candidates"][0]["label"] == "HYPOTHESIS"
    assert replay.data["candidates"][0]["verification"] == "UNVERIFIED"
    assert replay.data["warning"] == "MODEL_OUTPUT_IS_NOT_EMPIRICAL_EVIDENCE"


def test_p003_rejects_failed_constraint_and_missing_evidence(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    dream = ActiveDreamingCapability(
        tmp_path / "dream.sqlite3",
        rag,
        SandboxedImaginationCapability(),
        HypothesisTestProvider(),
    )
    with pytest.raises(LocalPillarError) as rejected:
        dream.execute(
            {"action": "dream", "topic": "ranking", "constraints": ["2 + 2 == 5"]}
        )
    assert rejected.value.code == "CONSTRAINT_REJECTED"
    with pytest.raises(LocalPillarError) as missing:
        dream.execute(
            {
                "action": "dream",
                "topic": "unseen topic",
                "query": "zebra banana quantum",
                "constraints": ["True"],
            }
        )
    assert missing.value.code == "EVIDENCE_UNAVAILABLE"


def test_p003_rejects_unsafe_goal_and_destructive_commands(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    dream = ActiveDreamingCapability(
        tmp_path / "dream.sqlite3",
        rag,
        SandboxedImaginationCapability(),
        HypothesisTestProvider(),
    )
    with pytest.raises(LocalPillarError) as exc:
        dream.execute(
            {
                "action": "dream",
                "topic": "system purge rm -rf /etc/shadow",
                "constraints": ["True"],
            }
        )
    assert exc.value.code == "UNSAFE_GOAL_PROHIBITED"


def test_p003_deterministic_replay_by_request_id(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    dream = ActiveDreamingCapability(
        tmp_path / "dream.sqlite3",
        rag,
        SandboxedImaginationCapability(),
        DeterministicCounterfactualProvider(),
    )
    req = {
        "action": "dream",
        "topic": "temporal weighting",
        "query": "temporal weighting timestamps",
        "constraints": ["5 > 2"],
        "candidate_limit": 2,
        "seed": 42,
        "request_id": "req-replay-test-42",
    }
    first = dream.execute(req)
    assert first.code == "HYPOTHESIS_ARTIFACT_CREATED"
    dream_id = first.data["dream_id"]

    second = dream.execute(req)
    assert second.code == "REPLAYED_DREAM"
    assert second.data["dream_id"] == dream_id
    assert second.data["seed"] == 42


def test_p003_quantitative_novelty_and_diversity_metrics(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    dream = ActiveDreamingCapability(
        tmp_path / "dream.sqlite3",
        rag,
        SandboxedImaginationCapability(),
        DeterministicCounterfactualProvider(),
    )
    res1 = dream.execute(
        {
            "action": "dream",
            "topic": "temporal weighting",
            "query": "temporal weighting timestamps",
            "constraints": ["True"],
            "candidate_limit": 2,
            "seed": 100,
            "request_id": "r1",
        }
    )
    assert res1.data["metrics"]["novelty_score"] == 1.0
    assert res1.data["metrics"]["diversity_score"] > 0.0

    # Repeat same seed in new request_id
    res2 = dream.execute(
        {
            "action": "dream",
            "topic": "temporal weighting",
            "query": "temporal weighting timestamps",
            "constraints": ["True"],
            "candidate_limit": 2,
            "seed": 100,
            "request_id": "r2",
        }
    )
    assert res2.data["metrics"]["novelty_score"] == 0.0
    assert res2.data["metrics"]["accepted_candidates"] == 0
    assert res2.data["candidates"][0]["rejection_reason"] == "DUPLICATE_CANDIDATE"


def test_p003_tamper_detection_raises_storage_corrupt(tmp_path: Path) -> None:
    import sqlite3
    rag = _rag(tmp_path)
    db_path = tmp_path / "dream_tamper.sqlite3"
    dream = ActiveDreamingCapability(
        db_path,
        rag,
        SandboxedImaginationCapability(),
        DeterministicCounterfactualProvider(),
    )
    created = dream.execute(
        {
            "action": "dream",
            "topic": "temporal weighting",
            "query": "temporal weighting timestamps",
            "constraints": ["True"],
            "request_id": "tamper-id-1",
        }
    )
    dream_id = created.data["dream_id"]
    dream.close()

    # Tamper with the row
    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("UPDATE dream_artifacts SET seed = 99999 WHERE dream_id = ?", (dream_id,))
    conn.close()

    restarted = ActiveDreamingCapability(
        db_path,
        rag,
        SandboxedImaginationCapability(),
        DeterministicCounterfactualProvider(),
    )
    with pytest.raises(LocalPillarError) as exc:
        restarted.execute({"action": "get", "dream_id": dream_id})
    assert exc.value.code == "STORAGE_CORRUPT"
    restarted.close()


def test_p036_runs_independent_citation_and_sandbox_verifiers(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    evidence = rag.retrieve("temporal timestamps", 2)[0]
    capability = SpeculativeReasoningCapability(
        tmp_path / "speculative.sqlite3", rag, SandboxedImaginationCapability()
    )
    result = capability.execute(
        {
            "action": "evaluate",
            "candidates": [
                {
                    "candidate_id": "candidate-pass",
                    "evidence_id": evidence["evidence_id"],
                    "verification_expression": "10 > 2",
                    "retrieval_score": 0.8,
                },
                {
                    "candidate_id": "candidate-fail",
                    "evidence_id": evidence["evidence_id"],
                    "verification_expression": "10 < 2",
                    "retrieval_score": 0.9,
                },
            ],
        }
    )
    assert result.data["selected"]["candidate_id"] == "candidate-pass"
    assert result.data["rejected"][0]["checks"]["sandbox_constraint"] is False
    capability.close()
    rag.close()


def test_p036_safety_and_citation_failure_handling(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    evidence = rag.retrieve("temporal timestamps", 2)[0]
    capability = SpeculativeReasoningCapability(
        tmp_path / "speculative_safety.sqlite3", rag, SandboxedImaginationCapability()
    )
    # Candidate 1: Violates safety policy
    # Candidate 2: Cites non-existent evidence
    result = capability.execute(
        {
            "action": "evaluate",
            "candidates": [
                {
                    "candidate_id": "cand-unsafe",
                    "statement": "rm -rf / --no-preserve-root",
                    "evidence_id": evidence["evidence_id"],
                    "verification_expression": "True",
                },
                {
                    "candidate_id": "cand-missing-cite",
                    "statement": "Valid statement with hallucinated citation",
                    "evidence_id": "hallucinated_ghost_evidence_id_999",
                    "verification_expression": "True",
                },
            ],
        }
    )
    assert result.code == "NO_CANDIDATE_VERIFIED"
    assert result.data["selected"] is None
    assert len(result.data["rejected"]) == 2
    assert result.data["rejected"][0]["failure_code"] == "UNSAFE_GOAL_PROHIBITED"
    assert result.data["rejected"][0]["checks"]["safety_policy"] is False
    assert result.data["rejected"][1]["failure_code"] == "CITATION_UNAVAILABLE"
    assert result.data["rejected"][1]["checks"]["citation_exists"] is False
    capability.close()
    rag.close()


def test_p036_evaluator_disagreement_and_non_self_score_ranking(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    evidence = rag.retrieve("temporal timestamps", 2)[0]
    capability = SpeculativeReasoningCapability(
        tmp_path / "speculative_ranking.sqlite3", rag, SandboxedImaginationCapability()
    )
    # High unverified self-score (0.99) but fails sandbox constraint
    # Moderate score (0.80) and passes all verifiers
    result = capability.execute(
        {
            "action": "evaluate",
            "candidates": [
                {
                    "candidate_id": "cand-high-unverified",
                    "statement": "Candidate with high self score but false math",
                    "evidence_id": evidence["evidence_id"],
                    "verification_expression": "100 < 5",
                    "retrieval_score": 0.99,
                },
                {
                    "candidate_id": "cand-verified",
                    "statement": "Candidate passing all checks",
                    "evidence_id": evidence["evidence_id"],
                    "verification_expression": "100 > 5",
                    "retrieval_score": 0.80,
                },
            ],
        }
    )
    assert result.code == "VERIFIED_CANDIDATE_SELECTED"
    assert result.data["selected"]["candidate_id"] == "cand-verified"
    assert result.data["metrics"]["evaluator_disagreements"] == 1
    assert result.data["rejected"][0]["candidate_id"] == "cand-high-unverified"
    assert result.data["rejected"][0]["evaluator_disagreement"] is True
    capability.close()
    rag.close()


def test_p036_deterministic_replay_and_rejection_persistence(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    evidence = rag.retrieve("temporal timestamps", 2)[0]
    capability = SpeculativeReasoningCapability(
        tmp_path / "speculative_replay.sqlite3", rag, SandboxedImaginationCapability()
    )
    req_id = "replay-spec-req-42"
    payload = {
        "action": "evaluate",
        "request_id": req_id,
        "candidates": [
            {
                "candidate_id": "cand-1",
                "statement": "First candidate",
                "evidence_id": evidence["evidence_id"],
                "verification_expression": "1 + 1 == 2",
                "retrieval_score": 0.85,
            },
            {
                "candidate_id": "cand-fail",
                "statement": "Failed candidate",
                "evidence_id": "nonexistent_ref",
                "verification_expression": "True",
            },
        ],
    }
    run1 = capability.execute(payload)
    run2 = capability.execute(payload)
    replayed = capability.replay({"action": "replay", "request_id": req_id})

    assert run1.code == "VERIFIED_CANDIDATE_SELECTED"
    assert run2.code == "REPLAYED_SPECULATION"
    assert replayed.code == "REPLAYED_SPECULATION"
    assert run1.data["run_id"] == run2.data["run_id"] == replayed.data["run_id"]
    assert run1.data["receipt_sha256"] == run2.data["receipt_sha256"]

    # Check rejection archive persistence
    rejections = capability.rejections_by_run_id(run1.data["run_id"])
    assert len(rejections) == 1
    assert rejections[0]["candidate_id"] == "cand-fail"
    assert rejections[0]["failure_code"] == "CITATION_UNAVAILABLE"
    capability.close()
    rag.close()


def test_p036_tamper_detection_and_validation_errors(tmp_path: Path) -> None:
    import sqlite3
    rag = _rag(tmp_path)
    evidence = rag.retrieve("temporal timestamps", 2)[0]
    db_path = tmp_path / "speculative_tamper.sqlite3"
    capability = SpeculativeReasoningCapability(
        db_path, rag, SandboxedImaginationCapability()
    )

    # Validation errors
    with pytest.raises(LocalPillarError) as exc_unknown:
        capability.execute({
            "action": "evaluate",
            "candidates": [{"candidate_id": "c1", "evidence_id": evidence["evidence_id"], "verification_expression": "True"}],
            "unknown_extra": "illegal",
        })
    assert exc_unknown.value.code == "UNKNOWN_FIELD"

    with pytest.raises(LocalPillarError) as exc_missing:
        capability.execute({"action": "evaluate"})
    assert exc_missing.value.code == "MISSING_FIELD"

    with pytest.raises(LocalPillarError) as exc_limit:
        capability.execute({"action": "evaluate", "candidates": []})
    assert exc_limit.value.code == "RESOURCE_LIMIT"

    # Create a valid run then tamper it
    created = capability.execute({
        "action": "evaluate",
        "candidates": [{
            "candidate_id": "c1",
            "evidence_id": evidence["evidence_id"],
            "verification_expression": "True",
            "retrieval_score": 0.8,
        }],
    })
    run_id = created.data["run_id"]
    capability.close()

    conn = sqlite3.connect(db_path)
    with conn:
        conn.execute("UPDATE speculative_runs SET status = 'TAMPERED_STATUS' WHERE run_id = ?", (run_id,))
    conn.close()

    restarted = SpeculativeReasoningCapability(
        db_path, rag, SandboxedImaginationCapability()
    )
    with pytest.raises(LocalPillarError) as exc_tamper:
        restarted.by_run_id(run_id)
    assert exc_tamper.value.code == "STORAGE_CORRUPT"

    restarted.close()
    rag.close()


def test_p038_executes_multistep_plan_and_real_fallback(tmp_path: Path) -> None:
    rag = _rag(tmp_path)
    sandbox = SandboxedImaginationCapability()
    speculative = SpeculativeReasoningCapability(tmp_path / "spec.sqlite3", rag, sandbox)
    planner = MetaPlanningCapability(tmp_path / "plans.sqlite3", rag, sandbox, speculative)
    result = planner.execute(
        {
            "action": "run",
            "goal": "Retrieve temporal evidence and validate a bounded calculation",
            "invariants": ["1 + 1 == 2"],
            "steps": [
                {"type": "retrieve", "query": "temporal timestamps", "minimum_results": 1},
                {"type": "sandbox", "expression": "6 * 7 == 42"},
                {
                    "type": "retrieve",
                    "query": "missing zebra banana",
                    "minimum_results": 1,
                    "fallback": {"type": "sandbox", "expression": "3 ** 2 == 9"},
                },
            ],
            "maximum_steps": 4,
        }
    )
    assert result.data["status"] == "COMPLETED"
    assert result.data["recoveries"] == 1
    assert result.data["observations"][2]["status"] == "RECOVERED"


@pytest.mark.integration
def test_runtime_live_model_dream_to_verifier_to_meta_plan(tmp_path: Path) -> None:
    runtime = JayaCoreRuntime(
        db_path=tmp_path / "core.sqlite3",
        local_pillar_data_dir=tmp_path / "pillars",
        ollama_base_url="http://127.0.0.1:11434",
        local_model_name="qwen3.5:0.8b",
        local_model_timeout_seconds=120,
    )
    health = runtime.operational_snapshot()["local_pillar_capabilities"]["capabilities"]
    if health[DREAM_CAPABILITY_ID] != "HEALTHY":
        runtime.close()
        pytest.skip("BLOCKED_EXTERNAL: configured Ollama test model is unavailable")
    try:
        runtime.execute_local_pillar(
            RAG_CAPABILITY_ID,
            {
                "action": "ingest",
                "source_ref": "artifact:live-dream",
                "title": "Live hypothesis evidence",
                "content": "A lower decay rate retains older memory evidence for longer.",
            },
        )
        dream = runtime.execute_local_pillar(
            DREAM_CAPABILITY_ID,
            {
                "action": "dream",
                "topic": "temporal memory decay",
                "query": "lower decay rate older memory",
                "constraints": ["0.05 < 0.1"],
                "candidate_limit": 1,
                "seed": 23,
            },
        )
        verified = runtime.execute_local_pillar(
            SPECULATIVE_CAPABILITY_ID,
            {"action": "evaluate", "candidates": dream.data["candidates"]},
        )
        plan = runtime.execute_local_pillar(
            META_PLANNING_CAPABILITY_ID,
            {
                "action": "run",
                "goal": "Verify retrieved temporal memory evidence",
                "invariants": ["True"],
                "steps": [
                    {
                        "type": "speculate",
                        "candidates": dream.data["candidates"],
                    }
                ],
            },
        )
        assert dream.data["provider_type"] == "LOCAL_MODEL"
        assert verified.data["selected"] is not None
        assert plan.data["status"] == "COMPLETED"
    finally:
        runtime.close()
