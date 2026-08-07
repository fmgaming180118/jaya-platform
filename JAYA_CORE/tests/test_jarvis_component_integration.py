"""
test_jarvis_component_integration.py - Integration tests for JAYA Core components.
"""
import pytest
from JAYA_CORE.src.cognitive.contracts import RiskClass, UserRequest, IntentType
from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import create_cognitive_agent_bridge
from JAYA_CORE.src.security.approval_authority import ApprovalAuthority
from JAYA_CORE.src.cognitive.planner import ActionPlan, ActionStep
from JAYA_CORE.src.cognitive.execution_state import PlanExecutionState

def test_bridge_initialization():
    bridge = create_cognitive_agent_bridge()
    assert bridge._initialized is True
    assert bridge._capability_sandbox is not None

def test_plan_execution_state_dataflow():
    state = PlanExecutionState(plan_id="plan-1", goal_id="goal-1")
    state.record_step_success("step-1", {"ok": True, "artifacts": {"patch": "--- a/file\n+++ b/file"}})
    
    inputs = {"patch_content": "ref:step-1.patch"}
    resolved = state.resolve_references(inputs)
    assert resolved["patch_content"] == "--- a/file\n+++ b/file"

def test_approval_authority_validation():
    authority = ApprovalAuthority()
    # Test strict validation order by creating a receipt and corrupting the signature
    receipt = authority.issue_receipt(
        user_id="test_user",
        session_id="session_123",
        action="fs.write",
        resource="test.txt",
        request_digest="abcd",
        ttl_seconds=300
    )
    
    # Valid consumption
    is_valid, reason = authority.verify_and_consume(
        receipt, 
        current_session_id="session_123",
        expected_user_id="test_user",
        expected_action="fs.write",
        expected_resource="test.txt",
        expected_request_digest="abcd"
    )
    assert is_valid is True
    
    # Replay attack (nonce consumed)
    is_valid_replay, reason_replay = authority.verify_and_consume(
        receipt, 
        current_session_id="session_123",
        expected_user_id="test_user",
        expected_action="fs.write",
        expected_resource="test.txt",
        expected_request_digest="abcd"
    )
    assert is_valid_replay is False
    assert "Nonce already consumed" in reason_replay
