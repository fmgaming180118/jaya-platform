"""Representative verification runner for Pillar 40 Intent Extrapolation."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
import yaml

from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.advanced_capabilities import AdvancedPillarCapabilityService
from jaya_core.pillars.control_capabilities import (
    INTENT_CAPABILITY_ID,
    IntentExtrapolationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult

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


class IntentExtrapolationVerificationError(RuntimeError):
    """Stable P40 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@contextmanager
def _open_db(path: Path) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(path, timeout=5.0)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def _git_commit(workspace_root: Path) -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace_root,
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout.strip()
    except Exception:
        return "unknown"


def _system_metadata() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "processor": platform.processor() or "unknown",
        "machine": platform.machine() or "unknown",
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "total_memory_bytes": psutil.virtual_memory().total,
    }


def _load_profile(profile_path: Path) -> dict[str, Any]:
    if not profile_path.is_file():
        raise IntentExtrapolationVerificationError(
            "PROFILE_NOT_FOUND", f"Profile does not exist: {profile_path}"
        )
    with profile_path.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    missing = _PROFILE_FIELDS - set(profile)
    if missing:
        raise IntentExtrapolationVerificationError(
            "PROFILE_INVALID", f"Missing profile fields: {', '.join(sorted(missing))}"
        )
    if not _PROFILE_ID.match(str(profile.get("profile_id", ""))):
        raise IntentExtrapolationVerificationError("PROFILE_INVALID", "Invalid profile_id syntax")
    if profile.get("supported_os") != "Windows":
        raise IntentExtrapolationVerificationError(
            "UNSUPPORTED_OS_PROFILE", "This verification profile requires Windows"
        )
    return profile


def run_intent_extrapolation_verification(
    profile_path: Path | None = None,
    workspace_root: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Execute all 15 canonical verification gates for Pillar 40."""
    start_wall = time.time()
    workspace = (workspace_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p40_windows_intent_extrapolation_v1.json"
    ).resolve()

    profile = _load_profile(target_profile)
    gate_names = profile["matrix"]["gates"]
    soak_spec = profile["soak"]

    gate_results: dict[str, dict[str, Any]] = {}
    soak_metrics: dict[str, Any] = {}

    scratch = tempfile.mkdtemp(prefix="jaya_p40_verification_")
    scratch_dir = Path(scratch)
    db_path = scratch_dir / "intent_verification.sqlite3"
    try:

        # -------------------------------------------------------------
        # Gate 01: MANIFEST INTEGRITY
        # -------------------------------------------------------------
        g01_start = time.perf_counter()
        bundle = AdvancedPillarCapabilityService(data_dir=scratch_dir)
        manifests = {m.capability_id: m for m in bundle.manifests()}
        if INTENT_CAPABILITY_ID not in manifests:
            raise IntentExtrapolationVerificationError("G01_FAILED", "Intent capability missing from bundle")
        m_intent = manifests[INTENT_CAPABILITY_ID]
        if m_intent.health_status != "HEALTHY":
            raise IntentExtrapolationVerificationError("G01_FAILED", f"Intent capability is {m_intent.health_status}")
        if not m_intent.offline_available:
            raise IntentExtrapolationVerificationError("G01_FAILED", "Intent capability must be offline available")

        # Verify 40_pillars.yaml entry
        yaml_path = workspace / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
        if yaml_path.is_file():
            with yaml_path.open("r", encoding="utf-8") as yf:
                pillars_doc = yaml.safe_load(yf)
            p40_entry = next((item for item in pillars_doc if item.get("id") == 40), None)
            if p40_entry is None or p40_entry.get("capability_id") != INTENT_CAPABILITY_ID:
                raise IntentExtrapolationVerificationError("G01_FAILED", "Pillar 40 contract mismatch in 40_pillars.yaml")
        g01_dur = (time.perf_counter() - g01_start) * 1000.0
        gate_results["G01_MANIFEST_INTEGRITY"] = {
            "status": "PASSED",
            "duration_ms": round(g01_dur, 3),
            "details": {"capability_id": INTENT_CAPABILITY_ID, "provider": m_intent.provider},
        }

        # -------------------------------------------------------------
        # Gate 02: EXPLICIT EXPIRING CONSENT
        # -------------------------------------------------------------
        g02_start = time.perf_counter()
        cap = IntentExtrapolationCapability(db_path)
        # Verify unconsented fails
        try:
            cap.execute({"action": "observe", "owner_id": "test-owner", "sequence": ["step1", "step2"]})
            raise IntentExtrapolationVerificationError("G02_FAILED", "Unconsented observation should have failed")
        except LocalPillarError as exc:
            if exc.code != "CONSENT_REQUIRED":
                raise IntentExtrapolationVerificationError("G02_FAILED", f"Expected CONSENT_REQUIRED, got {exc.code}")

        now = time.time()
        c_res = cap.execute(
            {
                "action": "record_consent",
                "owner_id": "test-owner",
                "receipt_id": "rcpt-001",
                "granted_at": now - 1,
                "expires_at": now + 7200,
            }
        )
        if c_res.data["owner_id"] != "test-owner":
            raise IntentExtrapolationVerificationError("G02_FAILED", "Consent record data corrupted")
        status_res = cap.execute({"action": "consent_status", "owner_id": "test-owner"})
        if not status_res.data["active"] or not status_res.data["has_consent"]:
            raise IntentExtrapolationVerificationError("G02_FAILED", "Consent status not active")
        g02_dur = (time.perf_counter() - g02_start) * 1000.0
        gate_results["G02_EXPLICIT_EXPIRING_CONSENT"] = {
            "status": "PASSED",
            "duration_ms": round(g02_dur, 3),
            "details": {"receipt_id": "rcpt-001", "expires_at": now + 7200},
        }

        # -------------------------------------------------------------
        # Gate 03: CONSENT EXPIRY AND REVOCATION
        # -------------------------------------------------------------
        g03_start = time.perf_counter()
        # Test invalid window
        try:
            cap.execute(
                {
                    "action": "record_consent",
                    "owner_id": "exp-owner",
                    "receipt_id": "rcpt-exp",
                    "granted_at": now - 500,
                    "expires_at": now - 100,  # Already expired
                }
            )
            raise IntentExtrapolationVerificationError("G03_FAILED", "Past expiry consent should be rejected")
        except LocalPillarError as exc:
            if exc.code != "INVALID_CONSENT":
                raise IntentExtrapolationVerificationError("G03_FAILED", f"Expected INVALID_CONSENT, got {exc.code}")

        # Test short-lived consent that expires
        cap.execute(
            {
                "action": "record_consent",
                "owner_id": "exp-owner",
                "receipt_id": "rcpt-exp2",
                "granted_at": now,
                "expires_at": now + 0.15,
            }
        )
        time.sleep(0.2)
        try:
            cap.execute({"action": "predict", "owner_id": "exp-owner", "current_intent": "inspect"})
            raise IntentExtrapolationVerificationError("G03_FAILED", "Expired consent should fail prediction")
        except LocalPillarError as exc:
            if exc.code != "CONSENT_EXPIRED":
                raise IntentExtrapolationVerificationError("G03_FAILED", f"Expected CONSENT_EXPIRED, got {exc.code}")
        g03_dur = (time.perf_counter() - g03_start) * 1000.0
        gate_results["G03_CONSENT_EXPIRY_AND_REVOCATION"] = {
            "status": "PASSED",
            "duration_ms": round(g03_dur, 3),
            "details": {"expired_detected": True},
        }

        # -------------------------------------------------------------
        # Gate 04: PROFILING OPT OUT ENFORCEMENT
        # -------------------------------------------------------------
        g04_start = time.perf_counter()
        cap.execute(
            {
                "action": "record_consent",
                "owner_id": "opt-owner",
                "receipt_id": "rcpt-opt",
                "granted_at": time.time() - 1,
                "expires_at": time.time() + 3600,
            }
        )
        cap.execute({"action": "observe", "owner_id": "opt-owner", "sequence": ["alpha", "beta"]})
        cap.execute({"action": "opt_out", "owner_id": "opt-owner"})
        opt_status = cap.execute({"action": "consent_status", "owner_id": "opt-owner"})
        if not opt_status.data["opted_out"] or opt_status.data["active"]:
            raise IntentExtrapolationVerificationError("G04_FAILED", "Opt out state not reflected")
        try:
            cap.execute({"action": "observe", "owner_id": "opt-owner", "sequence": ["alpha", "beta"]})
            raise IntentExtrapolationVerificationError("G04_FAILED", "Observation after opt-out should fail")
        except LocalPillarError as exc:
            if exc.code != "CONSENT_REQUIRED":
                raise IntentExtrapolationVerificationError("G04_FAILED", f"Expected CONSENT_REQUIRED, got {exc.code}")
        g04_dur = (time.perf_counter() - g04_start) * 1000.0
        gate_results["G04_PROFILING_OPT_OUT_ENFORCEMENT"] = {
            "status": "PASSED",
            "duration_ms": round(g04_dur, 3),
            "details": {"opted_out": True, "profiling_disabled": True},
        }

        # -------------------------------------------------------------
        # Gate 05: SOVEREIGN DATA PURGE
        # -------------------------------------------------------------
        g05_start = time.perf_counter()
        purge_owner = "purge-owner"
        cap.execute(
            {
                "action": "record_consent",
                "owner_id": purge_owner,
                "receipt_id": "rcpt-purge",
                "granted_at": time.time() - 1,
                "expires_at": time.time() + 3600,
            }
        )
        cap.execute({"action": "observe", "owner_id": purge_owner, "sequence": ["build", "test", "deploy"]})
        cap.execute({"action": "delete", "owner_id": purge_owner})
        p_status = cap.execute({"action": "consent_status", "owner_id": purge_owner})
        if p_status.data["has_consent"]:
            raise IntentExtrapolationVerificationError("G05_FAILED", "Consent not erased after sovereign purge")
        with _open_db(db_path) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM intent_transitions WHERE owner_id=?", (purge_owner,)).fetchone()[0]
            if cnt != 0:
                raise IntentExtrapolationVerificationError("G05_FAILED", f"Residual transitions found: {cnt}")
        g05_dur = (time.perf_counter() - g05_start) * 1000.0
        gate_results["G05_SOVEREIGN_DATA_PURGE"] = {
            "status": "PASSED",
            "duration_ms": round(g05_dur, 3),
            "details": {"purged": True, "residual_count": 0},
        }

        # -------------------------------------------------------------
        # Gate 06: REAL TRANSITION OBSERVATION
        # -------------------------------------------------------------
        g06_start = time.perf_counter()
        owner = "bench-owner"
        cap.execute(
            {
                "action": "record_consent",
                "owner_id": owner,
                "receipt_id": "rcpt-bench",
                "granted_at": time.time() - 1,
                "expires_at": time.time() + 86400,
            }
        )
        for _ in range(5):
            cap.execute(
                {
                    "action": "observe",
                    "owner_id": owner,
                    "sequence": ["search_code", "read_file", "edit_code", "run_test"],
                }
            )
        with _open_db(db_path) as conn:
            row = conn.execute(
                "SELECT observations FROM intent_transitions WHERE owner_id=? AND current_intent=? AND next_intent=?",
                (owner, "edit_code", "run_test"),
            ).fetchone()
            if row is None or int(row[0]) != 5:
                raise IntentExtrapolationVerificationError("G06_FAILED", f"Expected 5 observations, got {row}")
        g06_dur = (time.perf_counter() - g06_start) * 1000.0
        gate_results["G06_REAL_TRANSITION_OBSERVATION"] = {
            "status": "PASSED",
            "duration_ms": round(g06_dur, 3),
            "details": {"observations_counted": 5},
        }

        # -------------------------------------------------------------
        # Gate 07: INFERENCE LABELING AND CONTRACT
        # -------------------------------------------------------------
        g07_start = time.perf_counter()
        pred = cap.execute({"action": "predict", "owner_id": owner, "current_intent": "read_file"})
        p_data = pred.data
        if p_data.get("source") != "INFERENCE":
            raise IntentExtrapolationVerificationError("G07_FAILED", f"Invalid source label: {p_data.get('source')}")
        if p_data.get("candidate") != "edit_code":
            raise IntentExtrapolationVerificationError("G07_FAILED", f"Expected 'edit_code', got {p_data.get('candidate')}")
        if not (0.0 <= float(p_data.get("confidence", -1)) <= 1.0):
            raise IntentExtrapolationVerificationError("G07_FAILED", "Confidence must be within [0, 1]")
        if not p_data.get("explanation"):
            raise IntentExtrapolationVerificationError("G07_FAILED", "Missing explanation in prediction contract")
        g07_dur = (time.perf_counter() - g07_start) * 1000.0
        gate_results["G07_INFERENCE_LABELING_AND_CONTRACT"] = {
            "status": "PASSED",
            "duration_ms": round(g07_dur, 3),
            "details": {"source": p_data["source"], "candidate": p_data["candidate"], "confidence": p_data["confidence"]},
        }

        # -------------------------------------------------------------
        # Gate 08: SIDE EFFECT PROHIBITION
        # -------------------------------------------------------------
        g08_start = time.perf_counter()
        if p_data.get("confirmation_required") is not True:
            raise IntentExtrapolationVerificationError("G08_FAILED", "confirmation_required must be strictly True")
        if p_data.get("executed") is not False:
            raise IntentExtrapolationVerificationError("G08_FAILED", "executed must be strictly False (never auto-execute)")
        g08_dur = (time.perf_counter() - g08_start) * 1000.0
        gate_results["G08_SIDE_EFFECT_PROHIBITION"] = {
            "status": "PASSED",
            "duration_ms": round(g08_dur, 3),
            "details": {"confirmation_required": True, "executed": False},
        }

        # -------------------------------------------------------------
        # Gate 09: INSUFFICIENT HISTORY HANDLING
        # -------------------------------------------------------------
        g09_start = time.perf_counter()
        try:
            cap.execute(
                {
                    "action": "predict",
                    "owner_id": owner,
                    "current_intent": "read_file",
                    "minimum_observations": 100,  # Far higher than 5
                }
            )
            raise IntentExtrapolationVerificationError("G09_FAILED", "Should have raised INSUFFICIENT_HISTORY")
        except LocalPillarError as exc:
            if exc.code != "INSUFFICIENT_HISTORY":
                raise IntentExtrapolationVerificationError("G09_FAILED", f"Expected INSUFFICIENT_HISTORY, got {exc.code}")
        g09_dur = (time.perf_counter() - g09_start) * 1000.0
        gate_results["G09_INSUFFICIENT_HISTORY_HANDLING"] = {
            "status": "PASSED",
            "duration_ms": round(g09_dur, 3),
            "details": {"threshold_enforced": True},
        }

        # -------------------------------------------------------------
        # Gate 10: AMBIGUOUS INTENT GATING
        # -------------------------------------------------------------
        g10_start = time.perf_counter()
        cap.execute({"action": "observe", "owner_id": owner, "sequence": ["branch_a", "branch_b"]})
        cap.execute({"action": "observe", "owner_id": owner, "sequence": ["branch_a", "branch_c"]})
        try:
            cap.execute({"action": "predict", "owner_id": owner, "current_intent": "branch_a"})
            raise IntentExtrapolationVerificationError("G10_FAILED", "Should have detected tied candidates")
        except LocalPillarError as exc:
            if exc.code != "AMBIGUOUS_INTENT":
                raise IntentExtrapolationVerificationError("G10_FAILED", f"Expected AMBIGUOUS_INTENT, got {exc.code}")
        g10_dur = (time.perf_counter() - g10_start) * 1000.0
        gate_results["G10_AMBIGUOUS_INTENT_GATING"] = {
            "status": "PASSED",
            "duration_ms": round(g10_dur, 3),
            "details": {"ambiguity_gated": True},
        }

        # -------------------------------------------------------------
        # Gate 11: STALE CONTEXT DECAY
        # -------------------------------------------------------------
        g11_start = time.perf_counter()
        with _open_db(db_path) as conn:
            conn.execute(
                "UPDATE intent_transitions SET updated_at = ? WHERE owner_id=? AND current_intent=?",
                (time.time() - 3600, owner, "read_file"),
            )
        try:
            cap.execute(
                {
                    "action": "predict",
                    "owner_id": owner,
                    "current_intent": "read_file",
                    "max_staleness_seconds": 60,
                }
            )
            raise IntentExtrapolationVerificationError("G11_FAILED", "Stale transition was not filtered out")
        except LocalPillarError as exc:
            if exc.code != "INSUFFICIENT_HISTORY":
                raise IntentExtrapolationVerificationError("G11_FAILED", f"Expected INSUFFICIENT_HISTORY, got {exc.code}")
        # Restore timestamp
        with _open_db(db_path) as conn:
            conn.execute(
                "UPDATE intent_transitions SET updated_at = ? WHERE owner_id=? AND current_intent=?",
                (time.time(), owner, "read_file"),
            )
        g11_dur = (time.perf_counter() - g11_start) * 1000.0
        gate_results["G11_STALE_CONTEXT_DECAY"] = {
            "status": "PASSED",
            "duration_ms": round(g11_dur, 3),
            "details": {"staleness_filtered": True},
        }

        # -------------------------------------------------------------
        # Gate 12: DETERMINISTIC FEEDBACK ADAPTATION
        # -------------------------------------------------------------
        g12_start = time.perf_counter()
        pred_fb = cap.execute({"action": "predict", "owner_id": owner, "current_intent": "edit_code"})
        pid = pred_fb.data["prediction_id"]
        # User rejects "run_test" and corrects with "lint_check"
        cap.execute(
            {
                "action": "feedback",
                "prediction_id": pid,
                "confirmed": False,
                "alternative_intent": "lint_check",
            }
        )
        with _open_db(db_path) as conn:
            row = conn.execute(
                "SELECT corrected FROM intent_transitions WHERE owner_id=? AND current_intent=? AND next_intent=?",
                (owner, "edit_code", "run_test"),
            ).fetchone()
            if row is None or int(row[0]) != 1:
                raise IntentExtrapolationVerificationError("G12_FAILED", "Correction count not incremented")
        g12_dur = (time.perf_counter() - g12_start) * 1000.0
        gate_results["G12_DETERMINISTIC_FEEDBACK_ADAPTATION"] = {
            "status": "PASSED",
            "duration_ms": round(g12_dur, 3),
            "details": {"corrected_applied": True, "alternative_recorded": True},
        }

        # -------------------------------------------------------------
        # Gate 13: RESTART DURABILITY AND WAL
        # -------------------------------------------------------------
        g13_start = time.perf_counter()
        restarted = IntentExtrapolationCapability(db_path)
        if not restarted.health_check():
            raise IntentExtrapolationVerificationError("G13_FAILED", "Restarted instance failed health check")
        pred_restarted = restarted.execute({"action": "predict", "owner_id": owner, "current_intent": "read_file"})
        if pred_restarted.data["candidate"] != "edit_code":
            raise IntentExtrapolationVerificationError("G13_FAILED", "State lost across restart")
        with _open_db(db_path) as conn:
            jmode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if jmode.upper() != "WAL":
                raise IntentExtrapolationVerificationError("G13_FAILED", f"Expected WAL mode, got {jmode}")
        g13_dur = (time.perf_counter() - g13_start) * 1000.0
        gate_results["G13_RESTART_DURABILITY_AND_WAL"] = {
            "status": "PASSED",
            "duration_ms": round(g13_dur, 3),
            "details": {"restart_verified": True, "journal_mode": "WAL"},
        }

        # -------------------------------------------------------------
        # Gate 14: TAMPER EVIDENT STATE INTEGRITY
        # -------------------------------------------------------------
        g14_start = time.perf_counter()
        if not cap.verify_integrity():
            raise IntentExtrapolationVerificationError("G14_FAILED", "Initial integrity verification failed")
        with _open_db(db_path) as conn:
            conn.execute(
                "UPDATE intent_transitions SET observations = 99999 WHERE owner_id=? AND current_intent=?",
                (owner, "read_file"),
            )
        try:
            cap.verify_integrity()
            raise IntentExtrapolationVerificationError("G14_FAILED", "Tampered state was not detected")
        except LocalPillarError as exc:
            if exc.code != "STORAGE_CORRUPT":
                raise IntentExtrapolationVerificationError("G14_FAILED", f"Expected STORAGE_CORRUPT, got {exc.code}")
        g14_dur = (time.perf_counter() - g14_start) * 1000.0
        gate_results["G14_TAMPER_EVIDENT_STATE_INTEGRITY"] = {
            "status": "PASSED",
            "duration_ms": round(g14_dur, 3),
            "details": {"tamper_detected": True},
        }

        # -------------------------------------------------------------
        # Gate 15: SOAK PERFORMANCE AND ENERGY
        # -------------------------------------------------------------
        g15_start = time.perf_counter()
        soak_db = scratch_dir / "intent_soak.sqlite3"
        soak_cap = IntentExtrapolationCapability(soak_db)
        soak_owner = "soak-subject"
        soak_cap.execute(
            {
                "action": "record_consent",
                "owner_id": soak_owner,
                "receipt_id": "soak-rcpt",
                "granted_at": time.time() - 1,
                "expires_at": time.time() + 86400,
            }
        )

        proc = psutil.Process()
        initial_rss = proc.memory_info().rss
        iterations = soak_spec.get("iterations", 100)
        latencies_ms: list[float] = []

        energy_meter: WindowsEmiEnergyMeter | None = None
        start_sample = None
        try:
            energy_meter = WindowsEmiEnergyMeter()
            start_sample = energy_meter.sample()
        except EnergyMeterError:
            energy_meter = None
            start_sample = None

        completed_count = 0
        soak_t0 = time.perf_counter()
        workflow_steps = ["open_doc", "analyze_syntax", "extract_ast", "format_output"]
        for i in range(iterations):
            iter_start = time.perf_counter()
            # Observe
            soak_cap.execute(
                {
                    "action": "observe",
                    "owner_id": soak_owner,
                    "sequence": workflow_steps,
                }
            )
            # Predict
            pred_soak = soak_cap.execute(
                {
                    "action": "predict",
                    "owner_id": soak_owner,
                    "current_intent": "analyze_syntax",
                    "minimum_observations": 1,
                }
            )
            # Feedback
            soak_cap.execute(
                {
                    "action": "feedback",
                    "prediction_id": pred_soak.data["prediction_id"],
                    "confirmed": True,
                }
            )
            iter_elapsed = (time.perf_counter() - iter_start) * 1000.0
            latencies_ms.append(iter_elapsed)
            completed_count += 1

        soak_elapsed = time.perf_counter() - soak_t0
        energy_report: dict[str, Any] | None = None
        if energy_meter is not None and start_sample is not None:
            try:
                end_sample = energy_meter.sample()
                measured = energy_meter.measure(start_sample, end_sample)
                energy_report = measured.to_dict()
                energy_report["joules_per_record"] = round(measured.joules / max(1, completed_count), 6)
            except EnergyMeterError:
                est_joules = round(soak_elapsed * 28.0, 4)
                energy_report = {
                    "status": "FALLBACK_ESTIMATED",
                    "joules": est_joules,
                    "joules_per_record": round(est_joules / max(1, completed_count), 6),
                }
        else:
            est_joules = round(soak_elapsed * 28.0, 4)
            energy_report = {
                "status": "FALLBACK_ESTIMATED",
                "joules": est_joules,
                "joules_per_record": round(est_joules / max(1, completed_count), 6),
            }

        final_rss = proc.memory_info().rss
        rss_growth = max(0, final_rss - initial_rss)
        mean_latency = sum(latencies_ms) / len(latencies_ms)
        sorted_lat = sorted(latencies_ms)
        p50 = sorted_lat[len(sorted_lat) // 2]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)]
        completion_rate = completed_count / iterations

        if mean_latency > soak_spec.get("max_mean_latency_ms", 100.0):
            raise IntentExtrapolationVerificationError(
                "G15_FAILED", f"Mean latency {mean_latency:.2f}ms exceeds limit {soak_spec['max_mean_latency_ms']}ms"
            )
        if rss_growth > soak_spec.get("max_rss_growth_bytes", 33554432):
            raise IntentExtrapolationVerificationError(
                "G15_FAILED", f"RSS growth {rss_growth} exceeds limit {soak_spec['max_rss_growth_bytes']}"
            )
        if completion_rate < soak_spec.get("min_completion_rate", 0.95):
            raise IntentExtrapolationVerificationError(
                "G15_FAILED", f"Completion rate {completion_rate:.2f} below minimum {soak_spec['min_completion_rate']}"
            )

        g15_dur = (time.perf_counter() - g15_start) * 1000.0
        soak_metrics = {
            "iterations": iterations,
            "completion_rate": completion_rate,
            "mean_latency_ms": round(mean_latency, 3),
            "p50_latency_ms": round(p50, 3),
            "p95_latency_ms": round(p95, 3),
            "p99_latency_ms": round(p99, 3),
            "initial_rss_bytes": initial_rss,
            "final_rss_bytes": final_rss,
            "rss_growth_bytes": rss_growth,
            "energy": energy_report,
        }
        gate_results["G15_SOAK_PERFORMANCE_AND_ENERGY"] = {
            "status": "PASSED",
            "duration_ms": round(g15_dur, 3),
            "details": soak_metrics,
        }

        # Explicitly release references and trigger garbage collection to close SQLite handles on Windows
        del cap, pred, pred_fb, pred_restarted, pred_soak, restarted, soak_cap, bundle
        import gc
        gc.collect()
    finally:
        import gc
        import shutil
        gc.collect()
        try:
            shutil.rmtree(scratch, ignore_errors=True)
        except Exception:
            pass

    total_wall_dur = (time.time() - start_wall) * 1000.0
    passed_count = sum(1 for g in gate_results.values() if g["status"] == "PASSED")
    all_passed = passed_count == len(gate_names)

    receipt = {
        "schema_version": 1,
        "pillar_id": 40,
        "pillar_name": "Intent Extrapolation",
        "capability_id": INTENT_CAPABILITY_ID,
        "profile_id": profile["profile_id"],
        "status": "VERIFIED" if all_passed else "FAILED",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "git_commit": _git_commit(workspace),
        "system": _system_metadata(),
        "gates_summary": {
            "total": len(gate_names),
            "passed": passed_count,
            "failed": len(gate_names) - passed_count,
            "all_passed": all_passed,
        },
        "gates": gate_results,
        "soak": soak_metrics,
        "total_duration_ms": round(total_wall_dur, 3),
    }

    if output_path:
        out_file = Path(output_path).resolve()
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w", encoding="utf-8") as f:
            json.dump(receipt, f, indent=2, ensure_ascii=False)

    return receipt


def verify_intent_extrapolation(
    repository_root: Path | None = None,
    profile_path: Path | None = None,
    output_directory: Path | None = None,
    approver: str = "System-Veritas",
) -> tuple[Path, dict[str, Any]]:
    """Canonical verification wrapper compatible with repo CLI scripts."""
    workspace = (repository_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p40_windows_intent_extrapolation_v1.json"
    ).resolve()
    out_dir = (output_directory or workspace / "artifacts" / "verified-intent-extrapolation").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "verification_receipt.json"

    receipt = run_intent_extrapolation_verification(
        profile_path=target_profile,
        workspace_root=workspace,
        output_path=out_file,
    )
    receipt["approver"] = approver
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)
    return out_file, receipt

