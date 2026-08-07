"""
test_cognitive_kernel.py — Unit and Integration tests for JAYA Core Portable Cognitive Kernel.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(repo_root))
sys.path.insert(0, str(repo_root / "JAYA_CORE"))

from src.artifacts.candidate_gate import CandidateArtifact, CandidateStatus, CognitiveArtifactGate
from src.capabilities.manifest import CapabilityManifest
from src.capabilities.negotiation import CapabilityNegotiator, NegotiationResultStatus
from src.capabilities.registry import CapabilityRegistry
from src.cognitive.contracts import (
    ActionResult,
    ActionStatus,
    ActionStep,
    Goal,
    IntentType,
    ResourceBudget,
    RiskClass,
    UserRequest,
)
from src.cognitive.intent import IntentEngine
from src.cognitive.planner import GenericHierarchicalPlanner
from src.cognitive.runtime import JayaCoreRuntime
from src.identity.models import AuthorityLevel, JayaIdentity, NodeClass, NodeIdentity, NodeRole
from src.identity.verifier import IdentityVerificationError, LocalIdentityVerifier
from src.memory.episodic import EpisodicMemoryStore
from src.memory.events import MemoryEvent
from src.memory.working import WorkingMemory
from src.models.protocol import ModelRequest
from src.models.router import ModelRouter
from src.models.rule_based import RuleBasedCognitiveModel
from src.resources.budget import ResourceBudgetCalculator
from src.resources.modes import ExecutionMode, ExecutionModeController, InvalidModeTransitionError
from src.resources.profiler import ResourceProfile, ResourceProfiler
from src.sync.event_log import AppendOnlyEventLog, NodeEvent


# ============================================================================
# 1. Contracts Tests
# ============================================================================

class TestCognitiveContracts:
    def test_user_request_serialization(self):
        req = UserRequest(request_id="req-100", raw_prompt="Test prompt", user_id="user_a")
        d = req.to_dict()
        assert d["request_id"] == "req-100"
        assert d["schema_version"] == "1.0"

        deserialized = UserRequest.from_dict(d)
        assert deserialized.raw_prompt == "Test prompt"
        assert deserialized.user_id == "user_a"

    def test_action_step_risk_class_serialization(self):
        step = ActionStep(
            step_id="s1",
            title="Export model",
            action_type="export",
            required_capability="cad.export",
            risk_class=RiskClass.DESTRUCTIVE,
            approval_required=True,
        )
        d = step.to_dict()
        assert d["risk_class"] == "DESTRUCTIVE"
        assert d["approval_required"] is True


# ============================================================================
# 2. Identity Tests
# ============================================================================

class TestIdentity:
    def test_local_verifier_registers_and_verifies_node(self):
        master = JayaIdentity("jaya-master", "owner_a")
        verifier = LocalIdentityVerifier(master)
        node = NodeIdentity(
            node_id="node-01",
            jaya_identity_id="jaya-master",
            node_class=NodeClass.STANDARD,
            role=NodeRole.PERSONAL_WORKSTATION_NODE,
            authority=AuthorityLevel.STANDARD_WORKER,
        )
        verifier.register_node(node)
        verified = verifier.verify_node("node-01")
        assert verified.node_id == "node-01"
        assert verifier.has_required_authority("node-01", AuthorityLevel.EDGE_OBSERVER) is True
        assert verifier.has_required_authority("node-01", AuthorityLevel.CENTRAL_AUTHORITY) is False

    def test_local_verifier_rejects_mismatched_identity(self):
        master = JayaIdentity("jaya-master", "owner_a")
        verifier = LocalIdentityVerifier(master)
        fake_node = NodeIdentity(
            node_id="node-fake",
            jaya_identity_id="jaya-imposter",
            node_class=NodeClass.EDGE,
            role=NodeRole.PERSONAL_MOBILE_NODE,
            authority=AuthorityLevel.EDGE_OBSERVER,
        )
        with pytest.raises(IdentityVerificationError):
            verifier.register_node(fake_node)


# ============================================================================
# 3. Resource & Mode Tests
# ============================================================================

class TestResourceAndMode:
    def test_resource_classification(self):
        profiler = ResourceProfiler()
        assert profiler._classify(20000, 10000) == NodeClass.CENTRAL
        assert profiler._classify(8000, 4000) == NodeClass.STANDARD
        assert profiler._classify(2000, 1000) == NodeClass.EDGE
        assert profiler._classify(500, 200) == NodeClass.CONSTRAINED

    def test_invalid_mode_transition(self):
        ctrl = ExecutionModeController(ExecutionMode.EMERGENCY)
        with pytest.raises(InvalidModeTransitionError):
            ctrl.transition_to(ExecutionMode.ONLINE_FULL)

    def test_auto_determine_mode_offline_and_low_memory(self):
        ctrl = ExecutionModeController()
        profiler = ResourceProfiler()
        profile_offline = profiler.profile(
            override_total_mem_mb=1024,
            override_available_mem_mb=400,
            network_available=False,
        )
        mode = ctrl.auto_determine_mode(profile_offline)
        assert mode in (ExecutionMode.OFFLINE_AUTONOMOUS, ExecutionMode.OFFLINE_SAFE)


# ============================================================================
# 4. Capability Registry & Negotiation Tests
# ============================================================================

class TestCapabilities:
    def test_registry_register_lookup_filter(self):
        reg = CapabilityRegistry()
        cap = CapabilityManifest(
            capability_id="cad.parametric_modeling",
            version="1.0",
            provider="mcp",
            execution_location="local",
            min_memory_mb=512,
            offline_available=True,
        )
        reg.register(cap)
        assert reg.lookup("cad.parametric_modeling") == cap

        # Filter insufficient memory
        available = reg.filter_available(memory_available_mb=256)
        assert len(available) == 0

        # Filter sufficient memory
        available = reg.filter_available(memory_available_mb=1024)
        assert len(available) == 1

    def test_negotiation_local_vs_offload_vs_unavailable(self):
        reg = CapabilityRegistry()
        reg.register(
            CapabilityManifest(
                capability_id="core.reason",
                version="1.0",
                provider="built_in",
                execution_location="local",
                min_memory_mb=16,
                offline_available=True,
            )
        )
        negotiator = CapabilityNegotiator(reg)
        budget = ResourceBudget(max_memory_mb=512, allow_network=True, allow_remote_offload=True)

        # Local match
        neg_local = negotiator.negotiate("core.reason", ExecutionMode.ONLINE_FULL, budget)
        assert neg_local.status == NegotiationResultStatus.EXECUTE_LOCAL

        # Remote match
        known_remote = {"central-server": ["cad.parametric_modeling"]}
        neg_remote = negotiator.negotiate(
            "cad.parametric_modeling",
            ExecutionMode.ONLINE_FULL,
            budget,
            known_remote_capabilities=known_remote,
        )
        assert neg_remote.status == NegotiationResultStatus.OFFLOAD_TO_NODE
        assert neg_remote.target_node == "central-server"

        # Completely unavailable offline
        neg_unavail = negotiator.negotiate("unknown.cap", ExecutionMode.OFFLINE_SAFE, budget)
        assert neg_unavail.status == NegotiationResultStatus.CAPABILITY_UNAVAILABLE


# ============================================================================
# 5. Memory Tests
# ============================================================================

class TestMemory:
    def test_working_memory_eviction_and_ttl(self):
        wm = WorkingMemory(session_id="s1", max_items=2)
        wm.set("k1", "v1")
        wm.set("k2", "v2")
        assert wm.get("k1") == "v1"
        wm.set("k3", "v3")  # Exceeds max_items -> evicts k1
        assert wm.get("k1") is None
        assert wm.get("k3") == "v3"

    def test_episodic_memory_sqlite_idempotency_and_persistence(self, tmp_path):
        db_file = tmp_path / "test_episodic.db"
        mem = EpisodicMemoryStore(db_path=db_file)
        ev1 = MemoryEvent(
            event_id="evt-001",
            event_type="TEST_TYPE",
            session_id="sess_1",
            goal_id="goal_1",
            payload={"key": "val"},
        )
        assert mem.append_event(ev1) is True
        assert mem.append_event(ev1) is False  # Duplicate ignored

        events = mem.query_by_session("sess_1")
        assert len(events) == 1
        assert events[0].payload["key"] == "val"
        mem.close()

        # Reopen db -> persistence check
        mem2 = EpisodicMemoryStore(db_path=db_file)
        events2 = mem2.query_by_session("sess_1")
        assert len(events2) == 1
        mem2.close()


# ============================================================================
# 6. Planner Tests
# ============================================================================

class TestPlanner:
    def test_generic_3d_design_plan(self):
        planner = GenericHierarchicalPlanner()
        goal = Goal(
            goal_id="g-3d-01",
            title="Buat desain casing PC",
            intent_type=IntentType.CREATE_3D_DESIGN,
            domain="cad.parametric_modeling",
        )
        plan = planner.create_plan(goal)
        assert len(plan.steps) >= 4
        action_types = [s.action_type for s in plan.steps]
        assert "generate_parametric_geometry" in action_types
        assert any(s.approval_required for s in plan.steps)

    def test_no_thesis_defaults_in_generic_planner(self):
        planner = GenericHierarchicalPlanner()
        goal = Goal(
            goal_id="g-gen-01",
            title="Analisis performa server",
            intent_type=IntentType.CREATE_PLAN,
            domain="planning",
        )
        plan = planner.create_plan(goal)
        titles = " ".join([s.title.lower() for s in plan.steps])
        assert "skripsi" not in titles
        assert "bab" not in titles


# ============================================================================
# 7. Cognitive Runtime & End-to-End Tests
# ============================================================================

class TestJayaCoreRuntime:
    def test_runtime_init_and_readiness(self):
        runtime = JayaCoreRuntime(db_path=":memory:")
        assert runtime.is_ready() is True

    def test_runtime_process_request(self):
        runtime = JayaCoreRuntime(db_path=":memory:")
        req = UserRequest(
            request_id="req-test-01",
            raw_prompt="Buat rencana untuk merapikan file proyek saya.",
            user_id="user_test",
        )
        resp = runtime.process(req)
        assert resp.status == "SUCCESS"
        assert resp.intent_type == "CREATE_PLAN"
        assert resp.jayair_request is not None
        assert len(resp.jayair_request["steps"]) >= 1

    def test_runtime_process_3d_design_missing_capability(self):
        runtime = JayaCoreRuntime(db_path=":memory:")
        req = UserRequest(
            request_id="req-test-3d",
            raw_prompt="Buat desain casing mini PC.",
            user_id="user_test",
        )
        resp = runtime.process(req)
        # cad.parametric_modeling is missing locally
        assert resp.status in ("CAPABILITY_UNAVAILABLE", "OFFLOAD_REQUIRED")

    def test_runtime_chat_compatibility(self):
        runtime = JayaCoreRuntime(db_path=":memory:")
        ans = runtime.chat("Bantu saya merapikan file")
        assert isinstance(ans, str)
        assert len(ans) > 0

    def test_process_action_result(self):
        runtime = JayaCoreRuntime(db_path=":memory:")
        result = ActionResult(
            request_id="req-test-01",
            step_id="step-1",
            status=ActionStatus.SUCCESS,
            output={"files_scanned": 15},
        )
        resp = runtime.process_action_result(result, total_steps=1)
        assert resp.status == "SUCCESS"
        assert resp.evaluation["is_goal_achieved"] is True


# ============================================================================
# 8. Cognitive Artifact Gate Tests
# ============================================================================

class TestArtifactGate:
    def test_valid_candidate_is_staged(self):
        gate = CognitiveArtifactGate()
        cand = CandidateArtifact(
            artifact_id="art-001",
            artifact_type="knowledge_candidate",
            target_system="JAYA_CORE",
            provenance={"source": "arxiv:1234.5678"},
            payload={"delta": "new info"},
            evidence_kind="EMPIRICAL",
            executable=False,
            auto_install=False,
            rollback_info={"rollback_supported": True, "method": "revert_delta"},
        )
        res = gate.evaluate_candidate(cand)
        assert res.is_valid is True
        assert res.status == CandidateStatus.STAGED

    def test_reject_executable_candidate(self):
        gate = CognitiveArtifactGate()
        cand = CandidateArtifact(
            artifact_id="art-bad-exec",
            artifact_type="knowledge_candidate",
            target_system="JAYA_CORE",
            provenance={"source": "untrusted"},
            payload={},
            executable=True,  # Violation!
            rollback_info={"rollback_supported": True},
        )
        res = gate.evaluate_candidate(cand)
        assert res.is_valid is False
        assert res.status == CandidateStatus.REJECTED
        assert any("executable" in r for r in res.rejection_reasons)

    def test_reject_simulation_for_cognitive_update(self):
        gate = CognitiveArtifactGate()
        cand = CandidateArtifact(
            artifact_id="art-sim",
            artifact_type="reasoning_strategy",  # Cognitive update type
            target_system="JAYA_CORE",
            provenance={"source": "sim_run"},
            payload={},
            evidence_kind="SIMULATION",  # Violation!
            executable=False,
            rollback_info={"rollback_supported": True},
        )
        res = gate.evaluate_candidate(cand)
        assert res.is_valid is False
        assert res.status == CandidateStatus.REJECTED
        assert any("SIMULATION" in r for r in res.rejection_reasons)


# ============================================================================
# 9. Sync Event Log Tests
# ============================================================================

class TestSyncEventLog:
    def test_append_and_deduplicate(self):
        log = AppendOnlyEventLog(node_id="node-a")
        e1 = log.append("GOAL_CREATED", {"goal": "g1"})
        assert e1.sequence_number == 1

        cursor = log.get_cursor()
        assert cursor.last_sequence_number == 1

        # Duplicate append_raw
        raw_dup = NodeEvent(
            event_id=e1.event_id,
            event_type="GOAL_CREATED",
            node_id="node-a",
            sequence_number=1,
        )
        assert log.append_raw(raw_dup) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
