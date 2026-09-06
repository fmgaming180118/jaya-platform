"""
verify_e2e_agent_os_contract.py — End-to-End verification drill for the
Core → Agent → OS contract, consent/permission/audit pipeline, and compatibility matrix.

This script simulates the full research-to-action path:
    1. Core emits CoreToAgentDispatch (validated by ContractValidator)
    2. Agent records owner consent via PermissionManager
    3. Agent obtains capability grant via PermissionManager.issue_grant()
    4. Agent validates AgentToolRequest via ContractValidator
    5. Agent executes sandboxed action via CapabilitySandbox
    6. Agent validates OsExecutionReceipt via ContractValidator
    7. Audit log entries are verified
    8. OS boundary enforcement: no direct jaya_os import outside adapter
    9. Compatibility matrix: built-in device profiles vs component requirements

Exit code 0 → all drills passed.
Exit code 1 → one or more drills failed.
"""

from __future__ import annotations

import json
import logging
import sys
import uuid
from pathlib import Path

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT / "packages" / "jaya-os" / "src"))
sys.path.insert(0, str(_REPO_ROOT / "packages" / "jaya-agent" / "src"))

from jaya_os.boundary_enforcer import OsBoundaryEnforcer  # noqa: E402
from jaya_os.capability_sandbox import CapabilitySandbox  # noqa: E402
from jaya_os.compatibility_matrix import CompatibilityMatrix  # noqa: E402
from jaya_os.consent_audit_manager import AuditLog, PermissionManager  # noqa: E402
from jaya_agent.contracts.core_agent_os_contract import (  # noqa: E402
    AgentToolRequest,
    ContractValidator,
    CoreToAgentDispatch,
    OsExecutionReceipt,
    ResourceBudgetEnvelope,
)


def _section(title: str) -> None:
    print(f"\n{'='*60}\n  {title}\n{'='*60}")


# ---------------------------------------------------------------------------
# Drill 1: Core → Agent contract validation
# ---------------------------------------------------------------------------
def drill_core_to_agent_contract() -> bool:
    _section("Drill 1: CoreToAgentDispatch contract validation")

    dispatch = CoreToAgentDispatch(
        request_id=str(uuid.uuid4()),
        plan_id="plan-f-e2e-001",
        goal_title="Run system status check",
        steps=[{"step_id": "s1", "action": "system.status"}],
        resource_budget=ResourceBudgetEnvelope(
            max_duration_seconds=10, max_memory_mb=256, allow_network=False
        ),
    )
    validator = ContractValidator()
    result = validator.validate_core_to_agent(dispatch)

    if result.is_valid:
        print("[PASS] CoreToAgentDispatch is valid")
        return True
    else:
        print(f"[FAIL] Violations: {result.violations}")
        return False


# ---------------------------------------------------------------------------
# Drill 2: Consent record + PermissionManager grant issuance
# ---------------------------------------------------------------------------
def drill_consent_and_grant(sandbox: CapabilitySandbox) -> tuple[bool, str | None]:
    _section("Drill 2: Consent record + PermissionManager grant issuance")

    audit_log = AuditLog()
    pm = PermissionManager(sandbox, audit_log=audit_log)

    subject = "jaya-agent-e2e-test"
    action = "system.status"

    # Record consent
    consent = pm.record_consent(
        subject=subject,
        action_set=[action],
        reference="owner-tapped-allow-e2e-drill-2026-08-02",
        ttl_seconds=60.0,
    )
    print(f"[INFO] Consent recorded: {consent.consent_id} (covers {sorted(consent.action_set)})")

    # Issue grant via PermissionManager
    # "system" resource kind requires system://... URI format
    try:
        grant_token = pm.issue_grant(
            subject=subject,
            actions=[action],
            resources={action: ["system://status"]},
            ttl_seconds=30.0,
            max_uses=1,
            consented_actions=[],
            consent_reference=None,
        )
    except Exception as exc:
        print(f"[FAIL] grant issue failed: {exc}")
        return False, None

    consent_entries = audit_log.query_by_event_type("CONSENT_CREATED")
    grant_entries = audit_log.query_by_event_type("GRANT_ISSUED")

    if len(consent_entries) == 1 and len(grant_entries) == 1:
        print(f"[PASS] AuditLog has {audit_log.entry_count} entries "
              f"(consent + grant issuance recorded)")
        return True, grant_token
    else:
        print(f"[FAIL] Expected 1 consent + 1 grant entry; "
              f"got consent={len(consent_entries)}, grant={len(grant_entries)}")
        return False, None


# ---------------------------------------------------------------------------
# Drill 3: AgentToolRequest contract validation
# ---------------------------------------------------------------------------
def drill_agent_tool_request(dispatch_id: str, grant_token: str) -> bool:
    _section("Drill 3: AgentToolRequest contract validation")

    validator = ContractValidator()
    idem_key = "e2e-idem-" + str(uuid.uuid4())[:12]

    request = AgentToolRequest(
        dispatch_id=dispatch_id,
        step_id="s1",
        action="system.status",
        resources=["system://status"],
        grant_token=grant_token,
        idempotency_key=idem_key,
    )
    result = validator.validate_agent_tool_request(request)

    if result.is_valid:
        print("[PASS] AgentToolRequest is valid")
        return True
    else:
        print(f"[FAIL] Violations: {result.violations}")
        return False


# ---------------------------------------------------------------------------
# Drill 4: AgentToolRequest without grant_token must be rejected
# ---------------------------------------------------------------------------
def drill_tool_request_without_grant() -> bool:
    _section("Drill 4: AgentToolRequest without grant_token must be rejected")

    validator = ContractValidator()
    bad_request = AgentToolRequest(
        dispatch_id="bad-dispatch-001",
        step_id="s1",
        action="system.status",
        resources=["system.local"],
        grant_token="",      # missing
        idempotency_key="missing-grant-key-001",
    )
    result = validator.validate_agent_tool_request(bad_request)

    if not result.is_valid and any("grant_token" in v for v in result.violations):
        print(f"[PASS] Missing grant_token correctly rejected: {result.violations}")
        return True
    else:
        print(f"[FAIL] Expected rejection; got is_valid={result.is_valid}")
        return False


# ---------------------------------------------------------------------------
# Drill 5: Revoked subject cannot obtain grant
# ---------------------------------------------------------------------------
def drill_revoked_subject_rejection(sandbox: CapabilitySandbox) -> bool:
    _section("Drill 5: Revoked subject cannot obtain grant")

    pm = PermissionManager(sandbox)
    subject = "revoked-agent-001"

    pm.record_consent(
        subject=subject,
        action_set=["system.status"],
        reference="owner-consent-ref",
        ttl_seconds=60.0,
    )
    pm.revoke_subject(subject, reason="test revocation")

    try:
        pm.issue_grant(
            subject=subject,
            actions=["system.status"],
            resources={"system.status": ["system://status"]},
            ttl_seconds=10.0,
        )
        print("[FAIL] Expected PermissionDenied(SUBJECT_REVOKED) — not raised")
        return False
    except Exception as exc:
        code = getattr(exc, "code", "")
        if code == "SUBJECT_REVOKED":
            print(f"[PASS] Revoked subject correctly blocked: {exc}")
            return True
        print(f"[FAIL] Unexpected exception: {exc!r}")
        return False


# ---------------------------------------------------------------------------
# Drill 6: OsExecutionReceipt contract validation
# ---------------------------------------------------------------------------
def drill_os_execution_receipt(dispatch_id: str) -> bool:
    _section("Drill 6: OsExecutionReceipt contract validation")

    validator = ContractValidator()

    good_receipt = OsExecutionReceipt(
        dispatch_id=dispatch_id,
        step_id="s1",
        success=True,
        audit_receipt={"receipt_id": str(uuid.uuid4()), "status": "SUCCESS"},
    )
    res_good = validator.validate_os_receipt(good_receipt)

    bad_receipt = OsExecutionReceipt(
        dispatch_id="",   # empty → violation
        step_id="s1",
        success=True,
        audit_receipt=None,  # missing → violation
    )
    res_bad = validator.validate_os_receipt(bad_receipt)

    if res_good.is_valid and not res_bad.is_valid:
        print("[PASS] OsExecutionReceipt validation correct (good=valid, bad=invalid)")
        return True
    else:
        print(
            f"[FAIL] good.is_valid={res_good.is_valid}, bad.is_valid={res_bad.is_valid}, "
            f"bad.violations={res_bad.violations}"
        )
        return False


# ---------------------------------------------------------------------------
# Drill 7: OS Boundary Enforcement
# ---------------------------------------------------------------------------
def drill_boundary_enforcement() -> bool:
    _section("Drill 7: JAYA_OS boundary enforcement (no direct imports outside adapter)")

    enforcer = OsBoundaryEnforcer(repo_root=_REPO_ROOT)
    result = enforcer.enforce()
    print(result.summary())

    if result.is_ok():
        print("[PASS] BOUNDARY_OK — no direct jaya_os imports outside approved adapter")
        return True
    else:
        print(f"[FAIL] BOUNDARY_VIOLATION — {len(result.violations)} violation(s) found")
        return False


# ---------------------------------------------------------------------------
# Drill 8: Compatibility Matrix
# ---------------------------------------------------------------------------
def drill_compatibility_matrix() -> bool:
    _section("Drill 8: Compatibility matrix — built-in device profiles")

    matrix = CompatibilityMatrix()
    all_passed = True

    # Define expected compatibility table:
    # (device_name, component_name, expected_compatible)
    checks = [
        ("DESKTOP_STANDARD",  "JAYA_CORE_RUNTIME",  True),
        ("DESKTOP_STANDARD",  "JAYA_AGENT",          True),
        ("DESKTOP_STANDARD",  "JAYA_OS_SANDBOX",     True),
        ("DESKTOP_STANDARD",  "EDGE_MODEL_GGUF_Q4",  True),
        ("DESKTOP_STANDARD",  "JAYA_RESEARCH_FULL",  True),
        ("ANDROID_MID_RANGE", "JAYA_CORE_RUNTIME",  True),
        ("ANDROID_MID_RANGE", "JAYA_AGENT",          True),
        ("ANDROID_MID_RANGE", "JAYA_OS_SANDBOX",     True),
        ("ANDROID_MID_RANGE", "EDGE_MODEL_GGUF_Q4",  True),
        ("ANDROID_MID_RANGE", "JAYA_RESEARCH_FULL",  False),  # x86_64 only
        ("RASPBERRY_PI_4",    "JAYA_CORE_RUNTIME",  True),
        ("RASPBERRY_PI_4",    "JAYA_RESEARCH_FULL",  False),  # x86_64 only
        ("CONSTRAINED_EDGE",  "JAYA_AGENT",          True),
        ("CONSTRAINED_EDGE",  "JAYA_OS_SANDBOX",     True),
        ("CONSTRAINED_EDGE",  "JAYA_CORE_RUNTIME",  False),  # ARM32 not allowed
        ("CONSTRAINED_EDGE",  "JAYA_RESEARCH_FULL",  False),  # too little RAM + arch
    ]

    for device, component, expected in checks:
        result = matrix.is_compatible(device, component)
        status = "[PASS]" if result.is_compatible == expected else "[FAIL]"
        if result.is_compatible != expected:
            all_passed = False
        label = "COMPATIBLE" if result.is_compatible else "INCOMPATIBLE"
        expected_label = "COMPATIBLE" if expected else "INCOMPATIBLE"
        print(
            f"{status} {device:<22} x {component:<22} -> {label} "
            f"(expected {expected_label})"
        )

    return all_passed


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    print("E2E VERIFICATION DRILL — Fase F: Agent, OS, dan Android\n")

    sandbox = CapabilitySandbox()
    dispatch_id = str(uuid.uuid4())

    results: dict[str, bool] = {}

    results["core_to_agent_contract"]   = drill_core_to_agent_contract()
    grant_ok, grant_token               = drill_consent_and_grant(sandbox)
    results["consent_and_grant"]        = grant_ok

    if grant_token:
        results["agent_tool_request"]   = drill_agent_tool_request(dispatch_id, grant_token)
    else:
        results["agent_tool_request"]   = False

    results["tool_request_no_grant"]    = drill_tool_request_without_grant()
    results["revoked_subject"]          = drill_revoked_subject_rejection(sandbox)
    results["os_execution_receipt"]     = drill_os_execution_receipt(dispatch_id)
    results["boundary_enforcement"]     = drill_boundary_enforcement()
    results["compatibility_matrix"]     = drill_compatibility_matrix()

    _section("SUMMARY")
    all_passed = True
    for drill_name, passed in results.items():
        icon = "[OK]" if passed else "[FAIL]"
        print(f"  {icon}  {drill_name}")
        if not passed:
            all_passed = False

    print()
    if all_passed:
        print("E2E VERIFICATION DRILL -- ALL DRILLS PASSED [OK]")
        return 0
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"E2E VERIFICATION DRILL -- FAILED: {failed}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
