"""
test_real_action_loop_unit.py — Unit Tests for Real Action Loop and P0 Cognitive Audit Fixes.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
import pytest

from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import CognitiveAgentBridge
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


def test_cognitive_agent_bridge_real_file_write_and_read():
    """Test P0.2 & P0.4: CognitiveAgentBridge performs real file write/read within workspace with explicit consent."""
    bridge = CognitiveAgentBridge()
    assert bridge.initialize() is True

    # Real file.write execution with explicit consent context
    test_file = "temp_test_output.txt"
    test_content = "Hello real tool execution from JAYA!"

    try:
        write_res = bridge.execute_cognitive_intent(
            intent=f"tulis file ke {test_file}",
            context={"target_path": test_file, "content": test_content, "auto_consent": True},
            user_id="test_user",
        )
        assert write_res["ok"] is True
        assert write_res["tool_executed"] == "file.write"

        # Real file.read execution
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
    """Test P0.1 & P0.2: Real safe process execution (no shell=True) via CognitiveAgentBridge."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    cmd_res = bridge.execute_cognitive_intent(
        intent="eksekusi perintah echo JAYA_ACTION_LOOP",
        context={"command": "echo JAYA_ACTION_LOOP", "auto_consent": True},
        user_id="test_user",
    )
    assert cmd_res["ok"] is True
    assert cmd_res["tool_executed"] == "process.execute"
    assert "JAYA_ACTION_LOOP" in cmd_res["tool_result"]["result"]["stdout"]


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
    """Test P0.2: Dangerous actions without consent in context are rejected."""
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

    res = bridge.execute_cognitive_intent(
        intent="baca file ../../../etc/passwd",
        context={"target_path": "../../../etc/passwd"},
        user_id="test_user",
    )
    assert res["ok"] is False
    assert res["tool_result"]["status"] == "error"
    assert "PATH_ESCAPE_DENIED" in str(res["tool_result"].get("error")) or res["tool_result"].get("error_code") == "TOOL_EXECUTION_FAILED"


def test_p0_unauthorized_command_executable_rejected():
    """Test P0.1: Command injection / unauthorized binaries without shell=True are rejected."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    res = bridge.execute_cognitive_intent(
        intent="jalankan perintah malicioustool --hack",
        context={"command": "malicioustool --hack", "auto_consent": True},
        user_id="test_user",
    )
    assert res["ok"] is False
    assert res["tool_result"]["status"] == "error"


def test_structured_action_step_execution():
    """Test Real Action Loop: Direct execution of structured ActionStep."""
    class MockActionStep:
        def __init__(self, action_type, inputs):
            self.action_type = action_type
            self.inputs = inputs

    bridge = CognitiveAgentBridge()
    bridge.initialize()

    step = MockActionStep("file.write", {"path": "temp_step.txt", "content": "step content"})
    res = bridge.execute_action_step(step, context={"auto_consent": True})
    
    assert res["ok"] is True
    assert res["action_type"] == "file.write"
    
    clean_path = Path("temp_step.txt").resolve()
    if clean_path.exists():
        clean_path.unlink()

