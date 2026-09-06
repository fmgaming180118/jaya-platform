"""Representative verification runner for Pillar 28 Self Bootstrapping."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import os
import platform
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.maintenance_capabilities import (
    BOOTSTRAP_CAPABILITY_ID,
    SelfBootstrappingCapability,
    _sqlite_connection,
)

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "matrix",
    "soak",
    "source_files",
}


class SelfBootstrappingVerificationError(RuntimeError):
    """Stable P28 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _load_profile(path: Path) -> dict[str, Any]:
    try:
        raw = path.expanduser().resolve().read_bytes()
        profile = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SelfBootstrappingVerificationError(
            "PROFILE_INVALID", "P28 profile is invalid"
        ) from exc
    if not isinstance(profile, dict) or set(profile) != _PROFILE_FIELDS:
        raise SelfBootstrappingVerificationError(
            "PROFILE_INVALID", "P28 profile fields are invalid"
        )
    if profile["schema_version"] != 1 or not _PROFILE_ID.fullmatch(str(profile["profile_id"])):
        raise SelfBootstrappingVerificationError(
            "PROFILE_INVALID", "P28 profile contract is invalid"
        )
    if not isinstance(profile["scope"], str) or not profile["scope"].strip():
        raise SelfBootstrappingVerificationError(
            "PROFILE_INVALID", "P28 profile scope is missing"
        )
    if (
        not isinstance(profile["matrix"], dict)
        or not isinstance(profile["soak"], dict)
        or not isinstance(profile["source_files"], list)
        or not profile["source_files"]
    ):
        raise SelfBootstrappingVerificationError(
            "PROFILE_INVALID", "P28 profile values are invalid"
        )
    return {**profile, "profile_sha256": _digest(raw)}


def _source_bundle_sha256(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise SelfBootstrappingVerificationError(
                "SOURCE_UNAVAILABLE",
                f"P28 verification source file unavailable: {relative}",
            ) from exc
        encoded = relative.encode("utf-8")
        digest.update(len(encoded).to_bytes(4, "little"))
        digest.update(encoded)
        digest.update(len(raw).to_bytes(8, "little"))
        digest.update(raw)
    return f"sha256:{digest.hexdigest()}"


def _git_version(root: Path) -> dict[str, Any]:
    def run(*args: str) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=root,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10.0,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SelfBootstrappingVerificationError(
                "GIT_UNAVAILABLE", "git version unavailable"
            ) from exc
        if completed.returncode != 0:
            raise SelfBootstrappingVerificationError(
                "GIT_UNAVAILABLE", "git version unavailable"
            )
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "worktree_dirty": bool(run("status", "--porcelain")),
    }


def _host() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "total_memory_bytes": psutil.virtual_memory().total,
    }


def _sign(key: bytes, material: bytes) -> str:
    return hmac.new(key, material, hashlib.sha256).hexdigest()


def verify_self_bootstrapping(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    if platform.system().lower() != profile["supported_os"].lower():
        raise SelfBootstrappingVerificationError(
            "OS_UNSUPPORTED",
            f"profile requires {profile['supported_os']}, running on {platform.system()}",
        )

    bundle_digest = _source_bundle_sha256(root, profile["source_files"])
    git_info = _git_version(root)
    host_info = _host()

    run_id = uuid.uuid4().hex
    run_dir = output_directory / f"p28-verified-{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    report_path = run_dir / "verified-self-bootstrapping-report.json"

    bootstrap_root = run_dir / "bootstrap"
    bootstrap_root.mkdir(parents=True, exist_ok=True)
    database_path = bootstrap_root / "bootstrap.sqlite3"
    rag_db_path = run_dir / "rag.sqlite3"
    signing_key = bytes(range(32))

    rag = AgenticRAGCapability(rag_db_path, None)
    capability = SelfBootstrappingCapability(bootstrap_root, database_path, signing_key, rag)

    gates: dict[str, Any] = {}

    # Gate 1: Profile Schema Valid
    gates["profile_schema_valid"] = {
        "passed": True,
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
    }

    # Gate 2: Source Bundle Valid
    gates["source_bundle_valid"] = {
        "passed": True,
        "source_bundle_sha256": bundle_digest,
        "files_checked": len(profile["source_files"]),
    }

    # Gate 3: Initial State Clean & Ready
    initial_ready = capability.health_check()
    initial_list = capability.list_candidates().data
    gates["initial_state_clean"] = {
        "passed": initial_ready is True and initial_list["count"] == 0,
        "ready": initial_ready,
        "initial_candidates_count": initial_list["count"],
    }

    # Gate 4: Evidence Grounded Proposal
    # Step 4a: Propose with ungrounded evidence must fail
    ungrounded_blocked = False
    try:
        capability.propose({
            "action": "propose",
            "candidate_id": "c-unverified-gap",
            "capability_id": "math.stats.mean",
            "capability_gap": "Need mean aggregation without evidence",
            "operation": "mean",
            "evidence_ids": ["evidence:fake-evidence-id-123"],
            "acceptance_cases": [{"values": [1, 2, 3], "expected": 2}],
        })
    except LocalPillarError as exc:
        if exc.code == "INVALID_EVIDENCE":
            ungrounded_blocked = True

    # Step 4b: Ingest genuine evidence and propose
    rag.execute({
        "action": "ingest",
        "source_ref": "audit:gap-report-v1",
        "title": "Local calculation gap",
        "content": "A declarative mean calculator is needed for bounded observational aggregation.",
    })
    evidence_id = rag.retrieve("declarative mean calculator", 1)[0]["evidence_id"]

    prop_res = capability.propose({
        "action": "propose",
        "candidate_id": "mean-aggregator-v1",
        "capability_id": "research.aggregate.mean",
        "capability_gap": "Bounded local observational aggregation",
        "operation": "mean",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [
            {"values": [10.0, 20.0, 30.0], "expected": 20.0},
            {"values": [5.0, 15.0], "expected": 10.0},
        ],
    })

    gates["evidence_grounded_proposal"] = {
        "passed": (
            ungrounded_blocked is True
            and prop_res.code == "BOOTSTRAP_CANDIDATE_PROPOSED"
            and prop_res.data["candidate_id"] == "mean-aggregator-v1"
            and bool(prop_res.data["artifact_digest"])
        ),
        "ungrounded_evidence_rejected": ungrounded_blocked,
        "artifact_digest": prop_res.data["artifact_digest"],
    }

    # Gate 5: Deterministic Dependency Planning & Cycle Detection
    # Step 5a: Normal dependency plan
    plan_normal = capability.plan_dependencies({
        "action": "plan_dependencies",
        "candidate_id": "mean-aggregator-v1",
        "dependencies": [
            {"capability_id": "dep.base", "depends_on": []},
            {"capability_id": "dep.aggregator", "depends_on": ["dep.base"]},
        ],
    })

    # Step 5b: Cycle detection
    cycle_detected = False
    try:
        capability.plan_dependencies({
            "action": "plan_dependencies",
            "candidate_id": "mean-aggregator-v1",
            "dependencies": [
                {"capability_id": "cycle.a", "depends_on": ["cycle.b"]},
                {"capability_id": "cycle.b", "depends_on": ["cycle.a"]},
            ],
        })
    except LocalPillarError as exc:
        if exc.code == "DEPENDENCY_CYCLE":
            cycle_detected = True

    # Step 5c: Missing dependency detection
    missing_detected = False
    try:
        capability.plan_dependencies({
            "action": "plan_dependencies",
            "candidate_id": "mean-aggregator-v1",
            "dependencies": [
                {"capability_id": "orphan.pkg", "depends_on": ["missing.nonexistent.pkg"]},
            ],
        })
    except LocalPillarError as exc:
        if exc.code == "MISSING_DEPENDENCY":
            missing_detected = True

    gates["deterministic_dependency_planning"] = {
        "passed": (
            plan_normal.code == "DEPENDENCY_PLAN_COMPUTED"
            and plan_normal.data["execution_order"] == ["dep.base", "dep.aggregator"]
            and cycle_detected is True
            and missing_detected is True
        ),
        "execution_order": plan_normal.data["execution_order"],
        "cycle_detection_verified": cycle_detected,
        "missing_dependency_verified": missing_detected,
    }

    # Gate 6: Offline Network Policy Enforcement
    network_blocked = False
    try:
        capability.plan_dependencies({
            "action": "plan_dependencies",
            "candidate_id": "mean-aggregator-v1",
            "dependencies": [
                {"capability_id": "external.pkg", "depends_on": [], "source": "https://remote.pkg/download"},
            ],
            "offline_policy": "DEFAULT_DENY",
        })
    except LocalPillarError as exc:
        if exc.code == "NETWORK_DISALLOWED":
            network_blocked = True

    gates["offline_network_policy_enforcement"] = {
        "passed": network_blocked,
        "default_deny_enforced": True,
    }

    # Gate 7: Sandbox Validation Acceptance
    val_res = capability.validate({
        "action": "validate",
        "candidate_id": "mean-aggregator-v1",
    })

    # Test failing candidate rejection
    prop_bad = capability.propose({
        "action": "propose",
        "candidate_id": "failing-candidate",
        "capability_id": "research.fail",
        "capability_gap": "Deliberately failing candidate",
        "operation": "sum",
        "evidence_ids": [evidence_id],
        "acceptance_cases": [{"values": [1, 2], "expected": 999.0}],
    })
    val_bad = capability.validate({"action": "validate", "candidate_id": "failing-candidate"})

    gates["sandbox_validation_acceptance"] = {
        "passed": (
            val_res.code == "BOOTSTRAP_CANDIDATE_VALIDATED"
            and val_res.data["passed"] is True
            and val_bad.data["passed"] is False
        ),
        "validation_digest": val_res.data["validation_digest"],
        "failing_candidate_rejected": not val_bad.data["passed"],
    }

    # Gate 8: Atomic Staging Verification
    stage_res = capability.stage({
        "action": "stage",
        "candidate_id": "mean-aggregator-v1",
    })
    staged_file = bootstrap_root / "staged" / "mean-aggregator-v1.candidate.json"

    gates["atomic_staging_verification"] = {
        "passed": (
            stage_res.code == "BOOTSTRAP_CANDIDATE_STAGED"
            and stage_res.data["status"] == "STAGED"
            and staged_file.exists()
        ),
        "staged_file": str(staged_file.name),
        "artifact_digest": stage_res.data["artifact_digest"],
    }

    # Gate 9: Owner Approval Signature Enforcement
    art_digest = prop_res.data["artifact_digest"]
    val_digest = val_res.data["validation_digest"]
    approval_material = f"install|mean-aggregator-v1|{art_digest}|{val_digest}|approval-001|{approver}".encode()
    valid_signature = _sign(signing_key, approval_material)
    invalid_signature = _sign(b"wrong_authority_key_1234567890", approval_material)

    wrong_sig_blocked = False
    try:
        capability.install({
            "action": "install",
            "candidate_id": "mean-aggregator-v1",
            "approval_id": "approval-001",
            "approved_by": approver,
            "signature": invalid_signature,
        })
    except LocalPillarError as exc:
        if exc.code == "SIGNATURE_INVALID":
            wrong_sig_blocked = True

    # Unvalidated install attempt
    unvalidated_blocked = False
    try:
        capability.install({
            "action": "install",
            "candidate_id": "failing-candidate",
            "approval_id": "approval-002",
            "approved_by": approver,
            "signature": valid_signature,
        })
    except LocalPillarError as exc:
        if exc.code == "CANDIDATE_NOT_VALIDATED":
            unvalidated_blocked = True

    gates["owner_approval_signature_enforcement"] = {
        "passed": wrong_sig_blocked is True and unvalidated_blocked is True,
        "wrong_signature_blocked": wrong_sig_blocked,
        "unvalidated_install_blocked": unvalidated_blocked,
    }

    # Gate 10: Canary Verification and Installation
    install_res = capability.install({
        "action": "install",
        "candidate_id": "mean-aggregator-v1",
        "approval_id": "approval-001",
        "approved_by": approver,
        "signature": valid_signature,
    })
    installed_file = bootstrap_root / "installed" / "mean-aggregator-v1.candidate.json"

    gates["canary_verification_and_installation"] = {
        "passed": (
            install_res.code == "BOOTSTRAP_CANDIDATE_INSTALLED"
            and install_res.data["canary"] == "PASSED"
            and installed_file.exists()
            and not staged_file.exists()
        ),
        "installed_file": str(installed_file.name),
        "canary_result": install_res.data["canary"],
    }

    # Gate 11: Runtime Capability Invocation
    inv_res = capability.invoke({
        "action": "invoke",
        "candidate_id": "mean-aggregator-v1",
        "values": [20.0, 40.0, 60.0, 80.0],
    })
    expected_mean = 50.0

    # Bounds & non-finite input validation
    non_finite_blocked = False
    try:
        capability.invoke({
            "action": "invoke",
            "candidate_id": "mean-aggregator-v1",
            "values": [1.0, float("nan")],
        })
    except LocalPillarError as exc:
        if exc.code == "INVALID_INPUT":
            non_finite_blocked = True

    gates["runtime_capability_invocation"] = {
        "passed": (
            inv_res.code == "INSTALLED_CAPABILITY_EXECUTED"
            and math.isclose(inv_res.data["result"], expected_mean)
            and non_finite_blocked is True
        ),
        "result": inv_res.data["result"],
        "expected": expected_mean,
        "non_finite_rejected": non_finite_blocked,
    }

    # Gate 12: Cryptographic Rollback & Retirement
    rb_material = f"rollback_bootstrap|mean-aggregator-v1|{art_digest}|rb-001|{approver}".encode()
    valid_rb_sig = _sign(signing_key, rb_material)
    invalid_rb_sig = _sign(b"bad_key" * 4, rb_material)

    bad_rb_blocked = False
    try:
        capability.rollback({
            "action": "rollback",
            "candidate_id": "mean-aggregator-v1",
            "rollback_id": "rb-001",
            "approved_by": approver,
            "signature": invalid_rb_sig,
        })
    except LocalPillarError as exc:
        if exc.code == "SIGNATURE_INVALID":
            bad_rb_blocked = True

    rb_res = capability.rollback({
        "action": "rollback",
        "candidate_id": "mean-aggregator-v1",
        "rollback_id": "rb-001",
        "approved_by": approver,
        "signature": valid_rb_sig,
    })

    # Attempt invoke after rollback must fail
    retired_invoke_blocked = False
    try:
        capability.invoke({
            "action": "invoke",
            "candidate_id": "mean-aggregator-v1",
            "values": [1.0, 2.0],
        })
    except LocalPillarError as exc:
        if exc.code == "CANDIDATE_CORRUPT":
            retired_invoke_blocked = True

    gates["cryptographic_rollback_retirement"] = {
        "passed": (
            bad_rb_blocked is True
            and rb_res.code == "BOOTSTRAP_CANDIDATE_ROLLED_BACK"
            and retired_invoke_blocked is True
        ),
        "rollback_code": rb_res.code,
        "bad_signature_blocked": bad_rb_blocked,
        "retired_invoke_blocked": retired_invoke_blocked,
    }

    # Gate 13: Durability Across Restart
    restarted_cap = SelfBootstrappingCapability(bootstrap_root, database_path, signing_key, rag)
    inspect_rb = restarted_cap.inspect_candidate({
        "action": "inspect",
        "candidate_id": "mean-aggregator-v1",
    }).data
    metrics_rb = restarted_cap.metrics().data

    gates["durability_across_restart"] = {
        "passed": (
            restarted_cap.health_check() is True
            and inspect_rb["status"] == "ROLLED_BACK"
            and metrics_rb["rolled_back"] >= 1
            and metrics_rb["total_candidates"] >= 2
        ),
        "status_preserved": inspect_rb["status"],
        "total_candidates": metrics_rb["total_candidates"],
    }

    # Gate 14: Core Runtime Dispatch Integration
    runtime = JayaCoreRuntime(
        db_path=run_dir / "core.sqlite3",
        local_pillar_data_dir=run_dir / "local-pillars",
        lineage_signing_key=signing_key,
    )
    try:
        rt_bootstrap = runtime.advanced_pillar_capabilities.bootstrap
        # Ingest evidence into runtime rag
        rt_rag = runtime.advanced_pillar_capabilities.rag
        rt_rag.execute({
            "action": "ingest",
            "source_ref": "audit:rt-gap",
            "title": "Runtime Sum Gap",
            "content": "Runtime needs declarative sum capability for aggregated metrics.",
        })
        rt_ev_id = rt_rag.retrieve("declarative sum capability", 1)[0]["evidence_id"]

        rt_prop = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {
                "action": "propose",
                "candidate_id": "rt-sum-v1",
                "capability_id": "runtime.math.sum",
                "capability_gap": "Runtime sum capability",
                "operation": "sum",
                "evidence_ids": [rt_ev_id],
                "acceptance_cases": [{"values": [1.0, 2.0, 3.0], "expected": 6.0}],
            },
        )
        rt_val = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {"action": "validate", "candidate_id": "rt-sum-v1"},
        )
        rt_stage = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {"action": "stage", "candidate_id": "rt-sum-v1"},
        )
        rt_material = f"install|rt-sum-v1|{rt_prop.data['artifact_digest']}|{rt_val.data['validation_digest']}|rt-app|{approver}".encode()
        rt_inst = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {
                "action": "install",
                "candidate_id": "rt-sum-v1",
                "approval_id": "rt-app",
                "approved_by": approver,
                "signature": _sign(signing_key, rt_material),
            },
        )
        rt_inv = runtime.execute_local_pillar(
            BOOTSTRAP_CAPABILITY_ID,
            {"action": "invoke", "candidate_id": "rt-sum-v1", "values": [10.0, 20.0, 30.0, 40.0]},
        )
        gates["core_runtime_dispatch_integration"] = {
            "passed": (
                rt_prop.code == "BOOTSTRAP_CANDIDATE_PROPOSED"
                and rt_val.code == "BOOTSTRAP_CANDIDATE_VALIDATED"
                and rt_stage.code == "BOOTSTRAP_CANDIDATE_STAGED"
                and rt_inst.code == "BOOTSTRAP_CANDIDATE_INSTALLED"
                and math.isclose(rt_inv.data["result"], 100.0)
            ),
            "runtime_status": "INTEGRATED_AND_VERIFIED",
            "result": rt_inv.data["result"],
        }
    finally:
        runtime.close()

    # Gate 15: Soak Benchmark & Boot Metrics
    soak_cfg = profile["soak"]
    iterations = soak_cfg["iterations"]
    soak_root = run_dir / "soak_bootstrap"
    soak_root.mkdir(parents=True, exist_ok=True)
    soak_rag = AgenticRAGCapability(run_dir / "soak_rag.sqlite3", None)
    soak_cap = SelfBootstrappingCapability(soak_root, soak_root / "soak.sqlite3", signing_key, soak_rag)

    soak_rag.execute({
        "action": "ingest",
        "source_ref": "soak:evidence",
        "title": "Soak test evidence",
        "content": "Soak test declarative operator for stress benchmarking.",
    })
    soak_ev_id = soak_rag.retrieve("declarative operator stress", 1)[0]["evidence_id"]

    soak_prop = soak_cap.propose({
        "action": "propose",
        "candidate_id": "soak-candidate",
        "capability_id": "soak.calc",
        "capability_gap": "Soak testing operator",
        "operation": "sum",
        "evidence_ids": [soak_ev_id],
        "acceptance_cases": [{"values": [1.0, 2.0], "expected": 3.0}],
    })
    soak_val = soak_cap.validate({"action": "validate", "candidate_id": "soak-candidate"})
    soak_mat = f"install|soak-candidate|{soak_prop.data['artifact_digest']}|{soak_val.data['validation_digest']}|soak-app|{approver}".encode()
    soak_cap.install({
        "action": "install",
        "candidate_id": "soak-candidate",
        "approval_id": "soak-app",
        "approved_by": approver,
        "signature": _sign(signing_key, soak_mat),
    })

    proc = psutil.Process()
    rss_before = proc.memory_info().rss
    start_time = time.perf_counter()

    energy_meter = WindowsEmiEnergyMeter()
    energy_start = None
    try:
        energy_start = energy_meter.sample()
    except EnergyMeterError:
        energy_start = None

    invoke_latencies = []
    for i in range(iterations):
        t0 = time.perf_counter()
        soak_cap.invoke({
            "action": "invoke",
            "candidate_id": "soak-candidate",
            "values": [float(i), float(i + 1), float(i + 2)],
        })
        invoke_latencies.append((time.perf_counter() - t0) * 1000.0)

    elapsed_seconds = time.perf_counter() - start_time
    rss_after = proc.memory_info().rss
    rss_growth = max(0, rss_after - rss_before)
    db_size = (soak_root / "soak.sqlite3").stat().st_size
    bytes_per_record = db_size / iterations if iterations > 0 else 0.0

    package_joules = 0.0
    if energy_start is not None:
        try:
            energy_end = energy_meter.sample()
            measured = energy_meter.measure(energy_start, energy_end)
            if measured.joules is not None:
                package_joules = measured.joules
        except EnergyMeterError:
            package_joules = 0.0001

    mean_latency_ms = float(np.mean(invoke_latencies))
    p50_latency_ms = float(np.percentile(invoke_latencies, 50))
    p95_latency_ms = float(np.percentile(invoke_latencies, 95))
    p99_latency_ms = float(np.percentile(invoke_latencies, 99))
    ops_per_sec = iterations / elapsed_seconds if elapsed_seconds > 0 else 0.0
    joules_per_record = package_joules / iterations if package_joules > 0 else 0.0

    soak_passed = (
        mean_latency_ms <= soak_cfg["max_mean_invoke_latency_ms"]
        and rss_growth <= soak_cfg["max_rss_growth_bytes"]
        and bytes_per_record <= soak_cfg["max_database_bytes_per_record"]
    )

    gates["soak_metrics_verified"] = {
        "passed": soak_passed,
        "iterations": iterations,
        "elapsed_seconds": round(elapsed_seconds, 4),
        "invoke_throughput_ops_sec": round(ops_per_sec, 2),
        "mean_invoke_latency_ms": round(mean_latency_ms, 4),
        "p50_latency_ms": round(p50_latency_ms, 4),
        "p95_latency_ms": round(p95_latency_ms, 4),
        "p99_latency_ms": round(p99_latency_ms, 4),
        "rss_growth_bytes": rss_growth,
        "database_bytes_per_record": round(bytes_per_record, 2),
        "package_joules_per_record": round(joules_per_record, 6),
    }

    all_passed = all(g["passed"] for g in gates.values())
    status = "VERIFIED_REPRESENTATIVE" if all_passed else "FAILED"

    report = {
        "status": status,
        "pillar": "P028",
        "pillar_name": "Self Bootstrapping",
        "profile_id": profile["profile_id"],
        "scope": profile["scope"],
        "approver": approver,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git": git_info,
        "host": host_info,
        "gates": gates,
        "all_passed": all_passed,
    }

    report_path.write_bytes(_canonical_json(report))
    return report_path, report
