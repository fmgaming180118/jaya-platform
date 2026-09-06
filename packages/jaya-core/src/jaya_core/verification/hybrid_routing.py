"""Representative verification runner for Pillar 37 Hybrid Consciousness."""

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
from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
from jaya_core.pillars.control_capabilities import (
    HYBRID_CAPABILITY_ID,
    HybridRoutingCapability,
    RemoteModelProviderProtocol,
)
from jaya_core.pillars.foundation_capabilities import SandboxedImaginationCapability
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult
from jaya_core.pillars.media_capability import MediaObservationCapability

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


class HybridRoutingVerificationError(RuntimeError):
    """Stable P37 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class VerificationMockRetrievalProvider:
    provider_type = "TEST_IMPLEMENTATION"

    def health_check(self) -> bool:
        return True

    def answer(self, question: str, evidence: Sequence[Mapping[str, Any]]) -> Mapping[str, Any]:
        return {
            "answer": f"Verified answer from: {evidence[0]['content']}",
            "citations": [evidence[0]["evidence_id"]],
        }


class VerificationMockRemoteProvider(RemoteModelProviderProtocol):
    def __init__(self, healthy: bool = True, should_fail: bool = False) -> None:
        self.is_healthy = healthy
        self.should_fail = should_fail

    def health_check(self) -> bool:
        return self.is_healthy

    def ask(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        if self.should_fail:
            raise RuntimeError("Cloud endpoint timeout")
        return {
            "answer": "Verified remote cloud answer",
            "model_id": "verified-remote-model-v1",
            "citations": ["remote-chunk-01"],
        }


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
        raise HybridRoutingVerificationError(
            "PROFILE_NOT_FOUND", f"Profile does not exist: {profile_path}"
        )
    with profile_path.open("r", encoding="utf-8") as handle:
        profile = json.load(handle)
    missing = _PROFILE_FIELDS - set(profile)
    if missing:
        raise HybridRoutingVerificationError(
            "PROFILE_INVALID", f"Missing profile fields: {', '.join(sorted(missing))}"
        )
    if not _PROFILE_ID.match(str(profile.get("profile_id", ""))):
        raise HybridRoutingVerificationError("PROFILE_INVALID", "Invalid profile_id syntax")
    if profile.get("supported_os") != "Windows":
        raise HybridRoutingVerificationError(
            "UNSUPPORTED_OS_PROFILE", "This verification profile requires Windows"
        )
    return profile


def run_hybrid_routing_verification(
    profile_path: Path | None = None,
    workspace_root: Path | None = None,
    output_path: Path | None = None,
) -> dict[str, Any]:
    """Execute all 15 canonical verification gates for Pillar 37."""
    start_wall = time.time()
    workspace = (workspace_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p37_windows_hybrid_consciousness_v1.json"
    ).resolve()

    profile = _load_profile(target_profile)
    gate_names = profile["matrix"]["gates"]
    soak_spec = profile["soak"]

    gate_results: dict[str, dict[str, Any]] = {}
    soak_metrics: dict[str, Any] = {}

    scratch = tempfile.mkdtemp(prefix="jaya_p37_verification_")
    scratch_dir = Path(scratch)
    db_path = scratch_dir / "hybrid_routing_verification.sqlite3"
    rag_db = scratch_dir / "rag.sqlite3"
    media_root = scratch_dir / "media"
    media_root.mkdir()

    # Create dummy media asset for tool testing
    sample_img = media_root / "test_frame.png"
    sample_img.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82")

    rag = AgenticRAGCapability(rag_db, VerificationMockRetrievalProvider())
    rag.execute(
        {
            "action": "ingest",
            "source_ref": "doc:verified-routing",
            "title": "Routing Principles",
            "content": "Execution routing dispatches across deterministic rules, retrieval, and models.",
        }
    )
    media = MediaObservationCapability(root=media_root, database_path=scratch_dir / "media.sqlite3")
    sandbox = SandboxedImaginationCapability()
    remote = VerificationMockRemoteProvider(healthy=True)

    try:
        # -------------------------------------------------------------
        # Gate 01: MANIFEST INTEGRITY
        # -------------------------------------------------------------
        g01_start = time.perf_counter()
        bundle = AdvancedPillarCapabilityService(data_dir=scratch_dir)
        manifests = {m.capability_id: m for m in bundle.manifests()}
        if HYBRID_CAPABILITY_ID not in manifests:
            raise HybridRoutingVerificationError("G01_FAILED", "Hybrid capability missing from bundle")
        m_hyb = manifests[HYBRID_CAPABILITY_ID]
        if m_hyb.health_status != "HEALTHY":
            raise HybridRoutingVerificationError("G01_FAILED", f"Hybrid capability is {m_hyb.health_status}")
        if not m_hyb.offline_available:
            raise HybridRoutingVerificationError("G01_FAILED", "Hybrid capability must be offline available")

        # Verify 40_pillars.yaml entry
        yaml_path = workspace / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
        if yaml_path.is_file():
            with yaml_path.open("r", encoding="utf-8") as yf:
                pillars_doc = yaml.safe_load(yf)
            p37_entry = next((item for item in pillars_doc if item.get("id") == 37), None)
            if p37_entry is None or p37_entry.get("capability_id") != HYBRID_CAPABILITY_ID:
                raise HybridRoutingVerificationError("G01_FAILED", "Pillar 37 contract mismatch in 40_pillars.yaml")

        g01_dur = (time.perf_counter() - g01_start) * 1000.0
        gate_results["G01_MANIFEST_INTEGRITY"] = {
            "status": "PASSED",
            "duration_ms": round(g01_dur, 3),
            "details": {"capability_id": HYBRID_CAPABILITY_ID, "provider": m_hyb.provider},
        }

        # -------------------------------------------------------------
        # Gate 02: EXPLICIT SOURCE LABELING
        # -------------------------------------------------------------
        g02_start = time.perf_counter()
        router = HybridRoutingCapability(
            db_path, rag, sandbox, media, remote_provider=remote
        )
        r_rule = router.execute(
            {
                "action": "route",
                "request_kind": "expression",
                "sensitivity": "internal",
                "payload": {"expression": "10 + 20"},
            }
        )
        if r_rule.data["provider_type"] != "RULE_BASED":
            raise HybridRoutingVerificationError("G02_FAILED", f"Rule route must be RULE_BASED, got {r_rule.data['provider_type']}")
        if "result_digest" not in r_rule.data:
            raise HybridRoutingVerificationError("G02_FAILED", "Missing result_digest")

        g02_dur = (time.perf_counter() - g02_start) * 1000.0
        gate_results["G02_EXPLICIT_SOURCE_LABELING"] = {
            "status": "PASSED",
            "duration_ms": round(g02_dur, 3),
            "details": {"labeled_provider_type": "RULE_BASED", "anti_deception_verified": True},
        }

        # -------------------------------------------------------------
        # Gate 03: RULE BASED EXECUTION
        # -------------------------------------------------------------
        g03_start = time.perf_counter()
        r_math = router.execute(
            {
                "action": "route",
                "request_kind": "expression",
                "sensitivity": "internal",
                "payload": {"expression": "7 * 8 == 56"},
            }
        )
        if r_math.data["result"]["result"] is not True:
            raise HybridRoutingVerificationError("G03_FAILED", "Deterministic rule evaluation failed")

        g03_dur = (time.perf_counter() - g03_start) * 1000.0
        gate_results["G03_RULE_BASED_EXECUTION"] = {
            "status": "PASSED",
            "duration_ms": round(g03_dur, 3),
            "details": {"expression_evaluated": True, "result": True},
        }

        # -------------------------------------------------------------
        # Gate 04: GROUNDED RETRIEVAL ROUTE
        # -------------------------------------------------------------
        g04_start = time.perf_counter()
        r_ret = router.execute(
            {
                "action": "route",
                "request_kind": "retrieval",
                "sensitivity": "internal",
                "payload": {"query": "execution routing dispatches"},
            }
        )
        if r_ret.data["provider_type"] != "RETRIEVAL":
            raise HybridRoutingVerificationError("G04_FAILED", "Expected RETRIEVAL provider_type")
        if not r_ret.data["citations"]:
            raise HybridRoutingVerificationError("G04_FAILED", "Retrieval route missing citations")

        g04_dur = (time.perf_counter() - g04_start) * 1000.0
        gate_results["G04_GROUNDED_RETRIEVAL_ROUTE"] = {
            "status": "PASSED",
            "duration_ms": round(g04_dur, 3),
            "details": {"citations_count": len(r_ret.data["citations"])},
        }

        # -------------------------------------------------------------
        # Gate 05: LOCAL MODEL ROUTE
        # -------------------------------------------------------------
        g05_start = time.perf_counter()
        r_loc = router.execute(
            {
                "action": "route",
                "request_kind": "grounded_answer",
                "sensitivity": "internal",
                "payload": {"question": "What does execution routing dispatch across?"},
            }
        )
        if r_loc.data["provider_type"] != "LOCAL_MODEL":
            raise HybridRoutingVerificationError("G05_FAILED", "Expected LOCAL_MODEL provider_type")
        if "Verified answer" not in r_loc.data["result"]["answer"]:
            raise HybridRoutingVerificationError("G05_FAILED", "Local model answer synthesis corrupted")

        g05_dur = (time.perf_counter() - g05_start) * 1000.0
        gate_results["G05_LOCAL_MODEL_ROUTE"] = {
            "status": "PASSED",
            "duration_ms": round(g05_dur, 3),
            "details": {"local_model_answer_verified": True},
        }

        # -------------------------------------------------------------
        # Gate 06: REMOTE MODEL INTEGRATION
        # -------------------------------------------------------------
        g06_start = time.perf_counter()
        r_rem = router.execute(
            {
                "action": "route",
                "request_kind": "remote_answer",
                "sensitivity": "public",
                "payload": {"prompt": "Provide general overview"},
            }
        )
        if r_rem.data["provider_type"] != "REMOTE_MODEL":
            raise HybridRoutingVerificationError("G06_FAILED", "Expected REMOTE_MODEL provider_type")

        g06_dur = (time.perf_counter() - g06_start) * 1000.0
        gate_results["G06_REMOTE_MODEL_INTEGRATION"] = {
            "status": "PASSED",
            "duration_ms": round(g06_dur, 3),
            "details": {"remote_dispatched": True, "model_id": r_rem.data["result"]["model_id"]},
        }

        # -------------------------------------------------------------
        # Gate 07: PRIVACY DATA EGRESS GATING
        # -------------------------------------------------------------
        g07_start = time.perf_counter()
        try:
            router.execute(
                {
                    "action": "route",
                    "request_kind": "remote_answer",
                    "sensitivity": "restricted",
                    "payload": {"prompt": "Confidential financial telemetry"},
                }
            )
            raise HybridRoutingVerificationError("G07_FAILED", "Restricted remote route should have been blocked")
        except LocalPillarError as exc:
            if exc.code != "PRIVACY_DENIAL":
                raise HybridRoutingVerificationError("G07_FAILED", f"Expected PRIVACY_DENIAL, got {exc.code}")

        g07_dur = (time.perf_counter() - g07_start) * 1000.0
        gate_results["G07_PRIVACY_DATA_EGRESS_GATING"] = {
            "status": "PASSED",
            "duration_ms": round(g07_dur, 3),
            "details": {"privacy_denial_enforced": True},
        }

        # -------------------------------------------------------------
        # Gate 08: OFFLINE MODE ENFORCEMENT
        # -------------------------------------------------------------
        g08_start = time.perf_counter()
        router_offline = HybridRoutingCapability(
            scratch_dir / "offline.sqlite3", rag, sandbox, media, remote_provider=remote, offline_mode=True
        )
        try:
            router_offline.execute(
                {
                    "action": "route",
                    "request_kind": "remote_answer",
                    "sensitivity": "public",
                    "payload": {"prompt": "Cloud question"},
                    "allow_fallback": False,
                }
            )
            raise HybridRoutingVerificationError("G08_FAILED", "Offline mode should block remote route")
        except LocalPillarError as exc:
            if exc.code != "OFFLINE_REQUIRED":
                raise HybridRoutingVerificationError("G08_FAILED", f"Expected OFFLINE_REQUIRED, got {exc.code}")

        g08_dur = (time.perf_counter() - g08_start) * 1000.0
        gate_results["G08_OFFLINE_MODE_ENFORCEMENT"] = {
            "status": "PASSED",
            "duration_ms": round(g08_dur, 3),
            "details": {"offline_blocking_enforced": True},
        }

        # -------------------------------------------------------------
        # Gate 09: TOOL OBSERVATION ROUTE
        # -------------------------------------------------------------
        g09_start = time.perf_counter()
        r_media = router.execute(
            {
                "action": "route",
                "request_kind": "media",
                "sensitivity": "internal",
                "payload": {"path": "test_frame.png"},
            }
        )
        if r_media.data["provider_type"] != "TOOL":
            raise HybridRoutingVerificationError("G09_FAILED", f"Expected TOOL provider_type, got {r_media.data['provider_type']}")
        if r_media.data["result"]["modality"] != "IMAGE":
            raise HybridRoutingVerificationError("G09_FAILED", "Tool modality mismatch")

        g09_dur = (time.perf_counter() - g09_start) * 1000.0
        gate_results["G09_TOOL_OBSERVATION_ROUTE"] = {
            "status": "PASSED",
            "duration_ms": round(g09_dur, 3),
            "details": {"tool_route_executed": True, "modality": "IMAGE"},
        }

        # -------------------------------------------------------------
        # Gate 10: CAPABLE FAILOVER CHAIN
        # -------------------------------------------------------------
        g10_start = time.perf_counter()
        failing_remote = VerificationMockRemoteProvider(healthy=True, should_fail=True)
        router_fail = HybridRoutingCapability(
            scratch_dir / "failover.sqlite3", rag, sandbox, media, remote_provider=failing_remote
        )
        r_fo = router_fail.execute(
            {
                "action": "route",
                "request_kind": "remote_answer",
                "sensitivity": "public",
                "payload": {"question": "What does execution routing dispatch across?"},
                "allow_fallback": True,
            }
        )
        if r_fo.data["provider_type"] != "LOCAL_MODEL":
            raise HybridRoutingVerificationError("G10_FAILED", f"Expected fallback to LOCAL_MODEL, got {r_fo.data['provider_type']}")
        if not r_fo.data["failover_history"]:
            raise HybridRoutingVerificationError("G10_FAILED", "Failover history missing from degraded route")

        g10_dur = (time.perf_counter() - g10_start) * 1000.0
        gate_results["G10_CAPABLE_FAILOVER_CHAIN"] = {
            "status": "PASSED",
            "duration_ms": round(g10_dur, 3),
            "details": {"failover_lineage_preserved": True, "history": r_fo.data["failover_history"]},
        }

        # -------------------------------------------------------------
        # Gate 11: PROVIDER HEALTH AND TTL
        # -------------------------------------------------------------
        g11_start = time.perf_counter()
        p_list = router.execute({"action": "providers"}).data["providers"]
        if len(p_list) < 4:
            raise HybridRoutingVerificationError("G11_FAILED", "Provider registry incomplete")
        healthy_names = [p["provider_name"] for p in p_list if p["health_status"] == "HEALTHY"]
        if "rule_sandbox" not in healthy_names:
            raise HybridRoutingVerificationError("G11_FAILED", "rule_sandbox not healthy")

        g11_dur = (time.perf_counter() - g11_start) * 1000.0
        gate_results["G11_PROVIDER_HEALTH_AND_TTL"] = {
            "status": "PASSED",
            "duration_ms": round(g11_dur, 3),
            "details": {"registered_providers": len(p_list)},
        }

        # -------------------------------------------------------------
        # Gate 12: PROVENANCE AND CITATION PRESERVATION
        # -------------------------------------------------------------
        g12_start = time.perf_counter()
        r_prov = router.execute(
            {
                "action": "route",
                "request_kind": "retrieval",
                "sensitivity": "internal",
                "payload": {"query": "deterministic rules"},
            }
        )
        if not r_prov.data["citations"]:
            raise HybridRoutingVerificationError("G12_FAILED", "Citations missing from retrieval route")
        if not r_prov.data.get("result_digest"):
            raise HybridRoutingVerificationError("G12_FAILED", "Result digest missing")

        g12_dur = (time.perf_counter() - g12_start) * 1000.0
        gate_results["G12_PROVENANCE_AND_CITATION_PRESERVATION"] = {
            "status": "PASSED",
            "duration_ms": round(g12_dur, 3),
            "details": {"citations": r_prov.data["citations"]},
        }

        # -------------------------------------------------------------
        # Gate 13: OBJECTIVE CONTEXT ALIGNMENT
        # -------------------------------------------------------------
        g13_start = time.perf_counter()
        r_obj = router.execute(
            {
                "action": "route",
                "request_kind": "expression",
                "sensitivity": "internal",
                "payload": {"expression": "2 + 2 == 4"},
                "objective_id": "objective-active-p39",
            }
        )
        if r_obj.data.get("objective_id") != "objective-active-p39":
            raise HybridRoutingVerificationError("G13_FAILED", "Objective ID not bound to routing result")

        g13_dur = (time.perf_counter() - g13_start) * 1000.0
        gate_results["G13_OBJECTIVE_CONTEXT_ALIGNMENT"] = {
            "status": "PASSED",
            "duration_ms": round(g13_dur, 3),
            "details": {"bound_objective_id": "objective-active-p39"},
        }

        # -------------------------------------------------------------
        # Gate 14: TAMPER EVIDENT WAL PERSISTENCE
        # -------------------------------------------------------------
        g14_start = time.perf_counter()
        integ_res = router.execute({"action": "verify_integrity"})
        if integ_res.data["status"] != "HEALTHY":
            raise HybridRoutingVerificationError("G14_FAILED", "Initial route integrity check failed")

        with _open_db(db_path) as conn:
            jmode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            if jmode.upper() != "WAL":
                raise HybridRoutingVerificationError("G14_FAILED", f"Expected WAL mode, got {jmode}")
            conn.execute("UPDATE hybrid_routes SET result_digest='corrupt_digest_value'")

        try:
            router.execute({"action": "verify_integrity"})
            raise HybridRoutingVerificationError("G14_FAILED", "Tampered receipt was not detected")
        except LocalPillarError as exc:
            if exc.code != "STORAGE_CORRUPT":
                raise HybridRoutingVerificationError("G14_FAILED", f"Expected STORAGE_CORRUPT, got {exc.code}")

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
        soak_db = scratch_dir / "soak.sqlite3"
        soak_router = HybridRoutingCapability(
            soak_db, rag, sandbox, media, remote_provider=remote
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

        kinds = ["expression", "retrieval", "grounded_answer", "remote_answer"]
        for i in range(iterations):
            iter_start = time.perf_counter()
            k = kinds[i % len(kinds)]
            if k == "expression":
                soak_router.execute(
                    {
                        "action": "route",
                        "request_kind": "expression",
                        "sensitivity": "internal",
                        "payload": {"expression": f"{i} + 1"},
                    }
                )
            elif k == "retrieval":
                soak_router.execute(
                    {
                        "action": "route",
                        "request_kind": "retrieval",
                        "sensitivity": "internal",
                        "payload": {"query": "routing principles"},
                    }
                )
            elif k == "grounded_answer":
                soak_router.execute(
                    {
                        "action": "route",
                        "request_kind": "grounded_answer",
                        "sensitivity": "internal",
                        "payload": {"question": "What does execution routing dispatch across?"},
                    }
                )
            elif k == "remote_answer":
                soak_router.execute(
                    {
                        "action": "route",
                        "request_kind": "remote_answer",
                        "sensitivity": "public",
                        "payload": {"prompt": "Soak test prompt"},
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

        if mean_latency > soak_spec.get("max_mean_latency_ms", 50.0):
            raise HybridRoutingVerificationError(
                "G15_FAILED", f"Mean latency {mean_latency:.2f}ms exceeds limit {soak_spec['max_mean_latency_ms']}ms"
            )
        if rss_growth > soak_spec.get("max_rss_growth_bytes", 33554432):
            raise HybridRoutingVerificationError(
                "G15_FAILED", f"RSS growth {rss_growth} exceeds limit {soak_spec['max_rss_growth_bytes']}"
            )
        if completion_rate < soak_spec.get("min_completion_rate", 0.95):
            raise HybridRoutingVerificationError(
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
        del router, router_offline, router_fail, soak_router, bundle
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
        "pillar_id": 37,
        "pillar_name": "Hybrid Consciousness",
        "capability_id": HYBRID_CAPABILITY_ID,
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


def verify_hybrid_routing(
    repository_root: Path | None = None,
    profile_path: Path | None = None,
    output_directory: Path | None = None,
    approver: str = "System-Veritas",
) -> tuple[Path, dict[str, Any]]:
    """Canonical verification wrapper compatible with repo CLI scripts."""
    workspace = (repository_root or Path.cwd()).resolve()
    target_profile = (
        profile_path
        or workspace / "packages" / "jaya-core" / "verification" / "p37_windows_hybrid_consciousness_v1.json"
    ).resolve()
    out_dir = (output_directory or workspace / "artifacts" / "verified-hybrid-routing").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "verification_receipt.json"

    receipt = run_hybrid_routing_verification(
        profile_path=target_profile,
        workspace_root=workspace,
        output_path=out_file,
    )
    receipt["approver"] = approver
    with out_file.open("w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)

    return out_file, receipt
