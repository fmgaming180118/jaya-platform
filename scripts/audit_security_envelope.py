#!/usr/bin/env python3
"""Measure Tahap 3 Selubung Keamanan from executable evidence."""

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
TEST_FILES = (
    ROOT / "JAYA_CORE" / "tests" / "test_cryptographic_skin.py",
    ROOT / "JAYA_CORE" / "tests" / "test_hardware_binding.py",
    ROOT / "JAYA_CORE" / "tests" / "test_quantum_security.py",
    ROOT / "JAYA_CORE" / "tests" / "test_immune_system.py",
    ROOT / "JAYA_CORE" / "tests" / "test_security_capsule.py",
)
P13_DEMO = ROOT / "scripts" / "demo_cryptographic_skin.py"
P14_DEMO = ROOT / "scripts" / "demo_hardware_binding.py"
P12_DEMO = ROOT / "scripts" / "demo_immune_system.py"
P16_DEMO = ROOT / "scripts" / "demo_quantum_security.py"


@dataclass(frozen=True, slots=True)
class Gate:
    name: str
    weight: int
    tests: tuple[str, ...] = ()
    demo: bool = False
    unavailable_reason: str = ""


P13_GATES = (
    Gate(
        "versioned_contract_and_maintained_primitives",
        10,
        ("test_p13_aead_dna_envelope_roundtrip_and_plaintext_absence",),
    ),
    Gate(
        "aead_and_dna_authenticity",
        15,
        (
            "test_p13_aead_dna_envelope_roundtrip_and_plaintext_absence",
            "test_p13_metadata_ciphertext_nonce_and_suite_tamper_fail_closed",
        ),
    ),
    Gate(
        "persistent_key_rotation_revocation_and_nonce_registry",
        15,
        (
            "test_p13_restart_rotation_continuity_and_revocation",
            "test_p13_persistent_nonce_registry_rejects_reuse",
        ),
    ),
    Gate(
        "bounded_failure_paths",
        10,
        (
            "test_p13_wrong_secret_signature_and_unknown_field_fail_closed",
            "test_p13_expiry_payload_bound_and_invalid_clock_fail_closed",
            "test_p13_metadata_ciphertext_nonce_and_suite_tamper_fail_closed",
        ),
    ),
    Gate(
        "canonical_runtime_and_launcher_wiring",
        15,
        (
            "test_p13_runtime_vertical_slice_and_unconfigured_failure",
            "test_p13_canonical_launcher_wires_validated_secret_and_identity",
        ),
    ),
    Gate(
        "restart_and_tamper_evident_audit",
        10,
        (
            "test_p13_restart_rotation_continuity_and_revocation",
            "test_p13_corrupt_audit_blocks_restart",
        ),
    ),
    Gate(
        "real_demo_and_measurement",
        5,
        ("test_p13_envelope_latency_and_size_are_measured",),
        demo=True,
    ),
    Gate(
        "all_core_boundaries_migrated",
        10,
        (
            "test_one_file_capsule_covers_all_core_boundaries",
            "test_secure_sqlite_backup_capsule_restores_real_database",
            "test_sealed_puzzle_executes_only_after_p13_p16_verification",
            "test_mesh_sync_uses_authenticated_encrypted_capsule",
        ),
    ),
    Gate(
        "external_kms_and_anti_rollback",
        5,
        unavailable_reason=("belum diuji dengan OS keystore/HSM dan monotonic counter"),
    ),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason=(
            "belum ada telemetry dan recovery drill deployment persisten"
        ),
    ),
)

P14_GATES = (
    Gate(
        "versioned_node_binding_contract",
        5,
        ("test_p14_brain_node_instance_are_separate_and_restart_authorizes",),
    ),
    Gate(
        "real_os_machine_root_provider",
        5,
        ("test_p14_windows_dpapi_production_provider_roundtrip",),
    ),
    Gate(
        "brain_node_instance_separation",
        10,
        ("test_p14_brain_node_instance_are_separate_and_restart_authorizes",),
    ),
    Gate(
        "persistent_authorized_boot",
        10,
        (
            "test_p14_brain_node_instance_are_separate_and_restart_authorizes",
            "test_p14_canonical_launcher_requires_enrolled_current_node",
        ),
    ),
    Gate(
        "clone_wrong_node_wrong_root_rejection",
        10,
        ("test_p14_cloned_database_wrong_node_and_wrong_root_fail_closed",),
    ),
    Gate(
        "owner_migration_and_revocation",
        15,
        ("test_p14_owner_authorized_migration_preserves_brain_and_revokes_source",),
    ),
    Gate(
        "p13_hardware_bound_key_context",
        15,
        (
            "test_p14_hardware_context_binds_p13_data_key",
            "test_p14_canonical_launcher_requires_enrolled_current_node",
        ),
    ),
    Gate(
        "tamper_audit_and_unavailable_provider",
        10,
        (
            "test_p14_tamper_and_audit_corruption_fail_closed",
            "test_p14_unavailable_provider_is_explicit",
        ),
    ),
    Gate("real_demo_and_measurement", 5, demo=True),
    Gate(
        "hardware_attestation_tpm_secure_enclave",
        10,
        unavailable_reason=(
            "DPAPI aktif tetapi TPM/Secure Enclave attestation belum tersedia"
        ),
    ),
    Gate(
        "sustained_production_observation",
        5,
        unavailable_reason="belum ada migration/recovery drill deployment persisten",
    ),
)

P16_GATES = (
    Gate(
        "versioned_algorithm_agility_contract",
        10,
        (
            "test_p16_hybrid_contract_requires_both_signatures_and_payload_binding",
            "test_p16_unknown_fields_policy_version_and_suite_are_rejected",
        ),
    ),
    Gate(
        "asset_lifetime_and_threat_horizon_policy",
        10,
        ("test_p16_policy_rejects_downgrade_and_expired_classical_horizon",),
    ),
    Gate(
        "downgrade_protection",
        15,
        ("test_p16_policy_rejects_downgrade_and_expired_classical_horizon",),
    ),
    Gate(
        "provider_unavailable_fails_closed",
        10,
        ("test_p16_missing_production_provider_is_blocked_external_not_fallback",),
    ),
    Gate(
        "classical_fallback_truthful_label",
        5,
        ("test_p16_classical_compatibility_is_never_labeled_quantum_resistant",),
    ),
    Gate(
        "real_ml_dsa_provider",
        20,
        ("test_p16_real_ml_dsa_provider_sign_verify_and_measurement",),
    ),
    Gate(
        "persistent_key_rotation",
        10,
        ("test_p16_persistent_rotation_restart_and_revocation",),
    ),
    Gate(
        "p13_capsule_and_puzzle_integration",
        10,
        (
            "test_p16_canonical_launcher_and_runtime_capsule_wiring",
            "test_sealed_puzzle_executes_only_after_p13_p16_verification",
        ),
    ),
    Gate(
        "real_benchmark_and_demo",
        5,
        ("test_p16_real_ml_dsa_provider_sign_verify_and_measurement",),
        demo=True,
    ),
    Gate(
        "independent_security_review",
        5,
        unavailable_reason=(
            "security review independen belum dilakukan"
        ),
    ),
)

P12_GATES = (
    Gate(
        "versioned_contract_and_launcher_configuration",
        5,
        ("test_p12_config_and_canonical_launcher_wiring",),
    ),
    Gate(
        "dna_attested_integrity_registry",
        10,
        ("test_p12_integrity_quarantine_restart_and_verified_recovery",),
    ),
    Gate(
        "real_integrity_detection",
        15,
        (
            "test_p12_integrity_quarantine_restart_and_verified_recovery",
            "test_p12_path_escape_and_audit_tamper_fail_closed",
        ),
    ),
    Gate(
        "p13_encrypted_bounded_quarantine",
        15,
        (
            "test_p12_integrity_quarantine_restart_and_verified_recovery",
            "test_p12_quarantine_limit_still_enters_persistent_safe_stop",
        ),
    ),
    Gate(
        "runtime_safe_stop_wiring",
        10,
        ("test_p12_runtime_readiness_tracks_persistent_incident",),
    ),
    Gate(
        "persistent_dependency_circuit_breaker",
        10,
        (
            "test_p12_dependency_circuit_breaker_persists_and_requires_health_probe",
        ),
    ),
    Gate(
        "restart_and_verified_recovery",
        10,
        (
            "test_p12_integrity_quarantine_restart_and_verified_recovery",
            "test_p12_dependency_circuit_breaker_persists_and_requires_health_probe",
        ),
    ),
    Gate(
        "fail_closed_path_resource_and_audit_errors",
        5,
        (
            "test_p12_quarantine_limit_still_enters_persistent_safe_stop",
            "test_p12_path_escape_and_audit_tamper_fail_closed",
        ),
    ),
    Gate("real_demo_and_measurement", 5, demo=True),
    Gate(
        "live_policy_feed_and_detection_telemetry",
        5,
        (
            "test_p12_dependency_circuit_breaker_persists_and_requires_health_probe",
            "test_p12_runtime_readiness_tracks_persistent_incident",
        ),
    ),
    Gate(
        "sustained_production_observation",
        10,
        unavailable_reason="belum ada recovery drill dan observasi produksi persisten",
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
            name = case.attrib.get("name", "")
            states[name] = state
            base_name = name.split("[", 1)[0]
            existing = states.get(base_name)
            priority = {"PASSED": 0, "SKIPPED": 1, "FAILED": 2}
            if existing is None or priority[state] > priority[existing]:
                states[base_name] = state
    return states, {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def _run_demo(
    script: Path,
    workspace: Path,
    required_true: tuple[str, ...],
) -> tuple[bool, dict[str, Any]]:
    command = [sys.executable, str(script), "--workspace", str(workspace)]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    try:
        json_start = completed.stdout.find("{")
        payload = json.loads(completed.stdout[json_start:])
    except json.JSONDecodeError:
        payload = {}
    passed = completed.returncode == 0 and all(
        payload.get(key) is True for key in required_true
    )
    return passed, {
        "command": command,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
        "payload": payload,
    }


def _status(score: int) -> str:
    if score >= 95:
        return "VERIFIED"
    if score >= 85:
        return "INTEGRATED"
    if score >= 70:
        return "IMPLEMENTED_LOCAL"
    if score >= 40:
        return "PROTOTYPE"
    return "NOT_IMPLEMENTED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="jaya-security-envelope-audit-") as raw:
        workspace = Path(raw)
        states, test_run = _run_tests(workspace / "pytest.xml")
        p13_demo_passed, p13_demo_run = _run_demo(
            P13_DEMO,
            workspace / "p13-demo",
            (
                "restart_restored",
                "plaintext_absent",
                "rotation_continuity",
                "old_key_revoked",
                "audit_chain_valid",
            ),
        )
        p14_demo_passed, p14_demo_run = _run_demo(
            P14_DEMO,
            workspace / "p14-demo",
            (
                "provider_available",
                "brain_id_stable",
                "instance_rotated",
                "restart_restored",
                "plaintext_absent",
                "p13_hardware_bound",
                "clone_rejected",
                "audit_chain_valid",
            ),
        )
        p12_demo_passed, p12_demo_run = _run_demo(
            P12_DEMO,
            workspace / "p12-demo",
            (
                "healthy_scan",
                "quarantined",
                "plaintext_absent",
                "safe_stop",
                "restart_safe_stop",
                "verified_recovery",
                "audit_chain_valid",
            ),
        )
        p16_demo_passed, p16_demo_run = _run_demo(
            P16_DEMO,
            workspace / "p16-demo",
            (
                "ml_dsa_ready",
                "hybrid_verified",
                "capsule_restored",
                "plaintext_absent",
                "rotation_continuity",
                "restart_restored",
                "revoked_rejected",
            ),
        )

        def score_gates(
            definitions: tuple[Gate, ...], demo_passed: bool
        ) -> tuple[int, list[dict[str, object]]]:
            score = 0
            gates: list[dict[str, object]] = []
            for gate in definitions:
                tests_passed = bool(gate.tests) and all(
                    states.get(test) == "PASSED" for test in gate.tests
                )
                if gate.unavailable_reason:
                    passed = False
                elif gate.demo:
                    passed = tests_passed if gate.tests else demo_passed
                    passed = passed and demo_passed
                else:
                    passed = tests_passed
                if passed:
                    score += gate.weight
                gates.append(
                    {
                        "name": gate.name,
                        "weight": gate.weight,
                        "passed": passed,
                        "tests": list(gate.tests),
                        "unavailable_reason": gate.unavailable_reason or None,
                    }
                )
            return score, gates

        p13_score, p13_gates = score_gates(P13_GATES, p13_demo_passed)
        p14_score, p14_gates = score_gates(P14_GATES, p14_demo_passed)
        p16_score, p16_gates = score_gates(P16_GATES, p16_demo_passed)
        p12_score, p12_gates = score_gates(P12_GATES, p12_demo_passed)
        stage_score = round(
            (p13_score + p14_score + p16_score + p12_score) / 4, 2
        )
        stage_status = _status(round(stage_score))
        report = {
            "schema_version": 1,
            "stage": "3 - Selubung Keamanan",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pillars": {
                "P13 Cryptographic Skin": {
                    "score": p13_score,
                    "status": _status(p13_score),
                    "gates": p13_gates,
                },
                "P14 Hardware Locked": {
                    "score": p14_score,
                    "status": _status(p14_score),
                    "gates": p14_gates,
                },
                "P16 Quantum Resistant": {
                    "score": p16_score,
                    "status": _status(p16_score),
                    "gates": p16_gates,
                },
                "P12 Immune System": {
                    "score": p12_score,
                    "status": _status(p12_score),
                    "gates": p12_gates,
                },
            },
            "stage_score": stage_score,
            "stage_status": stage_status,
            "test_run": test_run,
            "demo_runs": {
                "P13": p13_demo_run,
                "P14": p14_demo_run,
                "P12": p12_demo_run,
                "P16": p16_demo_run,
            },
        }
        if args.json_output:
            destination = args.json_output.resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        print("Tahap 3 - Selubung Keamanan - executable evidence audit")
        print(f"P13 Cryptographic Skin: {p13_score}% ({_status(p13_score)})")
        print(f"P14 Hardware Locked: {p14_score}% ({_status(p14_score)})")
        print(f"P16 Quantum Resistant: {p16_score}% ({_status(p16_score)})")
        print(f"P12 Immune System: {p12_score}% ({_status(p12_score)})")
        print(f"TAHAP 3: {report['stage_score']}% ({stage_status})")
        print(test_run["stdout"])
        for demo_run in (
            p13_demo_run,
            p14_demo_run,
            p12_demo_run,
            p16_demo_run,
        ):
            if demo_run["stdout"]:
                print(demo_run["stdout"])
        return (
            0
            if (
                test_run["exit_code"] == 0
                and p13_demo_passed
                and p14_demo_passed
                and p12_demo_passed
                and p16_demo_passed
                and p13_score == 90
                and p14_score == 85
                and p16_score == 95
                and p12_score == 90
            )
            else 1
        )


if __name__ == "__main__":
    raise SystemExit(main())
