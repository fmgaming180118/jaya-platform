#!/usr/bin/env python3
"""Calculate Stage 1 progress only from executable evidence gates."""

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
TEST_FILE = ROOT / "JAYA_CORE" / "tests" / "test_logical_foundation.py"
DEMO = ROOT / "scripts" / "demo_logical_foundation.py"
DEPLOYMENT_VERIFIER = ROOT / "scripts" / "verify_logical_foundation_deployment.py"
DEMO_INPUT = ROOT / "JAYA_CORE" / "examples" / "logical_foundation_request.json"


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    weight: int
    tests: tuple[str, ...] = ()
    demo: str = ""
    deployment_check: str = ""
    unavailable_reason: str = ""


COMMON_UNFINISHED = (
    Gate(
        "real_process_environment",
        5,
        deployment_check="real_http_process",
    ),
    Gate(
        "deployment_package",
        5,
        ("test_stage1_canonical_launcher_builds_real_runtime",),
    ),
    Gate(
        "rollback_drill",
        5,
        deployment_check="rollback",
    ),
    Gate(
        "live_monitoring",
        5,
        deployment_check="monitoring",
    ),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason=(
            "belum ada bukti telemetry dan SLO dari deployment yang hidup "
            "berkelanjutan"
        ),
    ),
)

PILLARS: dict[str, tuple[Gate, ...]] = {
    "P01 Pure Logic": (
        Gate(
            "validated_contract",
            10,
            ("test_p01_contract_truth_states_and_proof_trace",),
        ),
        Gate(
            "real_implementation",
            10,
            ("test_p01_contract_truth_states_and_proof_trace",),
        ),
        Gate(
            "failure_and_input_security",
            5,
            (
                "test_p01_failure_limits_and_invalid_input",
                "test_p01_api_rejects_unknown_fields_and_conflicting_duplicate",
            ),
        ),
        Gate(
            "solver_timeout_and_theory_bounds",
            5,
            (
                "test_p01_failure_limits_and_invalid_input",
                "test_p01_solver_timeout_is_typed",
            ),
        ),
        Gate(
            "process_memory_enforcement",
            5,
            ("test_p01_process_memory_limit_is_enforced",),
        ),
        Gate(
            "runtime_api_ir_integration",
            15,
            (
                "test_p01_runtime_and_api_vertical_slice",
                "test_p01_p21_pure_logic_is_consumed_through_jayair",
            ),
        ),
        Gate(
            "persistence_and_restart",
            10,
            ("test_p01_persistence_restart_idempotency_and_corruption",),
        ),
        Gate("real_demo", 10, demo="proved"),
        Gate("measured_performance", 5, ("test_p01_solver_performance_is_measured",)),
    )
    + COMMON_UNFINISHED,
    "P21 Lingua Logica": (
        Gate(
            "validated_contract",
            10,
            ("test_p21_lingua_to_jayair_executes_supported_contract",),
        ),
        Gate(
            "real_implementation",
            15,
            ("test_p21_lingua_to_jayair_executes_supported_contract",),
        ),
        Gate(
            "failure_and_security",
            10,
            (
                "test_p21_unsupported_action_fails_closed",
                "test_p21_arithmetic_error_is_typed_and_not_fabricated",
            ),
        ),
        Gate(
            "runtime_ir_integration",
            15,
            (
                "test_p21_lingua_to_jayair_executes_supported_contract",
                "test_p01_p21_pure_logic_is_consumed_through_jayair",
            ),
        ),
        Gate(
            "deterministic_continuity",
            10,
            ("test_p21_deterministic_replay_and_performance",),
        ),
        Gate(
            "real_capability_demo",
            10,
            (
                "test_p21_external_puzzle_is_discovered_and_connected_automatically",
                "test_p21_puzzle_permission_fails_closed",
                "test_p21_puzzle_health_payload_and_timeout_fail_closed",
                "test_p21_tampered_external_puzzle_is_never_imported",
            ),
        ),
        Gate(
            "measured_performance",
            5,
            ("test_p21_deterministic_replay_and_performance",),
        ),
    )
    + COMMON_UNFINISHED,
    "P02 Resource Aware": (
        Gate(
            "truthful_schema_and_provenance",
            10,
            ("test_p02_real_profile_has_provenance_and_no_invented_metrics",),
        ),
        Gate(
            "base_metric_implementation",
            10,
            ("test_p02_real_profile_has_provenance_and_no_invented_metrics",),
        ),
        Gate(
            "accelerator_thermal_power_coverage",
            5,
            ("test_p02_real_profile_has_provenance_and_no_invented_metrics",),
        ),
        Gate(
            "failure_and_unknown_metrics",
            10,
            ("test_p02_unknown_metrics_fail_conservatively",),
        ),
        Gate(
            "runtime_budget_mode_integration",
            10,
            ("test_p02_profile_changes_runtime_budget_and_mode",),
        ),
        Gate(
            "core_resource_consumers_integration",
            5,
            (
                "test_p02_profile_changes_runtime_budget_and_mode",
                "test_stage1_authenticated_metrics_report_real_runtime_state",
            ),
        ),
        Gate(
            "deterministic_policy_continuity",
            10,
            ("test_p02_profile_changes_runtime_budget_and_mode",),
        ),
        Gate("real_device_demo", 10, demo="resource"),
        Gate(
            "measured_performance",
            5,
            (
                "test_p02_profiler_overhead_is_measured",
                "test_p02_slow_hardware_probe_is_cached_with_age",
            ),
        ),
    )
    + COMMON_UNFINISHED,
    "P05 Logical Homeostasis": (
        Gate(
            "validated_policy",
            10,
            ("test_p05_state_transitions_hysteresis_and_restart",),
        ),
        Gate(
            "real_implementation",
            15,
            ("test_p05_state_transitions_hysteresis_and_restart",),
        ),
        Gate("failure_and_safe_stop", 10, ("test_p05_runtime_safe_stop_blocks_logic",)),
        Gate(
            "runtime_gate_integration", 15, ("test_p05_runtime_safe_stop_blocks_logic",)
        ),
        Gate(
            "persistence_and_restart",
            7,
            ("test_p05_state_transitions_hysteresis_and_restart",),
        ),
        Gate(
            "corrupt_state_recovery",
            3,
            ("test_p05_corrupt_ledger_fails_closed_and_recovers_after_health",),
        ),
        Gate("degrade_recover_demo", 10, demo="homeostasis"),
        Gate(
            "measured_performance",
            5,
            (
                "test_p02_profiler_overhead_is_measured",
                "test_p02_slow_hardware_probe_is_cached_with_age",
            ),
        ),
    )
    + COMMON_UNFINISHED,
}


def _run_tests(junit_path: Path) -> tuple[dict[str, str], dict[str, Any]]:
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
        f"--junitxml={junit_path}",
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
    if junit_path.exists():
        for case in ET.parse(junit_path).iter("testcase"):
            name = case.attrib.get("name", "")
            state = "PASSED"
            if case.find("failure") is not None or case.find("error") is not None:
                state = "FAILED"
            elif case.find("skipped") is not None:
                state = "SKIPPED"
            states[name] = state
    metadata = {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }
    return states, metadata


def _run_demo(
    temp_dir: Path, memory_mb: int, request_id: str
) -> tuple[int, dict[str, Any]]:
    input_payload = json.loads(DEMO_INPUT.read_text(encoding="utf-8"))
    input_payload["request_id"] = request_id
    input_path = temp_dir / f"{request_id}.json"
    input_path.write_text(json.dumps(input_payload), encoding="utf-8")
    command = [
        sys.executable,
        str(DEMO),
        "--input",
        str(input_path),
        "--database",
        str(temp_dir / "demo.db"),
        "--node-id",
        "audit-node",
        "--available-memory-mb",
        str(memory_mb),
        "--thermal-celsius",
        "45",
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
        payload = {"raw_output": completed.stdout, "stderr": completed.stderr}
    return completed.returncode, payload


def _demo_states(temp_dir: Path) -> dict[str, bool]:
    degraded_code, degraded = _run_demo(temp_dir, 300, "audit-degraded")
    recovered_code, recovered = _run_demo(temp_dir, 1_024, "audit-recovered")
    proof = recovered.get("proof", {})
    resource = recovered.get("resource_profile", {})
    return {
        "proved": recovered_code == 0 and proof.get("status") == "PROVED",
        "resource": recovered_code == 0
        and resource.get("available_memory_mb") == 1_024
        and bool(resource.get("sources")),
        "homeostasis": degraded_code == 0
        and recovered_code == 0
        and degraded.get("homeostasis_state") == "DEGRADED"
        and recovered.get("homeostasis_state") == "NORMAL"
        and recovered.get("homeostasis_transitions", 0) >= 2,
    }


def _run_deployment_verification() -> tuple[dict[str, bool], dict[str, Any]]:
    command = [sys.executable, str(DEPLOYMENT_VERIFIER)]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError:
        payload = {"status": "FAILED", "raw_output": completed.stdout}
    checks = payload.get("checks", {}) if isinstance(payload, dict) else {}
    states = {
        name: value == "PASS" for name, value in checks.items() if isinstance(name, str)
    }
    return states, {
        "command": command,
        "exit_code": completed.returncode,
        "status": payload.get("status"),
        "checks": checks,
        "stderr": completed.stderr.strip(),
    }


def _status(percent: int, gates: list[dict[str, Any]]) -> str:
    if percent == 100:
        return "PRODUCTION"
    if percent >= 90:
        return "VERIFIED"
    integration_gates = [item for item in gates if "integration" in item["gate"]]
    integration_passed = bool(integration_gates) and all(
        item["passed"] for item in integration_gates
    )
    demo_passed = any("demo" in item["gate"] and item["passed"] for item in gates)
    if percent >= 60 and integration_passed and demo_passed:
        return "INTEGRATED"
    if percent >= 35:
        return "IMPLEMENTED_LOCAL"
    if percent > 0:
        return "PROTOTYPE"
    return "NOT_IMPLEMENTED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="jaya-logic-audit-") as directory:
        temp_dir = Path(directory)
        tests, test_run = _run_tests(temp_dir / "pytest.xml")
        demos = _demo_states(temp_dir)
        deployment, deployment_run = _run_deployment_verification()

    report: dict[str, Any] = {
        "schema_version": 1,
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "method": "weighted executable evidence gates",
        "test_run": test_run,
        "demo_results": demos,
        "deployment_run": deployment_run,
        "pillars": {},
    }
    percentages: list[int] = []
    for pillar, gates in PILLARS.items():
        achieved = 0
        gate_results = []
        for gate in gates:
            passed = False
            evidence: Any
            if gate.tests:
                observed = {name: tests.get(name, "NOT_RUN") for name in gate.tests}
                passed = all(state == "PASSED" for state in observed.values())
                evidence = observed
            elif gate.demo:
                passed = demos.get(gate.demo, False)
                evidence = {gate.demo: "PASSED" if passed else "FAILED"}
            elif gate.deployment_check:
                passed = deployment.get(gate.deployment_check, False)
                evidence = {gate.deployment_check: "PASSED" if passed else "FAILED"}
            else:
                evidence = {"reason": gate.unavailable_reason}
            if passed:
                achieved += gate.weight
            gate_results.append(
                {
                    "gate": gate.name,
                    "weight": gate.weight,
                    "passed": passed,
                    "evidence": evidence,
                }
            )
        percentages.append(achieved)
        report["pillars"][pillar] = {
            "percentage": achieved,
            "status": _status(achieved, gate_results),
            "gates": gate_results,
        }
    overall = round(sum(percentages) / len(percentages))
    status_order = {
        "NOT_IMPLEMENTED": 0,
        "PROTOTYPE": 1,
        "IMPLEMENTED_LOCAL": 2,
        "INTEGRATED": 3,
        "VERIFIED": 4,
        "PRODUCTION": 5,
    }
    overall_status = min(
        (value["status"] for value in report["pillars"].values()),
        key=status_order.__getitem__,
    )
    report["overall"] = {"percentage": overall, "status": overall_status}

    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    print("Pondasi Logika — executable evidence audit")
    for pillar, value in report["pillars"].items():
        print(f"{pillar}: {value['percentage']}% ({value['status']})")
    print(f"OVERALL: {overall}% ({overall_status})")
    print(test_run["stdout"])
    return (
        0
        if test_run["exit_code"] == 0
        and all(demos.values())
        and deployment_run["exit_code"] == 0
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
