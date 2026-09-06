"""Representative verification runner for Pillar 10 bounded affective control."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import psutil

from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.local_capabilities import LocalPillarError
from jaya_core.pillars.regulation_capabilities import AFFECTIVE_CAPABILITY_ID

_PROFILE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_PROFILE_FIELDS = {
    "schema_version",
    "profile_id",
    "scope",
    "supported_os",
    "expected_baseline",
    "matrix",
    "soak",
    "source_files",
}
_STATE_FIELDS = ("urgency", "caution", "patience", "escalation")


class AffectiveVerificationError(RuntimeError):
    """Stable P10 verification failure carrying the failed boundary."""

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
        raise AffectiveVerificationError("PROFILE_INVALID", "P10 profile is invalid") from exc
    if not isinstance(profile, dict) or set(profile) != _PROFILE_FIELDS:
        raise AffectiveVerificationError("PROFILE_INVALID", "P10 profile fields are invalid")
    if profile["schema_version"] != 1 or not _PROFILE_ID.fullmatch(
        str(profile["profile_id"])
    ):
        raise AffectiveVerificationError("PROFILE_INVALID", "P10 profile contract is invalid")
    if not isinstance(profile["scope"], str) or not profile["scope"].strip():
        raise AffectiveVerificationError("PROFILE_INVALID", "P10 profile scope is missing")
    baseline = profile["expected_baseline"]
    matrix = profile["matrix"]
    soak = profile["soak"]
    if (
        not isinstance(baseline, dict)
        or tuple(baseline) != _STATE_FIELDS
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not 0 <= float(value) <= 1
            for value in baseline.values()
        )
        or not isinstance(matrix, dict)
        or not isinstance(soak, dict)
        or not isinstance(profile["source_files"], list)
        or not profile["source_files"]
    ):
        raise AffectiveVerificationError("PROFILE_INVALID", "P10 profile values are invalid")
    return {**profile, "profile_sha256": _digest(raw)}


def _source_bundle_sha256(root: Path, paths: list[str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(paths):
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
            raw = path.read_bytes()
        except (OSError, ValueError) as exc:
            raise AffectiveVerificationError(
                "SOURCE_UNAVAILABLE", "P10 verification source bundle is unavailable"
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
            raise AffectiveVerificationError("GIT_UNAVAILABLE", "git version unavailable") from exc
        if completed.returncode != 0:
            raise AffectiveVerificationError("GIT_UNAVAILABLE", "git version unavailable")
        return completed.stdout.strip()

    return {
        "commit": run("rev-parse", "HEAD"),
        "worktree_dirty": bool(run("status", "--porcelain")),
    }


def _host() -> dict[str, Any]:
    return {
        "os": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "physical_cores": psutil.cpu_count(logical=False),
        "logical_cores": psutil.cpu_count(logical=True),
        "ram_bytes": psutil.virtual_memory().total,
        "python": sys.version.split()[0],
        "numpy": np.__version__,
        "psutil": psutil.__version__,
    }


def _runtime(root: Path) -> JayaCoreRuntime:
    return JayaCoreRuntime(
        db_path=root / "core.sqlite3",
        local_pillar_data_dir=root / "pillars",
        node_id="p10-verification-node",
    )


def _expect_error(
    runtime: JayaCoreRuntime, request: dict[str, Any], code: str
) -> dict[str, Any]:
    try:
        runtime.execute_local_pillar(AFFECTIVE_CAPABILITY_ID, request)
    except LocalPillarError as exc:
        if exc.code != code:
            raise AffectiveVerificationError(
                "FAULT_DRILL_FAILED", "P10 returned an unexpected failure code"
            ) from exc
        return exc.to_dict()
    raise AffectiveVerificationError("FAULT_DRILL_FAILED", "P10 accepted invalid input")


def _matrix(runtime: JayaCoreRuntime, profile: dict[str, Any]) -> dict[str, Any]:
    matrix = profile["matrix"]
    expected_baseline = {
        key: float(value) for key, value in profile["expected_baseline"].items()
    }
    maximum_delta = float(matrix["max_delta_per_signal"])
    tolerance = float(matrix["numeric_tolerance"])
    cases = 0
    mismatches = 0
    invariant_failures = 0
    observed_sources: set[str] = set()
    observed_dimensions: set[str] = set()
    observed_deltas: set[float] = set()
    for source in matrix["sources"]:
        for dimension in matrix["dimensions"]:
            for raw_delta in matrix["delta_values"]:
                reset = runtime.execute_local_pillar(
                    AFFECTIVE_CAPABILITY_ID, {"action": "reset"}
                )
                baseline = reset.data["state"]
                delta = float(raw_delta)
                request: dict[str, Any] = {
                    "action": "apply",
                    "source": source,
                    "signal_id": f"matrix-{cases}",
                    f"{dimension}_delta": delta,
                }
                if source == "USER_CONFIRMED":
                    request["user_state_confirmed"] = True
                result = runtime.execute_local_pillar(AFFECTIVE_CAPABILITY_ID, request)
                state = result.data["state"]
                decision = result.data["decision"]
                clipped = max(-maximum_delta, min(maximum_delta, delta))
                expected = max(0.0, min(1.0, expected_baseline[dimension] + clipped))
                if dimension == "caution":
                    expected = max(expected_baseline["caution"], expected)
                if any(abs(float(baseline[key]) - expected_baseline[key]) > tolerance for key in _STATE_FIELDS):
                    mismatches += 1
                if abs(float(state[dimension]) - expected) > tolerance:
                    mismatches += 1
                if (
                    any(not 0.0 <= float(state[key]) <= 1.0 for key in _STATE_FIELDS)
                    or float(state["caution"]) < expected_baseline["caution"] - tolerance
                    or decision["authority_changed"] is not False
                    or decision["safety_relaxed"] is not False
                    or decision["factual_content_changed"] is not False
                ):
                    invariant_failures += 1
                cases += 1
                observed_sources.add(str(source))
                observed_dimensions.add(str(dimension))
                observed_deltas.add(delta)
    return {
        "cases": cases,
        "mismatches": mismatches,
        "invariant_failures": invariant_failures,
        "sources": sorted(observed_sources),
        "dimensions": sorted(observed_dimensions),
        "delta_values": sorted(observed_deltas),
    }


def _soak(runtime: JayaCoreRuntime, config: dict[str, Any]) -> dict[str, Any]:
    iterations = int(config["iterations"])
    if not 10_000 <= iterations <= 1_000_000:
        raise AffectiveVerificationError("PROFILE_INVALID", "P10 soak iterations invalid")
    meter = WindowsEmiEnergyMeter()
    try:
        energy_start = meter.sample()
    except EnergyMeterError as exc:
        raise AffectiveVerificationError("ENERGY_REQUIRED", "P10 energy counter unavailable") from exc
    process = psutil.Process()
    rss_before = process.memory_info().rss
    started = time.perf_counter()
    errors = 0
    invariant_failures = 0
    for index in range(iterations):
        try:
            result = runtime.execute_local_pillar(
                AFFECTIVE_CAPABILITY_ID,
                {
                    "action": "apply",
                    "source": "TASK",
                    "signal_id": f"soak-{index}",
                },
            )
            decision = result.data["decision"]
            if any(
                decision[field] is not False
                for field in ("authority_changed", "safety_relaxed", "factual_content_changed")
            ):
                invariant_failures += 1
        except LocalPillarError:
            errors += 1
    elapsed = time.perf_counter() - started
    rss_after = process.memory_info().rss
    try:
        energy = meter.measure(energy_start, meter.sample())
    except EnergyMeterError as exc:
        raise AffectiveVerificationError("ENERGY_REQUIRED", "P10 energy measurement failed") from exc
    return {
        "iterations": iterations,
        "errors": errors,
        "invariant_failures": invariant_failures,
        "elapsed_seconds": elapsed,
        "mean_latency_ms": elapsed * 1_000.0 / iterations,
        "operations_per_second": iterations / elapsed,
        "rss_before_bytes": rss_before,
        "rss_after_bytes": rss_after,
        "rss_growth_bytes": max(0, rss_after - rss_before),
        "energy": {
            **energy.to_dict(),
            "joules_per_operation": energy.joules / iterations,
        },
    }


def _gate(name: str, passed: bool, actual: Any, limit: Any) -> dict[str, Any]:
    return {"name": name, "passed": bool(passed), "actual": actual, "limit": limit}


def verify_affective_control(
    *,
    repository_root: Path,
    profile_path: Path,
    output_directory: Path,
    approver: str,
) -> tuple[Path, dict[str, Any]]:
    """Execute the approved P10 boundary profile through the production runtime."""

    normalized_approver = " ".join(str(approver).strip().split())
    if not 3 <= len(normalized_approver) <= 160:
        raise AffectiveVerificationError("APPROVAL_REQUIRED", "P10 approver role required")
    root = repository_root.expanduser().resolve()
    profile = _load_profile(profile_path)
    host = _host()
    if host["os"] != profile["supported_os"]:
        raise AffectiveVerificationError("HOST_UNSUPPORTED", "P10 host profile differs")
    run_id = f"p10-verified-{uuid.uuid4().hex}"
    run_root = output_directory.expanduser().resolve() / run_id
    runtime_root = run_root / "runtime"
    runtime_root.mkdir(parents=True, exist_ok=False)
    runtime = _runtime(runtime_root)
    try:
        status = runtime.execute_local_pillar(AFFECTIVE_CAPABILITY_ID, {"action": "status"})
        matrix = _matrix(runtime, profile)
        replay_request = {
            "action": "apply",
            "source": "SAFETY",
            "caution_delta": 0.25,
            "signal_id": "idempotency-same",
        }
        first = runtime.execute_local_pillar(AFFECTIVE_CAPABILITY_ID, replay_request)
        replay = runtime.execute_local_pillar(AFFECTIVE_CAPABILITY_ID, replay_request)
        conflict = _expect_error(
            runtime,
            {**replay_request, "caution_delta": -0.25},
            "IDEMPOTENCY_CONFLICT",
        )
        unconfirmed = _expect_error(
            runtime,
            {
                "action": "apply",
                "source": "USER_CONFIRMED",
                "signal_id": "unconfirmed-user-state",
                "urgency_delta": 0.2,
                "user_state_confirmed": False,
            },
            "INVALID_INPUT",
        )
        nonfinite = _expect_error(
            runtime,
            {
                "action": "apply",
                "source": "TASK",
                "signal_id": "nonfinite-delta",
                "urgency_delta": "nan",
            },
            "INVALID_INPUT",
        )
        unknown = _expect_error(
            runtime,
            {"action": "status", "unexpected": True},
            "UNKNOWN_FIELD",
        )
    finally:
        runtime.close()

    restarted = _runtime(runtime_root)
    try:
        restart_status = restarted.execute_local_pillar(
            AFFECTIVE_CAPABILITY_ID, {"action": "status"}
        )
        soak = _soak(restarted, profile["soak"])
    finally:
        restarted.close()

    moved_root = run_root / "runtime-closed-probe"
    runtime_root.replace(moved_root)
    moved_root.replace(runtime_root)
    clean_shutdown = runtime_root.is_dir()
    expected_baseline = profile["expected_baseline"]
    restart_state = restart_status.data["state"]
    restart_is_baseline = all(
        abs(float(restart_state[key]) - float(expected_baseline[key])) <= 0.00001
        for key in _STATE_FIELDS
    )
    soak_config = profile["soak"]
    gates = [
        _gate(
            "classification",
            status.data["classification"] == "RULE_BASED_CONTROL_STATE",
            status.data["classification"],
            "RULE_BASED_CONTROL_STATE",
        ),
        _gate("matrix_cases", matrix["cases"] >= 80, matrix["cases"], {"minimum": 80}),
        _gate("matrix_expected_values", matrix["mismatches"] == 0, matrix["mismatches"], 0),
        _gate(
            "matrix_safety_invariants",
            matrix["invariant_failures"] == 0,
            matrix["invariant_failures"],
            0,
        ),
        _gate(
            "idempotent_replay",
            first.data["changed"] is True and replay.data["changed"] is False,
            {"first": first.data["changed"], "replay": replay.data["changed"]},
            {"first": True, "replay": False},
        ),
        _gate("idempotency_conflict", conflict["code"] == "IDEMPOTENCY_CONFLICT", conflict["code"], "IDEMPOTENCY_CONFLICT"),
        _gate("unconfirmed_user_state", unconfirmed["code"] == "INVALID_INPUT", unconfirmed["code"], "INVALID_INPUT"),
        _gate("nonfinite_input", nonfinite["code"] == "INVALID_INPUT", nonfinite["code"], "INVALID_INPUT"),
        _gate("unknown_field", unknown["code"] == "UNKNOWN_FIELD", unknown["code"], "UNKNOWN_FIELD"),
        _gate("transient_restart", restart_is_baseline, restart_state, expected_baseline),
        _gate("clean_shutdown", clean_shutdown, clean_shutdown, True),
        _gate("soak_errors", soak["errors"] == 0, soak["errors"], 0),
        _gate("soak_invariants", soak["invariant_failures"] == 0, soak["invariant_failures"], 0),
        _gate(
            "soak_duration",
            soak["elapsed_seconds"] >= float(soak_config["minimum_elapsed_seconds"]),
            soak["elapsed_seconds"],
            {"minimum": float(soak_config["minimum_elapsed_seconds"])},
        ),
        _gate(
            "soak_latency",
            soak["mean_latency_ms"] <= float(soak_config["max_mean_latency_ms"]),
            soak["mean_latency_ms"],
            {"maximum": float(soak_config["max_mean_latency_ms"])},
        ),
        _gate(
            "soak_rss_growth",
            soak["rss_growth_bytes"] <= int(soak_config["max_rss_growth_bytes"]),
            soak["rss_growth_bytes"],
            {"maximum": int(soak_config["max_rss_growth_bytes"])},
        ),
        _gate(
            "package_energy_per_operation",
            soak["energy"]["joules_per_operation"]
            <= float(soak_config["max_package_joules_per_operation"]),
            soak["energy"]["joules_per_operation"],
            {"maximum": float(soak_config["max_package_joules_per_operation"])},
        ),
    ]
    verified = all(item["passed"] for item in gates)
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "VERIFIED_REPRESENTATIVE" if verified else "FAILED",
        "pillar": "P010",
        "scope": profile["scope"],
        "profile_id": profile["profile_id"],
        "profile_sha256": profile["profile_sha256"],
        "verified_at": datetime.now(UTC).isoformat(),
        "approval": {
            "approver": normalized_approver,
            "basis": "explicit repository-owner request to verify remaining pillars",
        },
        "version": {
            **_git_version(root),
            "source_bundle_sha256": _source_bundle_sha256(root, profile["source_files"]),
        },
        "environment": host,
        "matrix": matrix,
        "fault_drills": {
            "idempotency_conflict": conflict,
            "unconfirmed_user_state": unconfirmed,
            "nonfinite_input": nonfinite,
            "unknown_field": unknown,
        },
        "restart": {
            "status": restart_status.to_dict(),
            "state_is_baseline": restart_is_baseline,
            "clean_shutdown": clean_shutdown,
        },
        "soak": soak,
        "gates": gates,
        "limitations": [
            "verified only for explicit control signals in the named Windows profile",
            "the component is rule-based control state and does not infer human emotion",
            "energy is CPU-package total and is not process-attributed",
            "state is intentionally transient and resets on runtime restart",
            "worktree source is bound by digest because verification may precede commit",
        ],
        "rollback": {
            "action": "restore P010 manifest status to INTEGRATED",
            "state_impact": "none; affective control state is transient",
        },
    }
    report_path = run_root / "verified-affective-control-report.json"
    raw_report = _canonical_json(report)
    report_path.write_bytes(raw_report)
    Path(f"{report_path}.sha256").write_text(f"{_digest(raw_report)}\n", encoding="ascii")
    if not verified:
        failures = ", ".join(item["name"] for item in gates if not item["passed"])
        raise AffectiveVerificationError("VERIFICATION_FAILED", f"P10 gates failed: {failures}")
    return report_path, report


__all__ = ["AffectiveVerificationError", "verify_affective_control"]
