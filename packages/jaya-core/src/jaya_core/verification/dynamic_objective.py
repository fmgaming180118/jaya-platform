"""Representative verification runner for Pillar 39 Dynamic Objective."""

from __future__ import annotations

import hashlib
import hmac
import json
import math
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
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.control_capabilities import (
    OBJECTIVE_CAPABILITY_ID,
    DynamicObjectiveCapability,
)
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult
from jaya_core.pillars.reasoning_capabilities import (
    MetaPlanningCapability,
    SpeculativeReasoningCapability,
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

APPROVAL_KEY = b"dynamic-objective-verification-key-32b!"


class DynamicObjectiveVerificationError(RuntimeError):
    """Stable P39 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sign(material: str, key: bytes = APPROVAL_KEY) -> str:
    return hmac.new(key, material.encode("utf-8"), hashlib.sha256).hexdigest()


class RetrievalMockProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {"answer": f"Evidence says: {evidence[0]['content']}", "citations": [evidence[0]["evidence_id"]]}


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
        raise DynamicObjectiveVerificationError(
            "PROFILE_NOT_FOUND", f"Profile does not exist: {profile_path}"
        )
    with profile_path.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    missing = _PROFILE_FIELDS - set(profile)
    if missing:
        raise DynamicObjectiveVerificationError(
            "PROFILE_INVALID", f"Missing profile fields: {', '.join(sorted(missing))}"
        )
    if not _PROFILE_ID.match(str(profile.get("profile_id", ""))):
        raise DynamicObjectiveVerificationError("PROFILE_INVALID", "Invalid profile_id syntax")
    if profile.get("supported_os") != "Windows":
        raise DynamicObjectiveVerificationError(
            "UNSUPPORTED_OS_PROFILE", "This verification profile requires Windows"
        )
    return profile


def run_dynamic_objective_verification(
    profile_path: Path | None = None,
    workspace_root: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Execute all 15 canonical verification gates for Pillar 39."""
    start_wall = time.time()
    workspace = (workspace_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p39_windows_dynamic_objective_v1.json"
    ).resolve()

    profile = _load_profile(target_profile)
    gate_names = profile["matrix"]["gates"]
    soak_spec = profile["soak"]

    gate_results: dict[str, dict[str, Any]] = {}
    soak_metrics: dict[str, Any] = {}

    scratch = tempfile.mkdtemp(prefix="jaya_p39_verification_")
    scratch_dir = Path(scratch)
    db_path = scratch_dir / "dynamic_objective_verification.sqlite3"
    rag_db = scratch_dir / "rag.sqlite3"

    rag = AgenticRAGCapability(rag_db, RetrievalMockProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "artifact:resource-pressure",
            "title": "Resource Pressure Signal",
            "content": "Resource load exceeds threshold. Transition to high recovery mode.",
        }
    )
    evidence_id = rag.retrieve("resource load", 1)[0]["evidence_id"]
    sandbox = SandboxedImaginationCapability()

    try:
        # -------------------------------------------------------------
        # Gate 01: MANIFEST INTEGRITY
        # -------------------------------------------------------------
        g01_start = time.perf_counter()
        bundle = AdvancedPillarCapabilityService(
            data_dir=scratch_dir,
            control_approval_key=APPROVAL_KEY,
        )
        manifests = {m.capability_id: m for m in bundle.manifests()}
        if OBJECTIVE_CAPABILITY_ID not in manifests:
            raise DynamicObjectiveVerificationError("G01_FAILED", "Objective capability missing from bundle")
        m_obj = manifests[OBJECTIVE_CAPABILITY_ID]
        if m_obj.health_status != "HEALTHY":
            raise DynamicObjectiveVerificationError("G01_FAILED", f"Objective capability is {m_obj.health_status}")
        if not m_obj.offline_available:
            raise DynamicObjectiveVerificationError("G01_FAILED", "Objective capability must be offline available")

        # Verify 40_pillars.yaml entry
        yaml_path = workspace / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
        if yaml_path.is_file():
            with yaml_path.open("r", encoding="utf-8") as yf:
                pillars_doc = yaml.safe_load(yf)
            p39_entry = next((item for item in pillars_doc if item.get("id") == 39), None)
            if p39_entry is None or p39_entry.get("capability_id") != OBJECTIVE_CAPABILITY_ID:
                raise DynamicObjectiveVerificationError("G01_FAILED", "Pillar 39 contract mismatch in 40_pillars.yaml")

        g01_dur = (time.perf_counter() - g01_start) * 1000.0
        gate_results["G01_MANIFEST_INTEGRITY"] = {
            "status": "PASSED",
            "duration_ms": round(g01_dur, 3),
            "details": {"capability_id": OBJECTIVE_CAPABILITY_ID, "provider": m_obj.provider},
        }

        # -------------------------------------------------------------
        # Gate 02: OWNER GOAL IMMUTABILITY
        # -------------------------------------------------------------
        g02_start = time.perf_counter()
        cap = DynamicObjectiveCapability(db_path, APPROVAL_KEY, rag, sandbox, dampening_window_seconds=2.0)
        c_res = cap.execute(
            {
                "action": "create",
                "objective_id": "objective-root",
                "owner_id": "owner-root",
                "owner_goal": "Maintain uncompromised research integrity and availability",
                "invariants": ["1 + 1 == 2", "10 > 5"],
                "weights": {"recovery": 0.6, "exploration": 0.4},
            }
        )
        if c_res.data["version"] != 1:
            raise DynamicObjectiveVerificationError("G02_FAILED", "Initial version must be 1")
        if not c_res.data.get("goal_digest"):
            raise DynamicObjectiveVerificationError("G02_FAILED", "Initial goal digest missing")

        # Duplicate objective_id must be rejected
        try:
            cap.execute(
                {
                    "action": "create",
                    "objective_id": "objective-root",
                    "owner_id": "owner-root",
                    "owner_goal": "Duplicate attempt",
                    "invariants": ["True"],
                    "weights": {"recovery": 1.0},
                }
            )
            raise DynamicObjectiveVerificationError("G02_FAILED", "Duplicate objective creation should fail")
        except LocalPillarError as exc:
            if exc.code != "OBJECTIVE_EXISTS":
                raise DynamicObjectiveVerificationError("G02_FAILED", f"Expected OBJECTIVE_EXISTS, got {exc.code}")

        g02_dur = (time.perf_counter() - g02_start) * 1000.0
        gate_results["G02_OWNER_GOAL_IMMUTABILITY"] = {
            "status": "PASSED",
            "duration_ms": round(g02_dur, 3),
            "details": {"objective_id": "objective-root", "goal_digest": c_res.data["goal_digest"]},
        }

        # -------------------------------------------------------------
        # Gate 03: INVARIANT SAFETY GATING
        # -------------------------------------------------------------
        g03_start = time.perf_counter()
        try:
            cap.execute(
                {
                    "action": "create",
                    "objective_id": "obj-failing-invariant",
                    "owner_id": "owner-root",
                    "owner_goal": "Attempt with broken invariant",
                    "invariants": ["5 > 100"],
                    "weights": {"safety": 1.0},
                }
            )
            raise DynamicObjectiveVerificationError("G03_FAILED", "Failing invariant should fail creation")
        except LocalPillarError as exc:
            if exc.code != "INVARIANT_VIOLATION":
                raise DynamicObjectiveVerificationError("G03_FAILED", f"Expected INVARIANT_VIOLATION, got {exc.code}")

        g03_dur = (time.perf_counter() - g03_start) * 1000.0
        gate_results["G03_INVARIANT_SAFETY_GATING"] = {
            "status": "PASSED",
            "duration_ms": round(g03_dur, 3),
            "details": {"invariant_violation_blocked": True},
        }

        # -------------------------------------------------------------
        # Gate 04: BOUNDED WEIGHT NORMALIZATION
        # -------------------------------------------------------------
        g04_start = time.perf_counter()
        # Test negative weights rejected
        try:
            cap.execute(
                {
                    "action": "create",
                    "objective_id": "obj-negative-weights",
                    "owner_id": "owner-root",
                    "owner_goal": "Attempt with negative weights",
                    "invariants": ["True"],
                    "weights": {"a": -0.5, "b": 1.0},
                }
            )
            raise DynamicObjectiveVerificationError("G04_FAILED", "Negative weights must be rejected")
        except LocalPillarError as exc:
            if exc.code != "INVALID_INPUT":
                raise DynamicObjectiveVerificationError("G04_FAILED", f"Expected INVALID_INPUT, got {exc.code}")

        # Test normalization summing strictly to 1.0
        norm_res = cap.execute(
            {
                "action": "create",
                "objective_id": "obj-norm-check",
                "owner_id": "owner-root",
                "owner_goal": "Check weight normalization",
                "invariants": ["True"],
                "weights": {"w1": 2.5, "w2": 7.5},
            }
        )
        total_w = sum(norm_res.data["weights"].values())
        if abs(total_w - 1.0) > 1e-6:
            raise DynamicObjectiveVerificationError("G04_FAILED", f"Normalized weights sum to {total_w} != 1.0")

        g04_dur = (time.perf_counter() - g04_start) * 1000.0
        gate_results["G04_BOUNDED_WEIGHT_NORMALIZATION"] = {
            "status": "PASSED",
            "duration_ms": round(g04_dur, 3),
            "details": {"weights": norm_res.data["weights"], "sum": total_w},
        }

        # -------------------------------------------------------------
        # Gate 05: LEARNING RATE CLAMPING
        # -------------------------------------------------------------
        g05_start = time.perf_counter()
        # Rate > 0.25 rejected
        try:
            cap.execute(
                {
                    "action": "propose",
                    "objective_id": "objective-root",
                    "signals": {"recovery": 0.5, "exploration": -0.5},
                    "learning_rate": 0.30,
                    "evidence_ids": [evidence_id],
                    "policy_decision": "ALLOW",
                    "expires_at": time.time() + 300,
                }
            )
            raise DynamicObjectiveVerificationError("G05_FAILED", "Learning rate > 0.25 must be rejected")
        except LocalPillarError as exc:
            if exc.code != "INVALID_INPUT":
                raise DynamicObjectiveVerificationError("G05_FAILED", f"Expected INVALID_INPUT, got {exc.code}")

        # Rate <= 0 rejected
        try:
            cap.execute(
                {
                    "action": "propose",
                    "objective_id": "objective-root",
                    "signals": {"recovery": 0.5, "exploration": -0.5},
                    "learning_rate": 0.0,
                    "evidence_ids": [evidence_id],
                    "policy_decision": "ALLOW",
                    "expires_at": time.time() + 300,
                }
            )
            raise DynamicObjectiveVerificationError("G05_FAILED", "Learning rate 0.0 must be rejected")
        except LocalPillarError as exc:
            if exc.code != "INVALID_INPUT":
                raise DynamicObjectiveVerificationError("G05_FAILED", f"Expected INVALID_INPUT, got {exc.code}")

        g05_dur = (time.perf_counter() - g05_start) * 1000.0
        gate_results["G05_LEARNING_RATE_CLAMPING"] = {
            "status": "PASSED",
            "duration_ms": round(g05_dur, 3),
            "details": {"clamped_range": "(0, 0.25]"},
        }

        # -------------------------------------------------------------
        # Gate 06: EVIDENCE GROUNDING
        # -------------------------------------------------------------
        g06_start = time.perf_counter()
        try:
            cap.execute(
                {
                    "action": "propose",
                    "objective_id": "objective-root",
                    "signals": {"recovery": 0.5, "exploration": -0.5},
                    "learning_rate": 0.1,
                    "evidence_ids": ["non-existent-evidence-id-999"],
                    "policy_decision": "ALLOW",
                    "expires_at": time.time() + 300,
                }
            )
            raise DynamicObjectiveVerificationError("G06_FAILED", "Missing evidence must be rejected")
        except LocalPillarError as exc:
            if exc.code != "INVALID_EVIDENCE":
                raise DynamicObjectiveVerificationError("G06_FAILED", f"Expected INVALID_EVIDENCE, got {exc.code}")

        g06_dur = (time.perf_counter() - g06_start) * 1000.0
        gate_results["G06_EVIDENCE_GROUNDING"] = {
            "status": "PASSED",
            "duration_ms": round(g06_dur, 3),
            "details": {"invalid_evidence_blocked": True},
        }

        # -------------------------------------------------------------
        # Gate 07: POLICY DECISION GATING
        # -------------------------------------------------------------
        g07_start = time.perf_counter()
        try:
            cap.execute(
                {
                    "action": "propose",
                    "objective_id": "objective-root",
                    "signals": {"recovery": 0.5, "exploration": -0.5},
                    "learning_rate": 0.1,
                    "evidence_ids": [evidence_id],
                    "policy_decision": "DENY",
                    "expires_at": time.time() + 300,
                }
            )
            raise DynamicObjectiveVerificationError("G07_FAILED", "Policy DENY must be rejected")
        except LocalPillarError as exc:
            if exc.code != "POLICY_DENIED":
                raise DynamicObjectiveVerificationError("G07_FAILED", f"Expected POLICY_DENIED, got {exc.code}")

        g07_dur = (time.perf_counter() - g07_start) * 1000.0
        gate_results["G07_POLICY_DECISION_GATING"] = {
            "status": "PASSED",
            "duration_ms": round(g07_dur, 3),
            "details": {"policy_denied_blocked": True},
        }

        # -------------------------------------------------------------
        # Gate 08: OWNER APPROVAL SIGNATURE
        # -------------------------------------------------------------
        g08_start = time.perf_counter()
        prop1 = cap.execute(
            {
                "action": "propose",
                "objective_id": "objective-root",
                "signals": {"recovery": 0.8, "exploration": -0.5},
                "learning_rate": 0.1,
                "evidence_ids": [evidence_id],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 600,
            }
        )
        digest1 = prop1.data["proposal_digest"]
        approval_material = f"approve|objective-root|2|{digest1}|appr-gate-08|owner-root"
        appr_res = cap.execute(
            {
                "action": "approve",
                "objective_id": "objective-root",
                "version": 2,
                "approval_id": "appr-gate-08",
                "approved_by": "owner-root",
                "signature": _sign(approval_material),
            }
        )
        if appr_res.data["version"] != 2:
            raise DynamicObjectiveVerificationError("G08_FAILED", "Approved version mismatch")

        active_now = cap.active("objective-root")
        if active_now["version"] != 2:
            raise DynamicObjectiveVerificationError("G08_FAILED", "Active version did not advance to 2")

        g08_dur = (time.perf_counter() - g08_start) * 1000.0
        gate_results["G08_OWNER_APPROVAL_SIGNATURE"] = {
            "status": "PASSED",
            "duration_ms": round(g08_dur, 3),
            "details": {"approved_version": 2, "active_weights": active_now["weights"]},
        }

        # -------------------------------------------------------------
        # Gate 09: FORGED AND REPLAYED APPROVAL REJECTION
        # -------------------------------------------------------------
        g09_start = time.perf_counter()
        prop2 = cap.execute(
            {
                "action": "propose",
                "objective_id": "objective-root",
                "signals": {"recovery": 0.2, "exploration": -0.1},
                "learning_rate": 0.05,
                "evidence_ids": [evidence_id],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 600,
            }
        )
        digest2 = prop2.data["proposal_digest"]

        # Imposter approval rejected
        try:
            cap.execute(
                {
                    "action": "approve",
                    "objective_id": "objective-root",
                    "version": 3,
                    "approval_id": "appr-gate-09",
                    "approved_by": "imposter-user",
                    "signature": _sign(f"approve|objective-root|3|{digest2}|appr-gate-09|imposter-user"),
                }
            )
            raise DynamicObjectiveVerificationError("G09_FAILED", "Imposter approval must be rejected")
        except LocalPillarError as exc:
            if exc.code != "APPROVAL_DENIED":
                raise DynamicObjectiveVerificationError("G09_FAILED", f"Expected APPROVAL_DENIED, got {exc.code}")

        # Forged signature rejected
        try:
            cap.execute(
                {
                    "action": "approve",
                    "objective_id": "objective-root",
                    "version": 3,
                    "approval_id": "appr-gate-09",
                    "approved_by": "owner-root",
                    "signature": "forged_000000000000000000000000000000000000000000000000000000000",
                }
            )
            raise DynamicObjectiveVerificationError("G09_FAILED", "Forged signature must be rejected")
        except LocalPillarError as exc:
            if exc.code != "APPROVAL_DENIED":
                raise DynamicObjectiveVerificationError("G09_FAILED", f"Expected APPROVAL_DENIED, got {exc.code}")

        # Replayed approval_id rejected
        try:
            cap.execute(
                {
                    "action": "approve",
                    "objective_id": "objective-root",
                    "version": 3,
                    "approval_id": "appr-gate-08",  # Already used in Gate 08!
                    "approved_by": "owner-root",
                    "signature": _sign(f"approve|objective-root|3|{digest2}|appr-gate-08|owner-root"),
                }
            )
            raise DynamicObjectiveVerificationError("G09_FAILED", "Replayed approval_id must be rejected")
        except LocalPillarError as exc:
            if exc.code != "APPROVAL_DENIED":
                raise DynamicObjectiveVerificationError("G09_FAILED", f"Expected APPROVAL_DENIED, got {exc.code}")

        # Approve version 3 legitimately
        cap.execute(
            {
                "action": "approve",
                "objective_id": "objective-root",
                "version": 3,
                "approval_id": "appr-gate-09-legit",
                "approved_by": "owner-root",
                "signature": _sign(f"approve|objective-root|3|{digest2}|appr-gate-09-legit|owner-root"),
            }
        )

        g09_dur = (time.perf_counter() - g09_start) * 1000.0
        gate_results["G09_FORGED_AND_REPLAYED_APPROVAL_REJECTION"] = {
            "status": "PASSED",
            "duration_ms": round(g09_dur, 3),
            "details": {"forged_rejected": True, "replay_rejected": True},
        }

        # -------------------------------------------------------------
        # Gate 10: PROPOSAL EXPIRATION
        # -------------------------------------------------------------
        g10_start = time.perf_counter()
        cap_exp = DynamicObjectiveCapability(scratch_dir / "exp.sqlite3", APPROVAL_KEY, rag, sandbox)
        cap_exp.execute(
            {
                "action": "create",
                "objective_id": "obj-expire",
                "owner_id": "owner-root",
                "owner_goal": "Goal with expiring proposal",
                "invariants": ["True"],
                "weights": {"w1": 0.5, "w2": 0.5},
            }
        )
        prop_exp = cap_exp.execute(
            {
                "action": "propose",
                "objective_id": "obj-expire",
                "signals": {"w1": 0.2, "w2": -0.2},
                "learning_rate": 0.1,
                "evidence_ids": [evidence_id],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 0.15,
            }
        )
        time.sleep(0.25)
        try:
            mat_exp = f"approve|obj-expire|2|{prop_exp.data['proposal_digest']}|appr-exp|owner-root"
            cap_exp.execute(
                {
                    "action": "approve",
                    "objective_id": "obj-expire",
                    "version": 2,
                    "approval_id": "appr-exp",
                    "approved_by": "owner-root",
                    "signature": _sign(mat_exp),
                }
            )
            raise DynamicObjectiveVerificationError("G10_FAILED", "Expired proposal must be rejected")
        except LocalPillarError as exc:
            if exc.code != "PROPOSAL_EXPIRED":
                raise DynamicObjectiveVerificationError("G10_FAILED", f"Expected PROPOSAL_EXPIRED, got {exc.code}")

        g10_dur = (time.perf_counter() - g10_start) * 1000.0
        gate_results["G10_PROPOSAL_EXPIRATION"] = {
            "status": "PASSED",
            "duration_ms": round(g10_dur, 3),
            "details": {"proposal_expired_detected": True},
        }

        # -------------------------------------------------------------
        # Gate 11: ANTI OSCILLATION DAMPENING
        # -------------------------------------------------------------
        g11_start = time.perf_counter()
        cap_osc = DynamicObjectiveCapability(
            scratch_dir / "osc.sqlite3",
            APPROVAL_KEY,
            rag,
            sandbox,
            dampening_window_seconds=10.0,
        )
        cap_osc.execute(
            {
                "action": "create",
                "objective_id": "obj-osc-gate",
                "owner_id": "owner-root",
                "owner_goal": "Goal with oscillation dampening",
                "invariants": ["True"],
                "weights": {"w1": 0.5, "w2": 0.5},
            }
        )
        p_v2 = cap_osc.execute(
            {
                "action": "propose",
                "objective_id": "obj-osc-gate",
                "signals": {"w1": 0.8, "w2": -0.8},
                "learning_rate": 0.1,
                "evidence_ids": [evidence_id],
                "policy_decision": "ALLOW",
                "expires_at": time.time() + 600,
            }
        )
        cap_osc.execute(
            {
                "action": "approve",
                "objective_id": "obj-osc-gate",
                "version": 2,
                "approval_id": "appr-osc-v2",
                "approved_by": "owner-root",
                "signature": _sign(f"approve|obj-osc-gate|2|{p_v2.data['proposal_digest']}|appr-osc-v2|owner-root"),
            }
        )
        # Immediate proposal directly opposing previous signal
        try:
            cap_osc.execute(
                {
                    "action": "propose",
                    "objective_id": "obj-osc-gate",
                    "signals": {"w1": -0.8, "w2": 0.8},
                    "learning_rate": 0.1,
                    "evidence_ids": [evidence_id],
                    "policy_decision": "ALLOW",
                    "expires_at": time.time() + 600,
                }
            )
            raise DynamicObjectiveVerificationError("G11_FAILED", "Oscillation should have been detected")
        except LocalPillarError as exc:
            if exc.code != "OSCILLATION_DETECTED":
                raise DynamicObjectiveVerificationError("G11_FAILED", f"Expected OSCILLATION_DETECTED, got {exc.code}")

        g11_dur = (time.perf_counter() - g11_start) * 1000.0
        gate_results["G11_ANTI_OSCILLATION_DAMPENING"] = {
            "status": "PASSED",
            "duration_ms": round(g11_dur, 3),
            "details": {"oscillation_blocked": True, "dampening_window_seconds": 10.0},
        }

        # -------------------------------------------------------------
        # Gate 12: APPEND ONLY ROLLBACK LINEAGE
        # -------------------------------------------------------------
        g12_start = time.perf_counter()
        rb_mat = "rollback|objective-root|3|1|rb-gate-12|owner-root"
        rb_res = cap.execute(
            {
                "action": "rollback",
                "objective_id": "objective-root",
                "to_version": 1,
                "rollback_id": "rb-gate-12",
                "approved_by": "owner-root",
                "signature": _sign(rb_mat),
            }
        )
        if rb_res.data["version"] != 4 or rb_res.data["restored_from"] != 1:
            raise DynamicObjectiveVerificationError("G12_FAILED", "Rollback versioning corrupted")

        # Duplicate rollback_id rejected
        try:
            cap.execute(
                {
                    "action": "rollback",
                    "objective_id": "objective-root",
                    "to_version": 2,
                    "rollback_id": "rb-gate-12",  # Reused rollback_id
                    "approved_by": "owner-root",
                    "signature": _sign("rollback|objective-root|4|2|rb-gate-12|owner-root"),
                }
            )
            raise DynamicObjectiveVerificationError("G12_FAILED", "Duplicate rollback_id must be rejected")
        except LocalPillarError as exc:
            if exc.code != "DUPLICATE_ROLLBACK":
                raise DynamicObjectiveVerificationError("G12_FAILED", f"Expected DUPLICATE_ROLLBACK, got {exc.code}")

        # Check full history lineage
        hist = cap.execute({"action": "history", "objective_id": "objective-root"})
        if len(hist.data["versions"]) != 4:
            raise DynamicObjectiveVerificationError("G12_FAILED", f"Expected 4 versions in history, got {len(hist.data['versions'])}")
        if len(hist.data["rollbacks"]) != 1:
            raise DynamicObjectiveVerificationError("G12_FAILED", "Rollback history missing")

        g12_dur = (time.perf_counter() - g12_start) * 1000.0
        gate_results["G12_APPEND_ONLY_ROLLBACK_LINEAGE"] = {
            "status": "PASSED",
            "duration_ms": round(g12_dur, 3),
            "details": {"new_version": 4, "restored_from": 1, "history_entries": len(hist.data["versions"])},
        }

        # -------------------------------------------------------------
        # Gate 13: META PLANNER CONSUMPTION
        # -------------------------------------------------------------
        g13_start = time.perf_counter()
        spec = SpeculativeReasoningCapability(scratch_dir / "spec.sqlite3", rag, sandbox)
        planner = MetaPlanningCapability(scratch_dir / "plan.sqlite3", rag, sandbox, spec)
        planner.objective_resolver = cap.active

        # Valid plan execution bound to active objective
        plan_res = planner.execute(
            {
                "action": "run",
                "objective_id": "objective-root",
                "goal": "Maintain uncompromised research integrity and availability",
                "invariants": ["True"],
                "steps": [{"type": "sandbox", "expression": "25 * 4 == 100"}],
            }
        )
        if plan_res.data["status"] != "COMPLETED":
            raise DynamicObjectiveVerificationError("G13_FAILED", "Planner execution did not complete")
        if plan_res.data["objective_version"] != 4:
            raise DynamicObjectiveVerificationError("G13_FAILED", f"Expected objective_version 4, got {plan_res.data['objective_version']}")

        # Hijack attempt with goal mismatch rejected
        try:
            planner.execute(
                {
                    "action": "run",
                    "objective_id": "objective-root",
                    "goal": "Hijacked adversarial goal differing from owner goal",
                    "invariants": ["True"],
                    "steps": [{"type": "sandbox", "expression": "True"}],
                }
            )
            raise DynamicObjectiveVerificationError("G13_FAILED", "Goal hijack should have been rejected")
        except LocalPillarError as exc:
            if exc.code != "OBJECTIVE_HIJACK":
                raise DynamicObjectiveVerificationError("G13_FAILED", f"Expected OBJECTIVE_HIJACK, got {exc.code}")

        g13_dur = (time.perf_counter() - g13_start) * 1000.0
        gate_results["G13_META_PLANNER_CONSUMPTION"] = {
            "status": "PASSED",
            "duration_ms": round(g13_dur, 3),
            "details": {"planner_bound_version": 4, "hijack_prevented": True},
        }

        # -------------------------------------------------------------
        # Gate 14: TAMPER EVIDENT WAL PERSISTENCE
        # -------------------------------------------------------------
        g14_start = time.perf_counter()
        integrity_ok = cap.execute({"action": "verify_integrity", "objective_id": "objective-root"})
        if integrity_ok.data["status"] != "HEALTHY":
            raise DynamicObjectiveVerificationError("G14_FAILED", "Initial integrity check failed")

        # Verify WAL mode in SQLite
        with _open_db(db_path) as conn:
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if mode.upper() != "WAL":
                raise DynamicObjectiveVerificationError("G14_FAILED", f"Expected WAL mode, got {mode}")

        # Tamper test
        tamper_db = scratch_dir / "tamper.sqlite3"
        cap_t = DynamicObjectiveCapability(tamper_db, APPROVAL_KEY, rag, sandbox)
        cap_t.execute(
            {
                "action": "create",
                "objective_id": "obj-tamper-gate",
                "owner_id": "owner-root",
                "owner_goal": "Protected goal",
                "invariants": ["True"],
                "weights": {"w1": 1.0},
            }
        )
        with _open_db(tamper_db) as conn:
            conn.execute(
                "UPDATE owner_goals SET owner_goal='Tampered owner goal text' WHERE objective_id='obj-tamper-gate'"
            )

        try:
            cap_t.execute({"action": "verify_integrity", "objective_id": "obj-tamper-gate"})
            raise DynamicObjectiveVerificationError("G14_FAILED", "Tamper should have been detected")
        except LocalPillarError as exc:
            if exc.code != "STORAGE_CORRUPT":
                raise DynamicObjectiveVerificationError("G14_FAILED", f"Expected STORAGE_CORRUPT, got {exc.code}")

        g14_dur = (time.perf_counter() - g14_start) * 1000.0
        gate_results["G14_TAMPER_EVIDENT_WAL_PERSISTENCE"] = {
            "status": "PASSED",
            "duration_ms": round(g14_dur, 3),
            "details": {"journal_mode": "WAL", "tamper_detected": True},
        }

        # -------------------------------------------------------------
        # Gate 15: SOAK PERFORMANCE AND ENERGY
        # -------------------------------------------------------------
        g15_start = time.perf_counter()
        soak_db = scratch_dir / "objective_soak.sqlite3"
        soak_cap = DynamicObjectiveCapability(
            soak_db, APPROVAL_KEY, rag, sandbox, dampening_window_seconds=0.0
        )
        soak_cap.execute(
            {
                "action": "create",
                "objective_id": "soak-obj",
                "owner_id": "soak-owner",
                "owner_goal": "Continuous soak test objective",
                "invariants": ["True"],
                "weights": {"w1": 0.6, "w2": 0.4},
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

        current_ver = 1
        for i in range(iterations):
            iter_start = time.perf_counter()
            # Alternating positive/negative nudge without opposing check (dampening=0.0)
            sig_w1 = 0.5 if (i % 2 == 0) else -0.5
            sig_w2 = -sig_w1
            # Propose
            prop = soak_cap.execute(
                {
                    "action": "propose",
                    "objective_id": "soak-obj",
                    "signals": {"w1": sig_w1, "w2": sig_w2},
                    "learning_rate": 0.05,
                    "evidence_ids": [evidence_id],
                    "policy_decision": "ALLOW",
                    "expires_at": time.time() + 600,
                }
            )
            v = prop.data["version"]
            # Approve
            appr_id = f"soak-appr-{i}"
            mat = f"approve|soak-obj|{v}|{prop.data['proposal_digest']}|{appr_id}|soak-owner"
            soak_cap.execute(
                {
                    "action": "approve",
                    "objective_id": "soak-obj",
                    "version": v,
                    "approval_id": appr_id,
                    "approved_by": "soak-owner",
                    "signature": _sign(mat),
                }
            )
            current_ver = v

            # Rollback every 10 iterations
            if (i + 1) % 10 == 0:
                rb_id = f"soak-rb-{i}"
                rb_mat = f"rollback|soak-obj|{current_ver}|1|{rb_id}|soak-owner"
                rb_done = soak_cap.execute(
                    {
                        "action": "rollback",
                        "objective_id": "soak-obj",
                        "to_version": 1,
                        "rollback_id": rb_id,
                        "approved_by": "soak-owner",
                        "signature": _sign(rb_mat),
                    }
                )
                current_ver = rb_done.data["version"]

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

        if mean_latency > soak_spec.get("max_mean_latency_ms", 50.0):
            raise DynamicObjectiveVerificationError(
                "G15_FAILED", f"Mean latency {mean_latency:.2f}ms exceeds limit {soak_spec['max_mean_latency_ms']}ms"
            )
        if rss_growth > soak_spec.get("max_rss_growth_bytes", 33554432):
            raise DynamicObjectiveVerificationError(
                "G15_FAILED", f"RSS growth {rss_growth} exceeds limit {soak_spec['max_rss_growth_bytes']}"
            )
        if completion_rate < soak_spec.get("min_completion_rate", 0.95):
            raise DynamicObjectiveVerificationError(
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

        # Clean up references
        del cap, cap_exp, cap_osc, cap_t, soak_cap, bundle, planner, spec
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
        "pillar_id": 39,
        "pillar_name": "Dynamic Objective",
        "capability_id": OBJECTIVE_CAPABILITY_ID,
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


def verify_dynamic_objective(
    repository_root: Path | None = None,
    profile_path: Path | None = None,
    output_directory: Path | None = None,
    approver: str = "System-Veritas",
) -> tuple[Path, dict[str, Any]]:
    """Canonical verification wrapper compatible with repo CLI scripts."""
    workspace = (repository_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p39_windows_dynamic_objective_v1.json"
    ).resolve()
    out_dir = (output_directory or workspace / "artifacts" / "verified-dynamic-objective").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "verification_receipt.json"

    receipt = run_dynamic_objective_verification(
        profile_path=target_profile,
        workspace_root=workspace,
        output_path=out_file,
    )
    receipt["approver"] = approver
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)

    return out_file, receipt
