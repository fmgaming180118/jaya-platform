"""
test_phase_f_agent_os.py — Unit tests for Phase F: Agent, OS, and Android.

Covers:
    - CoreToAgentDispatch contract validation (ContractValidator)
    - AgentToolRequest contract validation (grant_token, action allowlist)
    - OsExecutionReceipt contract validation
    - OsBoundaryEnforcer: BOUNDARY_OK on clean repo
    - ConsentRecord TTL and coverage
    - AuditLog: append, query, export
    - PermissionManager: consent gating, revocation rejection, audit recording
    - CompatibilityMatrix: profile registration, compatibility checks, built-in profiles
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

from jaya_os.boundary_enforcer import OsBoundaryEnforcer
from jaya_os.capability_sandbox import CapabilitySandbox
from jaya_os.compatibility_matrix import (
    CompatibilityMatrix,
    ComponentRequirements,
    DeviceProfile,
)
from jaya_os.consent_audit_manager import (
    AuditLog,
    AuditLogEntry,
    ConsentRecord,
    PermissionDenied,
    PermissionManager,
)
from jaya_agent.contracts.core_agent_os_contract import (
    AgentToolRequest,
    ContractValidationResult,
    ContractValidator,
    CoreToAgentDispatch,
    OsExecutionReceipt,
    ResourceBudgetEnvelope,
)


# ===========================================================================
# TestCoreAgentOsContract
# ===========================================================================


class TestCoreAgentOsContract:
    def test_valid_dispatch_passes_validation(self):
        validator = ContractValidator()
        dispatch = CoreToAgentDispatch(
            request_id="req-valid-001",
            plan_id="plan-001",
            goal_title="Read system status",
            resource_budget=ResourceBudgetEnvelope(
                max_duration_seconds=15, max_memory_mb=256
            ),
        )
        result = validator.validate_core_to_agent(dispatch)
        assert result.is_valid is True
        assert result.violations == []

    def test_empty_request_id_is_rejected(self):
        validator = ContractValidator()
        dispatch = CoreToAgentDispatch(
            request_id="",
            plan_id="plan-002",
        )
        result = validator.validate_core_to_agent(dispatch)
        assert result.is_valid is False
        assert any("request_id" in v for v in result.violations)

    def test_budget_exceeding_limit_is_rejected(self):
        validator = ContractValidator()
        dispatch = CoreToAgentDispatch(
            request_id="req-budget-001",
            plan_id="plan-003",
            resource_budget=ResourceBudgetEnvelope(
                max_duration_seconds=9999,  # exceeds max 300
                max_memory_mb=256,
            ),
        )
        result = validator.validate_core_to_agent(dispatch)
        assert result.is_valid is False
        assert any("max_duration_seconds" in v for v in result.violations)

    def test_wrong_schema_version_is_rejected(self):
        validator = ContractValidator()
        dispatch = CoreToAgentDispatch(
            request_id="req-schema-001",
            plan_id="plan-004",
            schema_version="2.0",  # invalid
        )
        result = validator.validate_core_to_agent(dispatch)
        assert result.is_valid is False
        assert any("schema_version" in v for v in result.violations)

    def test_valid_agent_tool_request_passes(self):
        validator = ContractValidator()
        request = AgentToolRequest(
            dispatch_id="disp-001",
            step_id="s1",
            action="system.status",
            resources=["system://status"],
            grant_token="a" * 32,
            idempotency_key="idem-key-12345",
        )
        result = validator.validate_agent_tool_request(request)
        assert result.is_valid is True

    def test_missing_grant_token_is_rejected(self):
        validator = ContractValidator()
        request = AgentToolRequest(
            dispatch_id="disp-002",
            step_id="s1",
            action="fs.read",
            resources=["/tmp/file"],
            grant_token="",
            idempotency_key="idem-key-12345",
        )
        result = validator.validate_agent_tool_request(request)
        assert result.is_valid is False
        assert any("grant_token" in v for v in result.violations)

    def test_forbidden_action_is_rejected(self):
        validator = ContractValidator()
        request = AgentToolRequest(
            dispatch_id="disp-003",
            step_id="s1",
            action="core.modify_policy",  # not in allowlist
            resources=["some.resource"],
            grant_token="a" * 32,
            idempotency_key="idem-key-67890",
        )
        result = validator.validate_agent_tool_request(request)
        assert result.is_valid is False
        assert any("action" in v for v in result.violations)

    def test_valid_os_receipt_passes(self):
        validator = ContractValidator()
        receipt = OsExecutionReceipt(
            dispatch_id="disp-004",
            step_id="s1",
            success=True,
            audit_receipt={"receipt_id": "r001", "status": "SUCCESS"},
        )
        result = validator.validate_os_receipt(receipt)
        assert result.is_valid is True

    def test_successful_receipt_without_audit_is_rejected(self):
        validator = ContractValidator()
        receipt = OsExecutionReceipt(
            dispatch_id="disp-005",
            step_id="s1",
            success=True,
            audit_receipt=None,  # must be present on success
        )
        result = validator.validate_os_receipt(receipt)
        assert result.is_valid is False
        assert any("audit_receipt" in v for v in result.violations)

    def test_failed_receipt_without_error_code_is_rejected(self):
        validator = ContractValidator()
        receipt = OsExecutionReceipt(
            dispatch_id="disp-006",
            step_id="s1",
            success=False,
            error_code=None,  # must be present on failure
        )
        result = validator.validate_os_receipt(receipt)
        assert result.is_valid is False
        assert any("error_code" in v for v in result.violations)


# ===========================================================================
# TestOsBoundaryEnforcer
# ===========================================================================


class TestOsBoundaryEnforcer:
    def test_boundary_ok_on_clean_repo(self):
        # Pass explicit repo_root so the enforcer finds the correct directories
        # regardless of which directory pytest is invoked from.
        enforcer = OsBoundaryEnforcer(repo_root=_REPO_ROOT)
        # Verify scan dirs actually exist before asserting scanned_files count
        jaya_core_exists = (_REPO_ROOT / "packages" / "jaya-core").is_dir()
        jaya_agent_exists = (_REPO_ROOT / "packages" / "jaya-agent").is_dir()
        result = enforcer.enforce()
        assert result.is_ok() is True
        assert result.status == "BOUNDARY_OK"
        assert result.violations == []
        if jaya_core_exists or jaya_agent_exists:
            assert result.scanned_files > 0

    def test_scanned_files_includes_both_modules(self):
        enforcer = OsBoundaryEnforcer(repo_root=_REPO_ROOT)
        result = enforcer.enforce()
        jaya_core_exists = (_REPO_ROOT / "packages" / "jaya-core").is_dir()
        jaya_agent_exists = (_REPO_ROOT / "packages" / "jaya-agent").is_dir()
        if jaya_core_exists and jaya_agent_exists:
            assert result.scanned_files >= 50
        else:
            # At least one dir found — still no violations
            assert result.status == "BOUNDARY_OK"


# ===========================================================================
# TestConsentAuditManager
# ===========================================================================


class TestConsentRecord:
    def test_active_consent_is_active_before_expiry(self):
        now = time.time()
        record = ConsentRecord(
            consent_id="c001",
            subject="agent-001",
            action_set=frozenset({"system.status"}),
            reference="owner-tapped-allow",
            granted_at=now,
            expires_at=now + 60.0,
        )
        assert record.is_active() is True
        assert record.covers("system.status") is True
        assert record.covers("fs.write") is False

    def test_expired_consent_is_not_active(self):
        past = time.time() - 120.0
        record = ConsentRecord(
            consent_id="c002",
            subject="agent-001",
            action_set=frozenset({"system.status"}),
            reference="owner-tapped-allow",
            granted_at=past - 60.0,
            expires_at=past,
        )
        assert record.is_active() is False


class TestAuditLog:
    def test_append_and_query(self):
        log = AuditLog(max_entries=100)
        entry = AuditLogEntry(
            entry_id="e001",
            event_type="GRANT_ISSUED",
            subject="agent-test",
            action="system.status",
            timestamp=time.time(),
        )
        log.append_entry(entry)
        assert log.entry_count == 1
        results = log.query_by_subject("agent-test")
        assert len(results) == 1
        assert results[0].entry_id == "e001"

    def test_query_by_event_type(self):
        log = AuditLog()
        for event_type in ["GRANT_ISSUED", "CONSENT_CREATED", "GRANT_ISSUED"]:
            log.append_entry(
                AuditLogEntry(
                    entry_id=f"e-{event_type}-{time.time()}",
                    event_type=event_type,
                    subject="agent-x",
                    action=None,
                    timestamp=time.time(),
                )
            )
        grant_entries = log.query_by_event_type("GRANT_ISSUED")
        assert len(grant_entries) == 2

    def test_export_json_produces_valid_json(self):
        import json

        log = AuditLog()
        log.append_entry(
            AuditLogEntry(
                entry_id="e001",
                event_type="EXECUTION",
                subject="agent-001",
                action="system.status",
                timestamp=time.time(),
            )
        )
        exported = log.export_json()
        parsed = json.loads(exported)
        assert isinstance(parsed, list)
        assert parsed[0]["event_type"] == "EXECUTION"

    def test_max_entries_eviction(self):
        log = AuditLog(max_entries=10)  # minimum allowed is 10
        for i in range(15):
            log.append_entry(
                AuditLogEntry(
                    entry_id=f"e{i:03d}",
                    event_type="EXECUTION",
                    subject="agent",
                    action="system.status",
                    timestamp=time.time(),
                )
            )
        assert log.entry_count == 10


class TestPermissionManager:
    def _make_sandbox(self) -> CapabilitySandbox:
        return CapabilitySandbox()

    def test_grant_with_valid_consent_succeeds(self):
        pm = PermissionManager(self._make_sandbox())
        pm.record_consent(
            subject="agent-a",
            action_set=["system.status"],
            reference="owner-approved",
            ttl_seconds=60.0,
        )
        token = pm.issue_grant(
            subject="agent-a",
            actions=["system.status"],
            resources={"system.status": ["system://status"]},
            ttl_seconds=30.0,
        )
        assert len(token) > 16

    def test_grant_without_consent_raises_permission_denied(self):
        pm = PermissionManager(self._make_sandbox())
        with pytest.raises(PermissionDenied) as exc_info:
            pm.issue_grant(
                subject="agent-no-consent",
                actions=["system.status"],
                resources={"system.status": ["system://status"]},
                ttl_seconds=10.0,
            )
        assert exc_info.value.code == "CONSENT_NOT_FOUND"

    def test_revoked_subject_cannot_obtain_grant(self):
        pm = PermissionManager(self._make_sandbox())
        pm.record_consent(
            subject="agent-revoked",
            action_set=["system.status"],
            reference="owner-ref",
            ttl_seconds=60.0,
        )
        pm.revoke_subject("agent-revoked", reason="policy breach")
        with pytest.raises(PermissionDenied) as exc_info:
            pm.issue_grant(
                subject="agent-revoked",
                actions=["system.status"],
                resources={"system.status": ["system://status"]},
                ttl_seconds=10.0,
            )
        assert exc_info.value.code == "SUBJECT_REVOKED"

    def test_audit_log_records_consent_and_grant(self):
        pm = PermissionManager(self._make_sandbox())
        pm.record_consent(
            subject="agent-audit",
            action_set=["system.status"],
            reference="ref-001",
            ttl_seconds=60.0,
        )
        pm.issue_grant(
            subject="agent-audit",
            actions=["system.status"],
            resources={"system.status": ["system://status"]},
            ttl_seconds=30.0,
        )
        assert pm.audit_log.entry_count == 2
        consent_entries = pm.audit_log.query_by_event_type("CONSENT_CREATED")
        grant_entries = pm.audit_log.query_by_event_type("GRANT_ISSUED")
        assert len(consent_entries) == 1
        assert len(grant_entries) == 1

    def test_expired_consent_blocks_grant(self):
        fixed_time = time.time()

        def clock_expired():
            return fixed_time + 200  # 200 seconds past consent issue

        # Issue consent with 60s TTL at fixed_time, then check 200s later
        sandbox = self._make_sandbox()
        pm = PermissionManager(sandbox, clock=lambda: fixed_time)
        pm.record_consent(
            subject="agent-expired",
            action_set=["system.status"],
            reference="ref-expired",
            ttl_seconds=60.0,
        )

        # Create new PM with future clock
        pm_future = PermissionManager(sandbox, audit_log=pm.audit_log, clock=clock_expired)
        # Copy consent store manually
        pm_future._consent_records = pm._consent_records

        with pytest.raises(PermissionDenied) as exc_info:
            pm_future.issue_grant(
                subject="agent-expired",
                actions=["system.status"],
                resources={"system.status": ["system://status"]},
                ttl_seconds=10.0,
            )
        assert exc_info.value.code == "CONSENT_NOT_FOUND"


# ===========================================================================
# TestCompatibilityMatrix
# ===========================================================================


class TestCompatibilityMatrix:
    def test_desktop_standard_compatible_with_core_runtime(self):
        matrix = CompatibilityMatrix()
        result = matrix.is_compatible("DESKTOP_STANDARD", "JAYA_CORE_RUNTIME")
        assert result.is_compatible is True
        assert result.fail_reasons == []

    def test_android_mid_range_incompatible_with_research_full(self):
        """JAYA_RESEARCH_FULL requires x86_64; ANDROID_MID_RANGE is ARM64."""
        matrix = CompatibilityMatrix()
        result = matrix.is_compatible("ANDROID_MID_RANGE", "JAYA_RESEARCH_FULL")
        assert result.is_compatible is False
        assert any("CPU arch" in r or "x86_64" in r for r in result.fail_reasons)

    def test_constrained_edge_compatible_with_agent(self):
        matrix = CompatibilityMatrix()
        result = matrix.is_compatible("CONSTRAINED_EDGE", "JAYA_AGENT")
        assert result.is_compatible is True

    def test_constrained_edge_incompatible_with_core_runtime(self):
        """JAYA_CORE_RUNTIME requires ARM64 or x86_64; CONSTRAINED_EDGE is ARM32."""
        matrix = CompatibilityMatrix()
        result = matrix.is_compatible("CONSTRAINED_EDGE", "JAYA_CORE_RUNTIME")
        assert result.is_compatible is False

    def test_raspberry_pi_4_compatible_with_core_runtime(self):
        matrix = CompatibilityMatrix()
        result = matrix.is_compatible("RASPBERRY_PI_4", "JAYA_CORE_RUNTIME")
        assert result.is_compatible is True

    def test_custom_profile_registration_and_check(self):
        matrix = CompatibilityMatrix()
        profile = DeviceProfile(
            device_type="EDGE_NODE",
            min_ram_mb=2048,
            cpu_arch="ARM64",
            os_name="linux",
            python_version=(3, 11),
        )
        matrix.register_profile("CUSTOM_EDGE_ARM64", profile)
        result = matrix.is_compatible("CUSTOM_EDGE_ARM64", "JAYA_CORE_RUNTIME")
        assert result.is_compatible is True

    def test_gpu_requirement_enforced(self):
        matrix = CompatibilityMatrix()
        gpu_req = ComponentRequirements(
            component_name="GPU_MODEL",
            required_min_ram_mb=8192,
            allowed_cpu_archs=frozenset({"x86_64"}),
            allowed_os_names=frozenset({"linux"}),
            required_python_version=(3, 11),
            required_has_gpu=True,
        )
        matrix.register_requirements("GPU_MODEL", gpu_req)

        # DESKTOP_STANDARD has has_gpu=False -> fails
        result_no_gpu = matrix.is_compatible("DESKTOP_STANDARD", "GPU_MODEL")
        assert result_no_gpu.is_compatible is False
        assert any("GPU" in r for r in result_no_gpu.fail_reasons)

        # DESKTOP_GPU has has_gpu=True -> passes
        result_gpu = matrix.is_compatible("DESKTOP_GPU", "GPU_MODEL")
        assert result_gpu.is_compatible is True

    def test_list_compatible_devices(self):
        matrix = CompatibilityMatrix()
        compatible = matrix.list_compatible_devices("JAYA_AGENT")
        # JAYA_AGENT allows all archs and OSes; all 5 built-in profiles should pass
        assert len(compatible) >= 4

    def test_unknown_device_raises_key_error(self):
        matrix = CompatibilityMatrix()
        with pytest.raises(KeyError):
            matrix.is_compatible("NONEXISTENT_DEVICE", "JAYA_AGENT")

    def test_unknown_component_raises_key_error(self):
        matrix = CompatibilityMatrix()
        with pytest.raises(KeyError):
            matrix.is_compatible("DESKTOP_STANDARD", "NONEXISTENT_COMPONENT")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
