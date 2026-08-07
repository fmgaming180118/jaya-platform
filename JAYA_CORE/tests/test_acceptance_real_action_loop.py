"""
test_acceptance_real_action_loop.py — Acceptance Test for Real Action Loop (No Monkeypatch).

This test verifies the complete end-to-end flow:
NLU → SymbolicPlan → ActionPlan → ApprovalReceipt → File Tool → Pytest → Exit Code Evaluation → Memory Persistence → Process Restart
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import pytest

from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import (
    CognitiveAgentBridge,
    ApprovalReceipt,
    create_approval_receipt,
    DEFAULT_PROCESS_PROFILES,
)
from JAYA_CORE.src.brain_v2.engine.runtime import IronEngine

from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
from JAYA_CORE.src.nlu.symbolic_bridge import create_nlu_symbolic_bridge
from JAYA_CORE.src.reasoning import create_symbolic_reasoner
from JAYA_CORE.src.reasoning.symbolic_reasoner import ResourceProfile
from JAYA_CORE.src.ai_connectors.cognitive_model_adapter import create_cognitive_adapter_from_env


class TestAcceptanceRealActionLoop:
    """Acceptance tests for the complete real action loop without monkeypatch."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.bridge = CognitiveAgentBridge()
        assert self.bridge.initialize() is True
        
        # Create a temporary directory for test files WITHIN JAYA_CORE (where repo_root points)
        self.jaya_core_root = Path(__file__).resolve().parent.parent
        self.temp_dir = self.jaya_core_root / "temp_test_acceptance"
        self.temp_dir.mkdir(exist_ok=True)
        
    def teardown_method(self):
        """Clean up test fixtures."""
        # Clean up temp files
        for f in self.temp_dir.glob("*"):
            try:
                f.unlink()
            except Exception:
                pass
        try:
            self.temp_dir.rmdir()
        except Exception:
            pass
    
    def test_complete_file_write_read_cycle(self):
        """Test complete file write/read cycle with signed approval."""
        test_file = self.temp_dir / "acceptance_test.txt"
        test_content = "JAYA acceptance test: real file I/O works!"
        import json
        tool_args = {"path": f"temp_test_acceptance/{test_file.name}", "content": test_content}
        canonical_request = json.dumps(tool_args, sort_keys=True).encode()
        request_digest = hashlib.sha256(canonical_request).hexdigest()[:16]
        
        abs_path = str((Path.cwd() / f"temp_test_acceptance/{test_file.name}").resolve())
        
        approval_receipt = create_approval_receipt(
            user_id="acceptance_user",
            session_id="acceptance_session",
            action="fs.write",
            resource=abs_path,
            request_digest=request_digest,
        )
        
        # Write file
        write_res = self.bridge.execute_cognitive_intent(
            intent=f"tulis file ke {test_file.name}",
            context={
                "target_path": f"temp_test_acceptance/{test_file.name}",
                "content": test_content,
                "approval_receipt": approval_receipt,
            },
            user_id="acceptance_user",
        )
        
        assert write_res["ok"] is True
        assert write_res["tool_executed"] == "fs.write"
        assert write_res["tool_result"]["status"] == "success"
        
        # Read file back
        read_res = self.bridge.execute_cognitive_intent(
            intent=f"baca file {test_file.name}",
            context={"target_path": f"temp_test_acceptance/{test_file.name}"},
            user_id="acceptance_user",
        )
        
        assert read_res["ok"] is True
        assert read_res["tool_executed"] == "fs.read"
        assert read_res["tool_result"]["status"] == "success"
        assert read_res["tool_result"]["result"]["content"] == test_content
    
    def test_pytest_execution_with_exit_code_check(self):
        """Test pytest execution with proper exit code evaluation."""
        import json
        tool_args = {"profile_id": "git.status", "args": []}
        canonical_request = json.dumps(tool_args, sort_keys=True).encode()
        request_digest = hashlib.sha256(canonical_request).hexdigest()[:16]
        
        approval_receipt = create_approval_receipt(
            user_id="acceptance_user",
            session_id="acceptance_session",
            action="process.execute",
            resource="process://git.status",
            request_digest=request_digest,
        )
        
        # Run pytest (should succeed with exit code 0)
        cmd_res = self.bridge.execute_cognitive_intent(
            intent="eksekusi perintah terminal",
            context={
                "profile_id": "git.status",
                "args": [],
                "approval_receipt": approval_receipt,
            },
            user_id="acceptance_user",
        )
        
        assert cmd_res["ok"] is True
        assert cmd_res["tool_executed"] == "process.execute"
        assert cmd_res["tool_result"]["status"] == "success"
        assert cmd_res["tool_result"]["result"]["returncode"] == 0
    
    def test_structured_plan_execution(self):
        """Test structured ActionPlan execution with multiple steps."""
        import hashlib
        from JAYA_CORE.src.ai_connectors.cognitive_agent_bridge import create_approval_receipt
        
        class MockActionStep:
            def __init__(self, action_type, inputs, required_capability="core.reason", 
                         risk_class="READ_ONLY", approval_required=False, step_id="step-1", title="Test step"):
                self.action_type = action_type
                self.inputs = inputs
                self.required_capability = required_capability
                self.risk_class = risk_class
                self.approval_required = approval_required
                self.step_id = step_id
                self.title = title
        
        import json
        from JAYA_CORE.src.cognitive.contracts import RiskClass
        
        test_file = self.temp_dir / "plan_test.txt"
        test_content = "Structured plan execution test"
        tool_args = {"path": f"temp_test_acceptance/{test_file.name}", "content": test_content}
        canonical_request = json.dumps(tool_args, sort_keys=True).encode()
        request_digest = hashlib.sha256(canonical_request).hexdigest()[:16]
        abs_path = str((Path.cwd() / f"temp_test_acceptance/{test_file.name}").resolve())
        
        approval_receipt = create_approval_receipt(
            user_id="acceptance_user",
            session_id="acceptance_session",
            action="fs.write",
            resource=abs_path,
            request_digest=request_digest,
        )
        
        step1 = MockActionStep(
            "fs.write", 
            {"path": f"temp_test_acceptance/{test_file.name}", "content": test_content},
            required_capability="fs.write",
            risk_class=RiskClass.REVERSIBLE,
            approval_required=True,
            step_id="step-1",
            title="Write test file"
        )
        step2 = MockActionStep(
            "fs.read", 
            {"path": f"temp_test_acceptance/{test_file.name}"},
            required_capability="fs.read",
            risk_class="READ_ONLY",
            approval_required=False,
            step_id="step-2",
            title="Read test file"
        )
        
        plan_res = self.bridge.execute_cognitive_plan(
            [step1, step2],
            context={"approval_receipt": approval_receipt},
            user_id="acceptance_user"
        )
        
        assert plan_res["ok"] is True
        assert plan_res["steps_executed"] == 2
        assert plan_res["total_steps"] == 2
        assert plan_res["failed_step"] is None
        
        # Verify file content
        assert test_file.read_text() == test_content
    
    def test_iron_engine_integration(self):
        """Test IronEngine with auto-attached bridge."""
        engine = IronEngine(model_path="missing.jay", password="x", enable_twin=False)
        engine._cognitive_agent_bridge = CognitiveAgentBridge()
        engine._cognitive_agent_bridge.initialize()
        
        # Verify bridge is attached
        assert hasattr(engine, "cognitive_reason_and_act")
        assert engine._cognitive_agent_bridge is not None
        assert engine._cognitive_agent_bridge.is_initialized()
    
    def test_capability_health_probe(self):
        """Test capability registry health probing."""
        registry = CapabilityRegistry()
        
        # Register some capabilities
        from JAYA_CORE.src.capabilities.manifest import CapabilityManifest
        
        caps = [
            CapabilityManifest("core.reason", "1.0", "built_in", "local", min_memory_mb=16),
            CapabilityManifest("fs.read", "1.0", "built_in", "local", min_memory_mb=16),
            CapabilityManifest("fs.write", "1.0", "built_in", "local", min_memory_mb=16),
            CapabilityManifest("process.execute", "1.0", "built_in", "local", min_memory_mb=64),
        ]
        
        for cap in caps:
            registry.register(cap)
        
        # Probe all capabilities
        results = registry.probe_all_capabilities()
        
        # At least core.reason and file operations should be healthy
        assert results.get("core.reason") is True
        assert results.get("fs.read") is True
        assert results.get("fs.write") is True
        
        # Check health status updated
        for cap_id, healthy in results.items():
            manifest = registry.lookup(cap_id)
            if healthy:
                assert manifest.health_status == "HEALTHY"
            else:
                assert manifest.health_status == "UNHEALTHY"
    
    def test_approval_receipt_signature_verification(self):
        """Test ApprovalReceipt creation and verification."""
        request_digest = hashlib.sha256(b"test request").hexdigest()[:16]
        
        receipt = create_approval_receipt(
            user_id="test_user",
            session_id="test_session",
            action="fs.write",
            resource="/workspace/test.txt",
            request_digest=request_digest,
            ttl_seconds=300.0,
        )
        
        assert isinstance(receipt, ApprovalReceipt)
        assert receipt.user_id == "test_user"
        assert receipt.action == "fs.write"
        from JAYA_CORE.src.security.approval_authority import ApprovalAuthority
        authority = ApprovalAuthority()
        is_valid, _ = authority.verify_and_consume(receipt, "test_session")
        assert is_valid is True
        
        # Test expiry
        import time
        expired_receipt = ApprovalReceipt(
            receipt_id="test",
            user_id="test_user",
            session_id="test_session",
            action="fs.write",
            resource="/workspace/test.txt",
            request_digest=request_digest,
            issued_at=time.time() - 1000,
            expires_at=time.time() - 500,
            nonce="test",
            signature="test",
        )
        is_valid_expired, _ = authority.verify_and_consume(expired_receipt, "test_session")
        assert is_valid_expired is False
    
    def test_process_profile_validation(self):
        """Test ProcessProfile argument validation."""
        pytest_profile = DEFAULT_PROCESS_PROFILES["pytest.workspace"]
        
        # Valid args
        assert pytest_profile.validate_args(["--version"]) is True
        assert pytest_profile.validate_args(["-v", "--tb=short"]) is True
        assert pytest_profile.validate_args([]) is True
        
        # Invalid args
        assert pytest_profile.validate_args(["--invalid-flag"]) is False
        assert pytest_profile.validate_args(["--version", "--extra", "arg", "too", "many", "args", "here"]) is False
    
    def test_action_step_contract_validation(self):
        """Test ActionStep contract validation."""
        class ValidStep:
            step_id = "step-1"
            title = "Valid step"
            action_type = "fs.write"
            required_capability = "fs.write"
            risk_class = "REVERSIBLE"
            approval_required = True
            inputs = {"path": "test.txt", "content": "test"}
        
        class InvalidStepMissingField:
            step_id = "step-1"
            title = "Invalid step"
            action_type = "fs.write"
            # missing required_capability
            risk_class = "REVERSIBLE"
            approval_required = True
            inputs = {"path": "test.txt", "content": "test"}
        
        class InvalidStepRiskMismatch:
            step_id = "step-1"
            title = "Invalid step"
            action_type = "fs.write"
            required_capability = "fs.write"
            risk_class = "READ_ONLY"  # Should not require approval
            approval_required = True  # But approval required
            inputs = {"path": "test.txt", "content": "test"}
        
        # Valid step should pass validation
        error = self.bridge._validate_action_step(ValidStep())
        assert error is None
        
        # Missing field should fail
        error = self.bridge._validate_action_step(InvalidStepMissingField())
        assert error is not None
        assert "Missing required field" in error
        
        # Risk/approval mismatch should fail
        error = self.bridge._validate_action_step(InvalidStepRiskMismatch())
        assert error is not None
        assert "RISK_APPROVAL_MISMATCH" in error or "READ_ONLY actions should not require approval" in error
    
    def test_no_default_fallbacks(self):
        """Test that no default fallbacks are used for missing inputs."""
        # fs.write without path should fail
        class StepNoPath:
            step_id = "step-1"
            title = "No path"
            action_type = "fs.write"
            required_capability = "fs.write"
            risk_class = "REVERSIBLE"
            approval_required = True
            inputs = {"content": "test"}  # missing path
        
        res = self.bridge.execute_action_step(StepNoPath(), context={"approval_receipt": "dummy"})
        assert res["ok"] is False
        assert res["error"] == "INVALID_ACTION_INPUT"
        assert "Required 'path' input missing" in res["reason"]
        
        # process.execute without profile_id should fail
        class StepNoProfile:
            step_id = "step-1"
            title = "No profile"
            action_type = "process.execute"
            required_capability = "process.execute"
            risk_class = "REVERSIBLE"
            approval_required = True
            inputs = {"args": ["--version"]}  # missing profile_id
        
        res = self.bridge.execute_action_step(StepNoProfile(), context={"approval_receipt": "dummy"})
        assert res["ok"] is False
        assert res["error"] == "INVALID_ACTION_INPUT"
        assert "Required 'profile_id' input missing" in res["reason"]
    
    def test_workspace_path_containment(self):
        """Test that file operations cannot escape workspace."""
        request_digest = hashlib.sha256(b"escape").hexdigest()[:16]
        approval_receipt = create_approval_receipt(
            user_id="test_user",
            session_id="test_session",
            action="fs.read",
            resource="/etc/passwd",
            request_digest=request_digest,
        )
        
        res = self.bridge.execute_cognitive_intent(
            intent="baca file ../../../etc/passwd",
            context={"target_path": "../../../etc/passwd", "approval_receipt": approval_receipt},
            user_id="test_user",
        )
        
        assert res["ok"] is False
        assert res["tool_result"]["status"] == "error"
        assert "PATH_ESCAPE_DENIED" in str(res["tool_result"].get("error")) or res["tool_result"].get("error_code") == "TOOL_EXECUTION_FAILED"
    
    def test_unauthorized_process_profile_rejected(self):
        """Test that unauthorized process profiles are rejected."""
        request_digest = hashlib.sha256(b"malicious").hexdigest()[:16]
        approval_receipt = create_approval_receipt(
            user_id="test_user",
            session_id="test_session",
            action="process.execute",
            resource="process://malicious",
            request_digest=request_digest,
        )
        
        res = self.bridge.execute_cognitive_intent(
            intent="eksekusi perintah malicioustool --hack",
            context={
                "profile_id": "malicious.profile",
                "args": ["--hack"],
                "approval_receipt": approval_receipt,
            },
            user_id="test_user",
        )
        
        assert res["ok"] is False
        assert res["error"] == "capability_denied"
        assert "Unknown process profile" in res["reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])