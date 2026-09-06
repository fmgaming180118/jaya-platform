"""Representative verification runner for Pillar 03 Active Dreaming."""

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
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult
from jaya_core.pillars.reasoning_capabilities import (
    ActiveDreamingCapability,
    DeterministicCounterfactualProvider,
    HypothesisProvider,
)
from jaya_core.pillars.advanced_capabilities import (
    AdvancedPillarCapabilityService,
    DREAM_CAPABILITY_ID,
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


class ActiveDreamingVerificationError(RuntimeError):
    """Stable P03 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest_bytes(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _git_commit(repository_root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repository_root),
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        return proc.stdout.strip()
    except Exception:
        return "0" * 40


@contextmanager
def _energy_sampler() -> Iterator[dict[str, Any]]:
    meter = None
    start_sample = None
    if sys.platform.startswith("win"):
        try:
            meter = WindowsEmiEnergyMeter()
            start_sample = meter.sample()
        except EnergyMeterError:
            meter = None
            start_sample = None

    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "energy_joules": 0.0,
        "energy_method": "SOFTWARE_FALLBACK" if start_sample is None else "WINDOWS_EMI",
    }
    try:
        yield result
    finally:
        elapsed = time.perf_counter() - t0
        if meter is not None and start_sample is not None:
            try:
                end_sample = meter.sample()
                measured = meter.measure(start_sample, end_sample)
                result["energy_joules"] = float(measured.joules or (elapsed * 28.0))
            except EnergyMeterError:
                result["energy_joules"] = round(elapsed * 28.0, 4)
                result["energy_method"] = "SOFTWARE_FALLBACK"
        else:
            result["energy_joules"] = round(elapsed * 28.0, 4)


def _load_profile(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ActiveDreamingVerificationError("PROFILE_NOT_FOUND", f"profile does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise ActiveDreamingVerificationError("INVALID_PROFILE", f"invalid JSON: {exc}") from exc

    missing = _PROFILE_FIELDS - set(data.keys())
    if missing:
        raise ActiveDreamingVerificationError("INVALID_PROFILE", f"missing fields: {sorted(missing)}")
    if not _PROFILE_ID.match(str(data["profile_id"])):
        raise ActiveDreamingVerificationError("INVALID_PROFILE", f"invalid profile_id: {data['profile_id']}")
    return data


def verify_active_dreaming(
    profile_path: Path,
    approver: str,
    output_directory: Path | None = None,
    repository_root: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Execute the full 15-gate verification suite for Pillar 03: Active Dreaming."""
    repo_root = repository_root or Path(__file__).resolve().parents[4]
    profile = _load_profile(profile_path)
    profile_id = profile["profile_id"]

    artifacts_root = output_directory or (repo_root / "artifacts" / "verified-active-dreaming")
    artifacts_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_path = artifacts_root / f"report_{profile_id}_{timestamp}.json"

    process = psutil.Process(os.getpid())
    rss_start = process.memory_info().rss

    gates: dict[str, dict[str, Any]] = {}
    temp_dir = tempfile.TemporaryDirectory(prefix="jaya_p03_verify_", ignore_cleanup_errors=True)
    work_dir = Path(temp_dir.name)

    rag = None
    dream = None
    soak_dream = None

    try:
        # Gate 1: Manifest and Contract Integrity
        pillars_manifest = repo_root / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
        if not pillars_manifest.is_file():
            raise ActiveDreamingVerificationError("MANIFEST_MISSING", "40_pillars.yaml not found")
        manifest_data = yaml.safe_load(pillars_manifest.read_text(encoding="utf-8"))
        p3_entry = next((item for item in manifest_data if item.get("id") == 3), None)
        g1_ok = (
            p3_entry is not None
            and p3_entry.get("name") == "Active Dreaming"
            and p3_entry.get("capability_id") == "core.reasoning.dream"
            and p3_entry.get("status") == "VERIFIED"
            and set(p3_entry.get("dependencies", [])) == {15, 23, 8, 33}
            and "verification_profile" in p3_entry
        )
        gates["G01_MANIFEST_INTEGRITY"] = {
            "passed": bool(g1_ok),
            "pillar_id": 3,
            "capability_id": "core.reasoning.dream",
            "status": p3_entry.get("status") if p3_entry else None,
            "dependencies": p3_entry.get("dependencies") if p3_entry else None,
            "verification_profile": p3_entry.get("verification_profile") if p3_entry else None,
        }

        # Setup standard RAG and sandbox test fixtures
        db_path = work_dir / "active_dreaming.sqlite3"
        rag_db_path = work_dir / "agentic_rag.sqlite3"
        rag = AgenticRAGCapability(rag_db_path, None)
        # Seed RAG with valid evidence chunks
        rag.ingest({
            "action": "ingest",
            "source_ref": "thermal_dissipation_experiment_v1",
            "title": "Cryogenic Heat Dissipation Evidence",
            "content": "Cryogenic cooling at 77K reduces thermal noise in superconducting circuits by 92%. Copper heat sinks provide predictable dissipation rates up to 450 Watts per square decimeter.",
        })
        rag.ingest({
            "action": "ingest",
            "source_ref": "nanomaterials_thermal_v1",
            "title": "Graphene Thermal Lattice",
            "content": "Graphene thermal interfaces show anisotropic heat flow along planar lattices under thermal gradients.",
        })

        sandbox = SandboxedImaginationCapability()
        provider = DeterministicCounterfactualProvider()
        dream = ActiveDreamingCapability(db_path, rag, sandbox, provider)

        # Gate 2: Goal Safety and Ethical Policy Gating
        unsafe_goal_caught = False
        try:
            dream.dream({
                "action": "dream",
                "topic": "format C: /fs:ntfs /q to reset state",
                "query": "thermal",
                "constraints": ["1 + 1 == 2"],
            })
        except LocalPillarError as exc:
            if exc.code == "UNSAFE_GOAL_PROHIBITED":
                unsafe_goal_caught = True

        # Test candidate-level safety review filter
        unsafe_provider = DeterministicCounterfactualProvider(unsafe_candidate=True)
        unsafe_dream = ActiveDreamingCapability(
            work_dir / "unsafe_dream.sqlite3", rag, sandbox, unsafe_provider
        )
        unsafe_res = unsafe_dream.dream({
            "action": "dream",
            "topic": "thermal security verification",
            "query": "thermal",
            "constraints": ["1 + 1 == 2"],
            "seed": 42,
            "request_id": "unsafe-candidate-eval",
        })
        candidates_safety = unsafe_res.data["candidates"]
        rejected_c = candidates_safety[0]
        safe_c = candidates_safety[1]
        unsafe_dream.close()

        g2_ok = (
            unsafe_goal_caught
            and rejected_c["label"] == "REJECTED_HYPOTHESIS"
            and rejected_c["verification"] == "REJECTED"
            and rejected_c["retained"] is False
            and rejected_c["rejection_reason"] == "UNSAFE_GOAL_PROHIBITED"
            and safe_c["label"] == "HYPOTHESIS"
            and safe_c["retained"] is True
        )
        gates["G02_GOAL_SAFETY_AND_ETHICAL_GATING"] = {
            "passed": bool(g2_ok),
            "unsafe_goal_blocked": unsafe_goal_caught,
            "candidate_safety_filtered": rejected_c["label"] == "REJECTED_HYPOTHESIS",
            "rejection_reason": rejected_c["rejection_reason"],
        }

        # Gate 3: No Evidence Insufficiency Gating
        no_evidence_caught = False
        try:
            dream.dream({
                "action": "dream",
                "topic": "quantum gravity in empty space",
                "query": "unreferenced_nonexistent_token_123456",
                "constraints": ["1 + 1 == 2"],
            })
        except LocalPillarError as exc:
            if exc.code == "EVIDENCE_UNAVAILABLE":
                no_evidence_caught = True

        gates["G03_NO_EVIDENCE_INSUFFICIENCY_GATING"] = {
            "passed": bool(no_evidence_caught),
            "rejection_code": "EVIDENCE_UNAVAILABLE" if no_evidence_caught else "NONE",
        }

        # Gate 4: Sandboxed Constraint Check
        constraint_failed_caught = False
        try:
            dream.dream({
                "action": "dream",
                "topic": "Cryogenic thermal conductivity",
                "query": "thermal",
                "constraints": ["2 * 2 == 5"],  # Fails math assertion
            })
        except LocalPillarError as exc:
            if exc.code == "CONSTRAINT_REJECTED":
                constraint_failed_caught = True

        gates["G04_SANDBOXED_CONSTRAINT_CHECK"] = {
            "passed": bool(constraint_failed_caught),
            "rejection_code": "CONSTRAINT_REJECTED" if constraint_failed_caught else "NONE",
        }

        # Gate 5: Resource and Budget Cap Gating
        invalid_limit_caught = False
        try:
            dream.dream({
                "action": "dream",
                "topic": "Cryogenic thermal conductivity",
                "query": "thermal",
                "constraints": ["1 + 1 == 2"],
                "candidate_limit": 50,  # Max allowed is 8
            })
        except LocalPillarError as exc:
            if exc.code == "RESOURCE_LIMIT":
                invalid_limit_caught = True

        gates["G05_RESOURCE_AND_BUDGET_CAP_GATING"] = {
            "passed": bool(invalid_limit_caught),
            "max_candidates_enforced": invalid_limit_caught,
        }

        # Gate 6: Model Not Configured Gating
        no_model_dream = ActiveDreamingCapability(
            work_dir / "no_model.sqlite3", rag, sandbox, provider=None
        )
        no_model_caught = False
        try:
            no_model_dream.dream({
                "action": "dream",
                "topic": "Cryogenic thermal conductivity",
                "query": "thermal",
                "constraints": ["1 + 1 == 2"],
            })
        except LocalPillarError as exc:
            if exc.code == "MODEL_NOT_CONFIGURED":
                no_model_caught = True
        no_model_dream.close()

        gates["G06_MODEL_NOT_CONFIGURED_GATING"] = {
            "passed": bool(no_model_caught),
            "rejection_code": "MODEL_NOT_CONFIGURED" if no_model_caught else "NONE",
        }

        # Gate 7: Provider Unavailable or Timeout
        unhealthy_p = DeterministicCounterfactualProvider(simulate_unhealthy=True)
        unhealthy_dream = ActiveDreamingCapability(
            work_dir / "unhealthy.sqlite3", rag, sandbox, unhealthy_p
        )
        unhealthy_caught = False
        try:
            unhealthy_dream.dream({
                "action": "dream",
                "topic": "Cryogenic thermal conductivity",
                "query": "thermal",
                "constraints": ["1 + 1 == 2"],
            })
        except LocalPillarError as exc:
            if exc.code == "MODEL_NOT_CONFIGURED":
                unhealthy_caught = True
        unhealthy_dream.close()

        timeout_p = DeterministicCounterfactualProvider(simulate_timeout=True)
        timeout_dream = ActiveDreamingCapability(
            work_dir / "timeout.sqlite3", rag, sandbox, timeout_p
        )
        timeout_caught = False
        try:
            timeout_dream.dream({
                "action": "dream",
                "topic": "Cryogenic thermal conductivity",
                "query": "thermal",
                "constraints": ["1 + 1 == 2"],
            })
        except LocalPillarError as exc:
            if exc.code == "TIMEOUT":
                timeout_caught = True
        timeout_dream.close()

        gates["G07_PROVIDER_UNAVAILABLE_OR_TIMEOUT"] = {
            "passed": bool(unhealthy_caught and timeout_caught),
            "unhealthy_handled": unhealthy_caught,
            "timeout_handled": timeout_caught,
        }

        # Gate 8: Deterministic Seeded Candidate Reproduction
        run1 = dream.dream({
            "action": "dream",
            "topic": "Deterministic Cryogenic Dissipation",
            "query": "thermal",
            "constraints": ["1 + 1 == 2"],
            "seed": 98765,
            "request_id": "repro-run-1",
            "candidate_limit": 2,
        })
        run2 = dream.dream({
            "action": "dream",
            "topic": "Deterministic Cryogenic Dissipation",
            "query": "thermal",
            "constraints": ["1 + 1 == 2"],
            "seed": 98765,
            "request_id": "repro-run-2",
            "candidate_limit": 2,
        })
        g8_ok = (
            run1.code == "HYPOTHESIS_ARTIFACT_CREATED"
            and run2.code == "HYPOTHESIS_ARTIFACT_CREATED"
            and len(run1.data["candidates"]) == len(run2.data["candidates"])
            and all(
                c1["statement"] == c2["statement"] and c1["candidate_id"] == c2["candidate_id"]
                for c1, c2 in zip(run1.data["candidates"], run2.data["candidates"])
            )
        )
        gates["G08_DETERMINISTIC_SEEDED_CANDIDATE_REPRODUCTION"] = {
            "passed": bool(g8_ok),
            "run1_candidates": len(run1.data["candidates"]),
            "run2_candidates": len(run2.data["candidates"]),
            "reproduced_statements": g8_ok,
        }

        # Gate 9: Request ID Deterministic Replay
        replayed = dream.dream({
            "action": "dream",
            "topic": "Deterministic Cryogenic Dissipation",
            "query": "thermal",
            "constraints": ["1 + 1 == 2"],
            "seed": 98765,
            "request_id": "repro-run-1",
        })
        stored = dream.by_request_id("repro-run-1")
        g9_ok = (
            replayed.code == "REPLAYED_DREAM"
            and stored is not None
            and replayed.data["request_id"] == "repro-run-1"
            and stored["receipt_sha256"] == replayed.data["receipt_sha256"]
        )
        gates["G09_REQUEST_ID_DETERMINISTIC_REPLAY"] = {
            "passed": bool(g9_ok),
            "replay_code": replayed.code,
            "receipt_sha256": replayed.data.get("receipt_sha256"),
        }

        # Gate 10: Hypothesis Labeling and Non-Promotion
        cands = run1.data["candidates"]
        first_c = cands[0]
        g10_ok = (
            first_c["label"] == "HYPOTHESIS"
            and first_c["verification"] == "UNVERIFIED"
            and first_c["executable"] is False
            and run1.data["uncertainty"] == "UNVERIFIED"
            and "MODEL_OUTPUT_IS_NOT_EMPIRICAL_EVIDENCE" in run1.data["warning"]
            and "MODEL_OUTPUT_IS_NOT_EMPIRICAL_EVIDENCE" in run1.data["warnings"]
        )
        gates["G10_HYPOTHESIS_LABELING_AND_NON_PROMOTION"] = {
            "passed": bool(g10_ok),
            "label": first_c["label"],
            "verification": first_c["verification"],
            "executable": first_c["executable"],
            "uncertainty": run1.data["uncertainty"],
            "warning": run1.data["warning"],
        }

        # Gate 11: Quantitative Novelty and Diversity
        dup_run = dream.dream({
            "action": "dream",
            "topic": "Deterministic Cryogenic Dissipation",
            "query": "thermal",
            "constraints": ["1 + 1 == 2"],
            "seed": 98765,
            "request_id": "dup-run-eval",
            "candidate_limit": 2,
        })
        dup_metrics = dup_run.data["metrics"]
        g11_ok = (
            dup_metrics["novelty_score"] == 0.0
            and dup_metrics["accepted_candidates"] == 0
            and dup_run.data["candidates"][0]["rejection_reason"] == "DUPLICATE_CANDIDATE"
            and run1.data["metrics"]["novelty_score"] == 1.0
            and run1.data["metrics"]["diversity_score"] > 0.0
        )
        gates["G11_QUANTITATIVE_NOVELTY_AND_DIVERSITY"] = {
            "passed": bool(g11_ok),
            "initial_novelty_score": run1.data["metrics"]["novelty_score"],
            "duplicate_novelty_score": dup_metrics["novelty_score"],
            "diversity_score": run1.data["metrics"]["diversity_score"],
        }

        # Gate 12: Tamper-Evident WAL Persistence
        conn = sqlite3.connect(str(db_path))
        with conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            schema_version = conn.execute("SELECT version FROM dream_schema WHERE singleton = 1").fetchone()[0]
            count = conn.execute("SELECT COUNT(*) FROM dream_artifacts").fetchone()[0]
        conn.close()

        # Tamper row directly to test integrity verification
        tamper_req_id = "tamper-check-target"
        dream.dream({
            "action": "dream",
            "topic": "Tamper Target Dream",
            "query": "thermal",
            "constraints": ["1 + 1 == 2"],
            "seed": 111,
            "request_id": tamper_req_id,
        })
        tamper_conn = sqlite3.connect(str(db_path))
        with tamper_conn:
            tamper_conn.execute(
                "UPDATE dream_artifacts SET seed = 999999 WHERE request_id = ?",
                (tamper_req_id,),
            )
        tamper_conn.close()

        tamper_caught = False
        try:
            dream.by_request_id(tamper_req_id)
        except LocalPillarError as exc:
            if exc.code == "STORAGE_CORRUPT":
                tamper_caught = True

        g12_ok = (
            str(journal_mode).lower() == "wal"
            and int(schema_version) == 1
            and count > 0
            and tamper_caught is True
        )
        gates["G12_TAMPER_EVIDENT_WAL_PERSISTENCE"] = {
            "passed": bool(g12_ok),
            "journal_mode": journal_mode,
            "schema_version": schema_version,
            "artifact_count": count,
            "tamper_detected": tamper_caught,
        }

        # Gate 13: Conflicting Evidence Handling
        conflict_rag_path = work_dir / "conflict_rag.sqlite3"
        conflict_rag = AgenticRAGCapability(conflict_rag_path, None)
        conflict_rag.ingest({
            "action": "ingest",
            "source_ref": "conflict_source_v1",
            "title": "Contradictory Physics Claims",
            "content": "Claim A: Supercooling increases lattice conductivity exponentially. Direct contradiction: Supercooling exhibits severe thermal conflict and terminates flow.",
        })
        conflict_dream = ActiveDreamingCapability(
            work_dir / "conflict_dream.sqlite3", conflict_rag, sandbox, provider
        )
        conflict_res = conflict_dream.dream({
            "action": "dream",
            "topic": "Supercooling contradictory properties",
            "query": "supercooling",
            "constraints": ["1 + 1 == 2"],
            "seed": 55,
            "request_id": "conflict-test-run",
        })
        conflict_dream.close()
        conflict_rag.close()

        g13_ok = (
            conflict_res.data["uncertainty"] == "EVIDENCE_CONFLICT"
            and "EVIDENCE_CONFLICT_DETECTED" in conflict_res.data["warnings"]
        )
        gates["G13_CONFLICTING_EVIDENCE_HANDLING"] = {
            "passed": bool(g13_ok),
            "uncertainty": conflict_res.data.get("uncertainty"),
            "warnings": conflict_res.data.get("warnings"),
        }

        # Gate 14: Canonical Core Runtime Wiring
        # Verify AdvancedPillarCapabilityService manifests and DREAM_CAPABILITY_ID dispatch
        adv_service_dir = work_dir / "adv_service_root"
        adv_service_dir.mkdir(parents=True, exist_ok=True)
        adv_service = AdvancedPillarCapabilityService(adv_service_dir)
        manifest_ids = [m.capability_id for m in adv_service.manifests()]
        g14_manifest_ok = DREAM_CAPABILITY_ID in manifest_ids

        # Wire deterministic provider into adv_service.dream and test execution dispatch
        adv_service.dream.provider = provider
        # Seed adv_service RAG with evidence chunk
        adv_service.rag.ingest({
            "action": "ingest",
            "source_ref": "adv_evidence_chunk",
            "title": "Canonical Advanced Ingest",
            "content": "Superconducting quantum bits experience decoherence from high frequency ambient electromagnetic noise.",
        })
        adv_res = adv_service.execute(
            DREAM_CAPABILITY_ID,
            {
                "action": "dream",
                "topic": "Superconducting quantum bit noise",
                "query": "quantum",
                "constraints": ["10 + 20 == 30"],
                "seed": 777,
                "request_id": "adv-service-dream-1",
            },
        )
        adv_service.close()

        g14_ok = (
            g14_manifest_ok
            and isinstance(adv_res, LocalPillarResult)
            and adv_res.pillar_id == "P003"
            and adv_res.code == "HYPOTHESIS_ARTIFACT_CREATED"
            and adv_res.data.get("topic") == "Superconducting quantum bit noise"
        )
        gates["G14_CANONICAL_RUNTIME_WIRING"] = {
            "passed": bool(g14_ok),
            "manifest_registered": g14_manifest_ok,
            "pillar_id": adv_res.pillar_id if isinstance(adv_res, LocalPillarResult) else None,
            "code": adv_res.code if isinstance(adv_res, LocalPillarResult) else None,
        }

        # Gate 15: Soak Performance and Energy Metering
        soak_iterations = profile["soak"]["iterations"]
        soak_db_path = work_dir / "soak_dream.sqlite3"
        soak_dream = ActiveDreamingCapability(soak_db_path, rag, sandbox, provider)

        latencies_ms: list[float] = []
        with _energy_sampler() as energy_data:
            for idx in range(soak_iterations):
                t_start = time.perf_counter()
                res = soak_dream.dream({
                    "action": "dream",
                    "topic": f"Thermal soak exploration iteration {idx}",
                    "query": "thermal",
                    "constraints": [f"{idx} + 1 == {idx + 1}"],
                    "seed": 1000 + idx,
                    "request_id": f"soak-req-{idx}",
                    "candidate_limit": 2,
                })
                latencies_ms.append((time.perf_counter() - t_start) * 1000.0)
                if res.code != "HYPOTHESIS_ARTIFACT_CREATED":
                    raise ActiveDreamingVerificationError("SOAK_FAILURE", f"failed at iteration {idx}")

        mean_latency = sum(latencies_ms) / len(latencies_ms)
        p95_latency = sorted(latencies_ms)[int(len(latencies_ms) * 0.95)]
        rss_end = process.memory_info().rss
        rss_growth = max(0, rss_end - rss_start)

        soak_db_bytes = soak_db_path.stat().st_size if soak_db_path.is_file() else 0
        bytes_per_rec = soak_db_bytes / max(1, soak_iterations)
        joules = float(energy_data.get("energy_joules", 0.0))
        joules_per_rec = joules / max(1, soak_iterations)

        soak_cfg = profile["soak"]
        g15_ok = (
            mean_latency <= soak_cfg["max_mean_latency_ms"]
            and rss_growth <= soak_cfg["max_rss_growth_bytes"]
            and bytes_per_rec <= soak_cfg["max_database_bytes_per_record"]
            and joules_per_rec <= soak_cfg["max_package_joules_per_record"]
        )
        gates["G15_SOAK_PERFORMANCE_AND_ENERGY"] = {
            "passed": bool(g15_ok),
            "iterations": soak_iterations,
            "mean_latency_ms": round(mean_latency, 3),
            "p95_latency_ms": round(p95_latency, 3),
            "rss_growth_bytes": rss_growth,
            "database_bytes_per_record": round(bytes_per_rec, 2),
            "energy_joules_total": round(joules, 4),
            "energy_joules_per_record": round(joules_per_rec, 5),
            "energy_method": energy_data.get("energy_method"),
        }

    finally:
        if dream is not None:
            dream.close()
        if soak_dream is not None:
            soak_dream.close()
        if rag is not None:
            rag.close()
        temp_dir.cleanup()

    all_passed = all(g.get("passed", False) for g in gates.values())
    overall_status = "VERIFIED" if all_passed else "FAILED"

    report: dict[str, Any] = {
        "schema_version": 1,
        "profile_id": profile_id,
        "pillar_id": 3,
        "pillar_name": "Active Dreaming",
        "capability_id": "core.reasoning.dream",
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "approver": approver,
        "git_commit": _git_commit(repo_root),
        "host_platform": platform.platform(),
        "python_version": platform.python_version(),
        "status": overall_status,
        "gates_summary": {
            "total": len(gates),
            "passed": sum(1 for g in gates.values() if g.get("passed")),
            "failed": sum(1 for g in gates.values() if not g.get("passed")),
        },
        "gates": gates,
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path, report
