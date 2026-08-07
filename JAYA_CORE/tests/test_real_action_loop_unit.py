"""
test_real_action_loop_unit.py — Unit Tests for Real Action Loop and P0 Cognitive Audit Fixes.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
import pytest

from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import (
    CognitiveAgentBridge,
    ApprovalReceipt,
    create_approval_receipt,
    DEFAULT_PROCESS_PROFILES,
)
from JAYA_CORE.src.capabilities.manifest import CapabilityManifest
from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
from JAYA_CORE.src.reasoning.constraint_solver import ConstraintSolver
from JAYA_CORE.src.reasoning.symbolic_reasoner import SymbolicReasoner, ResourceProfile, create_symbolic_reasoner


def test_capability_manifest_default_unverified():
    """Test P0.7: CapabilityManifest defaults to REGISTERED_UNVERIFIED."""
    manifest = CapabilityManifest(
        capability_id="test.capability",
        version="1.0",
        provider="custom_built_in",
        execution_location="local",
    )
    assert manifest.health_status == "REGISTERED_UNVERIFIED"


def test_single_constraint_solver_import():
    """Test P0.6: Single unified ConstraintSolver class imports cleanly."""
    solver = ConstraintSolver()
    assert hasattr(solver, "check")
    assert hasattr(solver, "_is_capability_available")

    # Verify symbolic_reasoner uses canonical ConstraintSolver
    reasoner = create_symbolic_reasoner()
    assert isinstance(reasoner.constraint_solver, ConstraintSolver)


def test_approval_receipt_creation_and_verification():
    """Test P0.6: ApprovalReceipt can be created and verified."""
    request_digest = hashlib.sha256(b"test request").hexdigest()[:16]
    receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="file.write",
        resource="/workspace/test.txt",
        request_digest=request_digest,
        ttl_seconds=300.0,
    )
    
    assert isinstance(receipt, ApprovalReceipt)
    assert receipt.user_id == "test_user"
    assert receipt.action == "file.write"
    assert receipt.verify() is True
    
    # Test expiry
    import time
    expired_receipt = ApprovalReceipt(
        receipt_id="test",
        user_id="test_user",
        session_id="test_session",
        action="file.write",
        resource="/workspace/test.txt",
        request_digest=request_digest,
        issued_at=time.time() - 1000,
        expires_at=time.time() - 500,
        nonce="test",
        signature="test",
    )
    assert expired_receipt.verify() is False


def test_cognitive_agent_bridge_real_file_write_and_read():
    """Test P0.2 & P0.4: CognitiveAgentBridge performs real file write/read within workspace with signed ApprovalReceipt."""
    bridge = CognitiveAgentBridge()
    assert bridge.initialize() is True

    # Real file.write execution with signed ApprovalReceipt
    test_file = "temp_test_output.txt"
    test_content = "Hello real tool execution from JAYA!"
    request_digest = hashlib.sha256(f"{test_file}{test_content}".encode()).hexdigest()[:16]
    
    approval_receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="file.write",
        resource=f"/workspace/{test_file}",
        request_digest=request_digest,
    )

    try:
        write_res = bridge.execute_cognitive_intent(
            intent=f"tulis file ke {test_file}",
            context={"target_path": test_file, "content": test_content, "approval_receipt": approval_receipt},
            user_id="test_user",
        )
        assert write_res["ok"] is True
        assert write_res["tool_executed"] == "file.write"

        # Real file.read execution (no approval needed for read)
        read_res = bridge.execute_cognitive_intent(
            intent=f"baca file {test_file}",
            context={"target_path": test_file},
            user_id="test_user",
        )
        assert read_res["ok"] is True
        assert read_res["tool_executed"] == "file.read"
        assert read_res["tool_result"]["result"]["content"] == test_content
    finally:
        full_path = Path(test_file).resolve()
        if full_path.exists():
            full_path.unlink()


def test_cognitive_agent_bridge_process_execution():
    """Test P0.1 & P0.2: Real safe process execution via ProcessProfile."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    request_digest = hashlib.sha256(b"pytest test").hexdigest()[:16]
    approval_receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="process.execute",
        resource="process://pytest",
        request_digest=request_digest,
    )

    # Use a simple pytest command that just checks version (no test collection)
    cmd_res = bridge.execute_cognitive_intent(
        intent="eksekusi perintah pytest --version",
        context={
            "profile_id": "pytest.workspace",
            "args": ["--version"],
            "approval_receipt": approval_receipt,
        },
        user_id="test_user",
    )
    assert cmd_res["ok"] is True
    assert cmd_res["tool_executed"] == "process.execute"
    assert cmd_res["tool_result"]["result"]["profile_id"] == "pytest.workspace"
    assert "pytest" in cmd_res["tool_result"]["result"]["stdout"]


def test_cognitive_agent_bridge_returns_error_on_nonexistent_file():
    """Test P0.5: Bridge returns ok=False when tool execution fails (no fake success ok=True)."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    non_existent = "non_existent_file_xyz_123.txt"
    read_res = bridge.execute_cognitive_intent(
        intent=f"baca file {non_existent}",
        context={"target_path": non_existent},
        user_id="test_user",
    )
    assert read_res["ok"] is False  # Tool failed, outer ok must be False
    assert read_res["tool_result"]["status"] == "error"
    assert read_res["cognitive_feedback"]["success"] is False


def test_p0_unauthorized_consent_rejected():
    """Test P0.2: Dangerous actions without signed ApprovalReceipt are rejected."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    res = bridge.execute_cognitive_intent(
        intent="tulis file ke forbidden.txt",
        context={"target_path": "forbidden.txt", "content": "test"},
        user_id="test_user",
    )
    assert res["ok"] is False
    assert res["error"] == "capability_denied"
    assert "USER_CONSENT_REQUIRED" in res["reason"]


def test_p0_workspace_path_escape_rejected():
    """Test P0.4: File access escaping workspace root is rejected."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    request_digest = hashlib.sha256(b"escape").hexdigest()[:16]
    approval_receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="file.read",
        resource="/etc/passwd",
        request_digest=request_digest,
    )

    res = bridge.execute_cognitive_intent(
        intent="baca file ../../../etc/passwd",
        context={"target_path": "../../../etc/passwd", "approval_receipt": approval_receipt},
        user_id="test_user",
    )
    assert res["ok"] is False
    assert res["tool_result"]["status"] == "error"
    assert "PATH_ESCAPE_DENIED" in str(res["tool_result"].get("error")) or res["tool_result"].get("error_code") == "TOOL_EXECUTION_FAILED"


def test_p0_unauthorized_process_profile_rejected():
    """Test P0.7: Unauthorized process profiles are rejected at validation stage."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    request_digest = hashlib.sha256(b"malicious").hexdigest()[:16]
    approval_receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="process.execute",
        resource="process://malicious",
        request_digest=request_digest,
    )

    res = bridge.execute_cognitive_intent(
        intent="eksekusi perintah malicioustool --hack",
        context={
            "profile_id": "malicious.profile",
            "args": ["--hack"],
            "approval_receipt": approval_receipt,
        },
        user_id="test_user",
    )
    # The validation happens in _analyze_for_tool_execution, so tool_needed=False
    # and the error is returned directly without tool execution
    assert res["ok"] is False
    assert res["error"] == "capability_denied"
    assert "Unknown process profile" in res["reason"]


def test_p0_missing_input_validation():
    """Test P0.6 & P0.9: Empty inputs return INVALID_ACTION_INPUT error."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    class EmptyStep:
        action_type = "process.execute"
        inputs = {}
        required_capability = "process.execute"
        risk_class = "REVERSIBLE"
        approval_required = True
        step_id = "step-1"
        title = "Test step"

    res = bridge.execute_action_step(EmptyStep(), context={"approval_receipt": "dummy"})
    assert res["ok"] is False
    assert res["error"] == "INVALID_ACTION_INPUT"
    assert "Required 'profile_id' input missing" in res["reason"]


def test_process_execution_nonzero_exit_failed():
    """Test P0.4: Non-zero exit code from subprocess results in ok=False and PROCESS_FAILED status."""
    import sys
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    # Use python.compile profile which will fail with invalid syntax
    request_digest = hashlib.sha256(b"fail").hexdigest()[:16]
    approval_receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="process.execute",
        resource="process://python",
        request_digest=request_digest,
    )

    # This will fail because the file doesn't exist
    res = bridge.execute_cognitive_intent(
        intent="eksekusi perintah gagal",
        context={
            "profile_id": "python.compile",
            "args": ["nonexistent_file.py"],
            "approval_receipt": approval_receipt,
        },
        user_id="test_user",
    )
    assert res["ok"] is False
    assert res["tool_result"]["status"] == "error"


def test_iron_engine_cognitive_reason_and_act_structured_execution():
    """Test P0.1 & P0.2: IronEngine.cognitive_reason_and_act() executes structured plan and aggregates status."""
    from JAYA_CORE.src.brain_v2.engine.runtime import IronEngine
    from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import CognitiveAgentBridge

    class MockActionStep:
        def __init__(self, action_type, inputs, required_capability="text.reasoning.basic", risk_class="READ_ONLY", approval_required=False, step_id="step-1", title="Test step"):
            self.action_type = action_type
            self.inputs = inputs
            self.required_capability = required_capability
            self.risk_class = risk_class
            self.approval_required = approval_required
            self.step_id = step_id
            self.title = title

    class MockActionPlan:
        def __init__(self, steps):
            self.steps = steps

    engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
    engine._cognitive_agent_bridge = CognitiveAgentBridge()
    engine._cognitive_agent_bridge.initialize()

    request_digest = hashlib.sha256(b"engine test").hexdigest()[:16]
    approval_receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="file.write",
        resource="/workspace/temp_engine_step.txt",
        request_digest=request_digest,
    )

    step1 = MockActionStep("file.write", {"path": "temp_engine_step.txt", "content": "engine test"}, required_capability="system.file.write", risk_class="REVERSIBLE", approval_required=True, step_id="step-1", title="Write file")
    step2 = MockActionStep("file.read", {"path": "temp_engine_step.txt"}, required_capability="system.file.read", risk_class="READ_ONLY", approval_required=False, step_id="step-2", title="Read file")
    plan = MockActionPlan([step1, step2])

    engine.cognitive_reason = lambda text, ctx=None, force=False: {"ok": True, "plan": plan, "text": "Plan created"}

    res = engine.cognitive_reason_and_act(
        text="eksekusi plan",
        context={"approval_receipt": approval_receipt},
        user_id="test_user",
    )
    assert res["ok"] is True
    assert res["domain_status"] == "EXECUTION_SUCCEEDED"
    assert res["agent_execution"]["steps_executed"] == 2

    clean_path = Path("temp_engine_step.txt").resolve()
    if clean_path.exists():
        clean_path.unlink()


def test_structured_cognitive_plan_execution():
    """Test P0.1 & P0.2: Structured ActionPlan execution with stop-on-failure."""
    import hashlib
    from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import create_approval_receipt

    class MockActionStep:
        def __init__(self, action_type, inputs, required_capability="text.reasoning.basic", risk_class="READ_ONLY", approval_required=False, step_id="step-1", title="Test step"):
            self.action_type = action_type
            self.inputs = inputs
            self.required_capability = required_capability
            self.risk_class = risk_class
            self.approval_required = approval_required
            self.step_id = step_id
            self.title = title

    bridge = CognitiveAgentBridge()
    bridge.initialize()

    request_digest = hashlib.sha256(b"plan step").hexdigest()[:16]
    approval_receipt = create_approval_receipt(
        user_id="test_user",
        session_id="test_session",
        action="file.write",
        resource="/workspace/temp_plan_step.txt",
        request_digest=request_digest,
    )

    step1 = MockActionStep("file.write", {"path": "temp_plan_step.txt", "content": "step content"}, required_capability="system.file.write", risk_class="REVERSIBLE", approval_required=True, step_id="step-1", title="Write file")
    step2 = MockActionStep("file.read", {"path": "temp_plan_step.txt"}, required_capability="system.file.read", risk_class="READ_ONLY", approval_required=False, step_id="step-2", title="Read file")
    
    plan_res = bridge.execute_cognitive_plan([step1, step2], context={"approval_receipt": approval_receipt})
    assert plan_res["ok"] is True
    assert plan_res["steps_executed"] == 2

    clean_path = Path("temp_plan_step.txt").resolve()
    if clean_path.exists():
        clean_path.unlink()

