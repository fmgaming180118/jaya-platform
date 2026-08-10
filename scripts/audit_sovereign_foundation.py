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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TEST_FILE = ROOT / "JAYA_CORE" / "tests" / "test_sovereign_foundation.py"
P11_DEMO = ROOT / "scripts" / "demo_sovereign_foundation.py"
P15_DEMO = ROOT / "scripts" / "demo_ethical_heart.py"


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    weight: int
    tests: tuple[str, ...] = ()
    demo: bool = False
    unavailable_reason: str = ""


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
        ("test_p15_owner_approval_is_signed_bound_expiring_and_one_time",),
    ),
    Gate(
        "dna_signed_decision_receipts",
        10,
        (
            "test_p15_runtime_signs_receipts_with_dna_and_preserves_them_on_restart",
        ),
    ),
    Gate(
        "restart_and_tamper_detection",
        10,
        (
            "test_p15_runtime_signs_receipts_with_dna_and_preserves_them_on_restart",
            "test_p15_policy_version_conflict_and_receipt_tamper_fail_closed",
        ),
    ),
    Gate(
        "failure_and_injection_paths",
        10,
        (
            "test_p15_call_capability_gate_cannot_be_bypassed_by_payload_text",
            "test_p15_owner_approval_is_signed_bound_expiring_and_one_time",
        ),
    ),
    Gate("real_demo_and_measurement", 5, demo=True),
    Gate(
        "deployment_trust_key_rotation",
        5,
        unavailable_reason=(
            "trust key owner belum diuji melalui HSM/secret manager target"
        ),
    ),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason="belum ada telemetry policy dari deployment persisten",
    ),
)


def _run_tests(junit: Path) -> tuple[dict[str, str], dict[str, Any]]:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "JAYA_CORE")
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        os.devnull,
        str(TEST_FILE),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="jaya-sovereign-audit-") as directory:
        workspace = Path(directory)
        tests, test_run = _run_tests(workspace / "pytest.xml")
        p11_demo_passed, p11_demo_run = _run_p11_demo(workspace / "p11-demo")
        p15_demo_passed, p15_demo_run = _run_p15_demo(workspace / "p15-demo")

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
    p11_status = "INTEGRATED" if p11_achieved >= 80 else "IMPLEMENTED_LOCAL"
    p15_status = "INTEGRATED" if p15_achieved >= 80 else "IMPLEMENTED_LOCAL"
    stage_percentage = round((p11_achieved + p15_achieved) / 4)
    report = {
        "schema_version": 1,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "method": "weighted executable evidence gates",
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
                "percentage": 0,
                "status": "NOT_IMPLEMENTED",
            },
            "P18 Zero Trust": {"percentage": 0, "status": "NOT_IMPLEMENTED"},
        },
        "overall": {"percentage": stage_percentage, "status": "IN_PROGRESS"},
        "test_run": test_run,
        "demo_runs": {"P11": p11_demo_run, "P15": p15_demo_run},
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
    print(f"OVERALL: {stage_percentage}% (IN_PROGRESS)")
    print(test_run["stdout"])
    return 0 if (
        test_run["exit_code"] == 0
        and p11_demo_passed
        and p15_demo_passed
    ) else 1


if __name__ == "__main__":
    raise SystemExit(main())
