#!/usr/bin/env python3
"""Measure Tahap 2 progress from executable sovereign evidence gates."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PILLAR_MANIFEST = (
    ROOT / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
)
TEST_FILES = (
    ROOT / "packages" / "jaya-core" / "tests" / "test_sovereign_foundation.py",
    ROOT / "packages" / "jaya-core" / "tests" / "test_approval_trust.py",
    ROOT / "packages" / "jaya-core" / "tests" / "test_sovereign_privacy.py",
    ROOT / "packages" / "jaya-core" / "tests" / "test_privacy_consent_trust.py",
    ROOT / "packages" / "jaya-core" / "tests" / "test_zero_trust_authority.py",
    ROOT / "packages" / "jaya-core" / "tests" / "test_zero_trust_lifecycle.py",
    ROOT / "packages" / "jaya-core" / "tests" / "test_logical_foundation.py",
)
P11_DEMO = ROOT / "scripts" / "demo_sovereign_foundation.py"
P15_DEMO = ROOT / "scripts" / "demo_ethical_heart.py"
P20_DEMO = ROOT / "scripts" / "demo_sovereign_privacy.py"
P18_DEMO = ROOT / "scripts" / "demo_zero_trust.py"


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    weight: int
    tests: tuple[str, ...] = ()
    demo: bool = False
    unavailable_reason: str = ""


class SovereignAuditError(RuntimeError):
    """The canonical status source cannot be audited safely."""


def _canonical_statuses() -> dict[str, str]:
    """Load maturity independently from the production-readiness percentage."""
    try:
        payload = yaml.safe_load(PILLAR_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise SovereignAuditError from exc
    if not isinstance(payload, list):
        raise SovereignAuditError
    statuses: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict) or type(item.get("id")) is not int:
            raise SovereignAuditError
        statuses[f"P{item['id']:03d}"] = str(item.get("status", ""))
    if len(statuses) != len(payload):
        raise SovereignAuditError
    return statuses


P11_GATES = (
    Gate(
        "versioned_contract",
        10,
        ("test_p11_enrollment_challenge_restart_and_replay_protection",),
    ),
    Gate(
        "explicit_enrollment",
        10,
        (
            "test_p11_enrollment_challenge_restart_and_replay_protection",
            "test_p11_owner_cli_runs_real_enroll_verify_rotate_and_revoke",
        ),
    ),
    Gate(
        "portable_brain_identity",
        10,
        (
            "test_p11_official_file_migration_preserves_identity_clone_without_key_fails",
            "test_p11_runtime_boot_uses_portable_brain_identity_and_distinct_node",
        ),
    ),
    Gate(
        "encrypted_injected_keystore",
        10,
        ("test_p11_duplicate_enrollment_wrong_secret_and_lost_keystore_fail_closed",),
    ),
    Gate(
        "production_secret_manager",
        5,
        unavailable_reason=(
            "belum diuji dengan OS keystore atau secret manager pada target produksi"
        ),
    ),
    Gate(
        "challenge_response_replay_expiry",
        15,
        (
            "test_p11_enrollment_challenge_restart_and_replay_protection",
            "test_p11_expired_modified_and_wrong_owner_challenges_fail_closed",
        ),
    ),
    Gate(
        "rotation_and_revocation",
        10,
        (
            "test_p11_rotation_preserves_brain_and_owner_but_invalidates_old_signature",
            "test_p11_revoked_identity_cannot_regain_authority",
        ),
    ),
    Gate(
        "runtime_boot_gate",
        10,
        (
            "test_p11_authorized_runtime_fails_closed_without_or_after_revoked_identity",
            "test_p11_canonical_launcher_loads_enrolled_identity_from_validated_config",
        ),
    ),
    Gate(
        "restart_and_migration",
        5,
        (
            "test_p11_enrollment_challenge_restart_and_replay_protection",
            "test_p11_official_file_migration_preserves_identity_clone_without_key_fails",
        ),
    ),
    Gate(
        "tamper_and_failure_paths",
        5,
        (
            "test_p11_tampered_identity_and_audit_ledger_are_detected",
            "test_p11_expired_modified_and_wrong_owner_challenges_fail_closed",
            "test_p11_duplicate_enrollment_wrong_secret_and_lost_keystore_fail_closed",
        ),
    ),
    Gate("real_demo_and_measurement", 5, demo=True),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason="belum ada telemetry identity dari deployment persisten",
    ),
)

P15_GATES = (
    Gate(
        "structured_contract",
        5,
        ("test_p15_structured_policy_is_deterministic_and_persistent",),
    ),
    Gate(
        "policy_integrity_and_versioning",
        10,
        ("test_p15_policy_version_conflict_and_receipt_tamper_fail_closed",),
    ),
    Gate(
        "deterministic_three_way_decision",
        15,
        ("test_p15_structured_policy_is_deterministic_and_persistent",),
    ),
    Gate(
        "mandatory_call_capability_gate",
        15,
        (
            "test_p15_call_capability_gate_cannot_be_bypassed_by_payload_text",
            "test_p15_canonical_planner_is_gated_before_jayair_handoff",
            "test_p15_runtime_registry_rejects_missing_or_forged_policy_receipt",
        ),
    ),
    Gate(
        "independent_signed_owner_approval",
        10,
        (
            "test_p15_owner_approval_is_signed_bound_expiring_and_one_time",
            "test_p15_dynamic_trust_rotation_revocation_recovery_and_restart",
        ),
    ),
    Gate(
        "dna_signed_decision_receipts",
        10,
        ("test_p15_runtime_signs_receipts_with_dna_and_preserves_them_on_restart",),
    ),
    Gate(
        "restart_and_tamper_detection",
        10,
        (
            "test_p15_runtime_signs_receipts_with_dna_and_preserves_them_on_restart",
            "test_p15_policy_version_conflict_and_receipt_tamper_fail_closed",
            "test_p15_dynamic_trust_tamper_and_wrong_root_fail_closed",
        ),
    ),
    Gate(
        "failure_and_injection_paths",
        10,
        (
            "test_p15_call_capability_gate_cannot_be_bypassed_by_payload_text",
            "test_p15_owner_approval_is_signed_bound_expiring_and_one_time",
            "test_p15_dynamic_trust_failure_is_a_stable_policy_error",
        ),
    ),
    Gate("real_demo_and_measurement", 5, demo=True),
    Gate(
        "deployment_trust_key_rotation",
        5,
        unavailable_reason=("trust key owner belum diuji melalui HSM/secret manager target"),
    ),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason="belum ada telemetry policy dari deployment persisten",
    ),
)

P20_GATES = (
    Gate(
        "structured_contract",
        5,
        ("test_p20_external_use_requires_signed_scoped_consent_and_revocation",),
    ),
    Gate(
        "signed_scoped_consent",
        10,
        (
            "test_p20_external_use_requires_signed_scoped_consent_and_revocation",
            "test_p20_dynamic_consent_trust_rotation_revocation_recovery_and_restart",
        ),
    ),
    Gate(
        "purpose_and_provider_gate",
        15,
        ("test_p20_external_use_requires_signed_scoped_consent_and_revocation",),
    ),
    Gate(
        "encryption_at_rest",
        15,
        (
            "test_p20_encrypted_vault_restart_export_and_owner_deletion",
            "test_p20_episodic_payload_is_encrypted_and_survives_restart",
        ),
    ),
    Gate(
        "retention_restart_deletion",
        10,
        (
            "test_p20_encrypted_vault_restart_export_and_owner_deletion",
            "test_p20_retention_purge_and_cross_owner_fail_closed",
        ),
    ),
    Gate(
        "owner_access_and_export",
        10,
        ("test_p20_encrypted_vault_restart_export_and_owner_deletion",),
    ),
    Gate(
        "log_redaction",
        10,
        ("test_p20_structured_logs_redact_messages_nested_fields_and_exceptions",),
    ),
    Gate(
        "canonical_runtime_gate",
        10,
        ("test_p20_runtime_blocks_external_model_and_encrypts_prompt_memory",),
    ),
    Gate(
        "tamper_wrong_key_failure",
        5,
        (
            "test_p20_wrong_key_and_ciphertext_tamper_fail_closed",
            "test_p20_dynamic_consent_trust_failure_is_stable_and_fail_closed",
        ),
    ),
    Gate("real_demo_and_measurement", 5, demo=True),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason=("belum ada key manager, retention scheduler, dan recovery drill live"),
    ),
)

P18_GATES = (
    Gate(
        "structured_contract",
        5,
        ("test_p18_payload_bound_dna_attestation_least_privilege_and_replay",),
    ),
    Gate(
        "persistent_principal_registry",
        10,
        (
            "test_p18_payload_bound_dna_attestation_least_privilege_and_replay",
            "test_p18_expired_wrong_node_revoked_and_injection_fail_closed",
            "test_p18_dynamic_dna_rotation_revocation_and_restart_fail_closed",
        ),
    ),
    Gate(
        "authentication_freshness_replay",
        15,
        (
            "test_p18_payload_bound_dna_attestation_least_privilege_and_replay",
            "test_p18_expired_wrong_node_revoked_and_injection_fail_closed",
            "test_p18_clock_resolver_verifier_payload_and_storage_fail_stably",
        ),
    ),
    Gate(
        "least_privilege_authorization",
        15,
        ("test_p18_payload_bound_dna_attestation_least_privilege_and_replay",),
    ),
    Gate(
        "artifact_integrity",
        10,
        ("test_p21_tampered_external_puzzle_is_never_imported",),
    ),
    Gate(
        "canonical_runtime_dual_gate",
        15,
        (
            "test_p18_canonical_launcher_executes_capability_through_dual_gate",
            "test_p15_runtime_registry_rejects_missing_or_forged_policy_receipt",
        ),
    ),
    Gate(
        "persistent_audit",
        10,
        (
            "test_p18_payload_bound_dna_attestation_least_privilege_and_replay",
            "test_p18_envelope_acl_and_nonce_storage_tamper_fail_closed",
        ),
    ),
    Gate(
        "spoof_expiry_revoke_injection",
        10,
        (
            "test_p18_expired_wrong_node_revoked_and_injection_fail_closed",
            "test_p18_dynamic_dna_rotation_revocation_and_restart_fail_closed",
            "test_p18_rejects_unsupported_storage_schema",
        ),
    ),
    Gate("real_demo_and_measurement", 5, demo=True),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason=(
            "belum ada CA rotation, distributed clock, dan revocation propagation live"
        ),
    ),
)


def _run_tests(junit: Path) -> tuple[dict[str, str], dict[str, Any]]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "packages" / "jaya-core" / "src")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        os.devnull,
        *(str(path) for path in TEST_FILES),
        "-q",
        f"--junitxml={junit}",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    states: dict[str, str] = {}
    if junit.exists():
        for case in ET.parse(junit).iter("testcase"):
            state = "PASSED"
            if case.find("failure") is not None or case.find("error") is not None:
                state = "FAILED"
            elif case.find("skipped") is not None:
                state = "SKIPPED"
            states[case.attrib.get("name", "")] = state
    return states, {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _run_p11_demo(workspace: Path) -> tuple[bool, dict[str, Any]]:
    command = [
        sys.executable,
        str(P11_DEMO),
        "--workspace",
        str(workspace),
        "--purpose",
        "runtime.boot",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"status": "FAILED", "raw_output": completed.stdout}
    passed = (
        completed.returncode == 0
        and payload.get("status") == "VERIFIED_LOCAL"
        and payload.get("migration_preserved_brain_id") is True
        and payload.get("audit_chain_valid") is True
    )
    return passed, {
        "command": command,
        "exit_code": completed.returncode,
        "result": payload,
        "stderr": completed.stderr.strip(),
    }


def _run_p15_demo(workspace: Path) -> tuple[bool, dict[str, Any]]:
    command = [
        sys.executable,
        str(P15_DEMO),
        "--workspace",
        str(workspace),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"status": "FAILED", "raw_output": completed.stdout}
    outcomes = payload.get("outcomes", {})
    passed = (
        completed.returncode == 0
        and payload.get("status") == "VERIFIED_LOCAL"
        and outcomes.get("allow") is True
        and outcomes.get("deny") == "policy_denied"
        and outcomes.get("require_approval") == "approval_required"
        and outcomes.get("approved") is True
        and payload.get("audit_chain_valid") is True
    )
    return passed, {
        "command": command,
        "exit_code": completed.returncode,
        "result": payload,
        "stderr": completed.stderr.strip(),
    }


def _run_p20_demo(workspace: Path) -> tuple[bool, dict[str, Any]]:
    return _run_simple_demo(
        P20_DEMO,
        workspace,
        lambda value: bool(
            value.get("restart_restored")
            and value.get("plaintext_absent")
            and value.get("external_without_consent") == "DENY"
            and value.get("external_with_consent") == "ALLOW"
            and value.get("audit_chain_valid")
        ),
    )


def _run_p18_demo(workspace: Path) -> tuple[bool, dict[str, Any]]:
    return _run_simple_demo(
        P18_DEMO,
        workspace,
        lambda value: bool(
            value.get("allow") == "ALLOW"
            and value.get("replay") == "ZERO_TRUST_REPLAY_DETECTED"
            and value.get("payload_tamper") == "ZERO_TRUST_PAYLOAD_MISMATCH"
            and value.get("audit_chain_valid")
        ),
    )


def _run_simple_demo(
    script: Path,
    workspace: Path,
    validator: Any,
) -> tuple[bool, dict[str, Any]]:
    command = [sys.executable, str(script), "--workspace", str(workspace)]
    completed = subprocess.run(
        command, cwd=ROOT, capture_output=True, text=True, timeout=30, check=False
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"status": "FAILED", "raw_output": completed.stdout}
    passed = (
        completed.returncode == 0
        and payload.get("status") == "VERIFIED_LOCAL"
        and validator(payload)
    )
    return passed, {
        "command": command,
        "exit_code": completed.returncode,
        "result": payload,
        "stderr": completed.stderr.strip(),
    }


def _score_gates(
    gates: tuple[Gate, ...],
    tests: dict[str, str],
    demo_passed: bool,
) -> tuple[int, list[dict[str, Any]]]:
    achieved = 0
    results: list[dict[str, Any]] = []
    for gate in gates:
        if gate.tests:
            evidence = {name: tests.get(name, "NOT_RUN") for name in gate.tests}
            passed = all(value == "PASSED" for value in evidence.values())
        elif gate.demo:
            passed = demo_passed
            evidence = {"demo": "PASSED" if passed else "FAILED"}
        else:
            passed = False
            evidence = {"reason": gate.unavailable_reason}
        if passed:
            achieved += gate.weight
        results.append(
            {
                "gate": gate.name,
                "weight": gate.weight,
                "passed": passed,
                "evidence": evidence,
            }
        )
    return achieved, results


def main() -> int:  # noqa: PLR0914
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="jaya-sovereign-audit-") as directory:
        workspace = Path(directory)
        tests, test_run = _run_tests(workspace / "pytest.xml")
        p11_demo_passed, p11_demo_run = _run_p11_demo(workspace / "p11-demo")
        p15_demo_passed, p15_demo_run = _run_p15_demo(workspace / "p15-demo")
        p20_demo_passed, p20_demo_run = _run_p20_demo(workspace / "p20-demo")
        p18_demo_passed, p18_demo_run = _run_p18_demo(workspace / "p18-demo")

    p11_achieved, p11_gate_results = _score_gates(
        P11_GATES,
        tests,
        p11_demo_passed,
    )
    p15_achieved, p15_gate_results = _score_gates(
        P15_GATES,
        tests,
        p15_demo_passed,
    )
    p20_achieved, p20_gate_results = _score_gates(P20_GATES, tests, p20_demo_passed)
    p18_achieved, p18_gate_results = _score_gates(P18_GATES, tests, p18_demo_passed)
    canonical_statuses = _canonical_statuses()
    p11_status = canonical_statuses["P011"]
    p15_status = canonical_statuses["P015"]
    p20_status = canonical_statuses["P020"]
    p18_status = canonical_statuses["P018"]
    stage_percentage = round(
        (p11_achieved + p15_achieved + p20_achieved + p18_achieved) / 4,
        1,
    )
    maturity_order = {
        "NOT_IMPLEMENTED": 0,
        "PROTOTYPE": 1,
        "IMPLEMENTED_LOCAL": 2,
        "INTEGRATED": 3,
        "VERIFIED": 4,
        "PRODUCTION": 5,
    }
    stage_status = min(
        (p11_status, p15_status, p20_status, p18_status),
        key=lambda value: maturity_order.get(value, -1),
    )
    report = {
        "schema_version": 1,
        "measured_at": datetime.now(UTC).isoformat(),
        "method": "weighted production-readiness gates plus canonical maturity",
        "pillars": {
            "P11 DNA Anchor": {
                "percentage": p11_achieved,
                "status": p11_status,
                "gates": p11_gate_results,
            },
            "P15 Ethical Heart": {
                "percentage": p15_achieved,
                "status": p15_status,
                "gates": p15_gate_results,
            },
            "P20 Sovereign Privacy": {
                "percentage": p20_achieved,
                "status": p20_status,
                "gates": p20_gate_results,
            },
            "P18 Zero Trust": {
                "percentage": p18_achieved,
                "status": p18_status,
                "gates": p18_gate_results,
            },
        },
        "overall": {
            "percentage": stage_percentage,
            "status": stage_status,
        },
        "test_run": test_run,
        "demo_runs": {
            "P11": p11_demo_run,
            "P15": p15_demo_run,
            "P20": p20_demo_run,
            "P18": p18_demo_run,
        },
    }
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print("Fondasi Kedaulatan — executable evidence audit")
    for name, value in report["pillars"].items():
        print(f"{name}: {value['percentage']}% ({value['status']})")
    print(f"OVERALL: {stage_percentage}% ({report['overall']['status']})")
    print(test_run["stdout"])
    return (
        0
        if (
            test_run["exit_code"] == 0
            and p11_demo_passed
            and p15_demo_passed
            and p20_demo_passed
            and p18_demo_passed
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
