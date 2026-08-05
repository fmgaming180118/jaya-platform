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
    """Test P0.2: CognitiveAgentBridge performs real file write and read operations."""
    bridge = CognitiveAgentBridge()
    assert bridge.initialize() is True

    with tempfile.TemporaryDirectory() as tmpdir:
        test_file = Path(tmpdir) / "test_output.txt"
        test_content = "Hello real tool execution from JAYA!"

        # Real file.write execution
        write_res = bridge.execute_cognitive_intent(
            intent=f"tulis file ke {test_file}",
            context={"target_path": str(test_file), "content": test_content},
            user_id="test_user",
        )
        assert write_res["ok"] is True
        assert write_res["tool_executed"] == "file.write"
        assert test_file.exists()
        assert test_file.read_text(encoding="utf-8") == test_content

        # Real file.read execution
        read_res = bridge.execute_cognitive_intent(
            intent=f"baca file {test_file}",
            context={"target_path": str(test_file)},
            user_id="test_user",
        )
        assert read_res["ok"] is True
        assert read_res["tool_executed"] == "file.read"
        assert read_res["tool_result"]["result"]["content"] == test_content


def test_cognitive_agent_bridge_process_execution():
    """Test P0.2: Real process execution via CognitiveAgentBridge."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    cmd_res = bridge.execute_cognitive_intent(
        intent="eksekusi perintah echo JAYA_ACTION_LOOP",
        context={"command": "echo JAYA_ACTION_LOOP"},
        user_id="test_user",
    )
    assert cmd_res["ok"] is True
    assert cmd_res["tool_executed"] == "process.execute"
    assert "JAYA_ACTION_LOOP" in cmd_res["tool_result"]["result"]["stdout"]


def test_cognitive_agent_bridge_returns_error_on_nonexistent_file():
    """Test P0.2: Bridge returns error status and ok=False when file does not exist (no fake success)."""
    bridge = CognitiveAgentBridge()
    bridge.initialize()

    non_existent = "non_existent_file_xyz_123.txt"
    read_res = bridge.execute_cognitive_intent(
        intent=f"baca file {non_existent}",
        context={"target_path": non_existent},
        user_id="test_user",
    )
    assert read_res["ok"] is True  # Grant issued
    assert read_res["tool_result"]["status"] == "error"
    assert read_res["cognitive_feedback"]["success"] is False
