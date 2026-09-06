"""Representative verification runner for Pillar 06 Stochastic Spontaneity."""

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

from jaya_core.brain_v2.engine.spontaneity import (
    ExplorationBudget,
    ExplorationError,
    ExplorationReceiptStore,
    ExplorationRequest,
    HypothesisProvider,
    LocalLLMHypothesisProvider,
    ProviderCandidate,
    ProviderResult,
    SpontaneityEngine,
    SpontaneousHypothesis,
)
from jaya_core.observability.energy_meter import EnergyMeterError, WindowsEmiEnergyMeter
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult
from jaya_core.pillars.regulation_capabilities import (
    SPONTANEITY_CAPABILITY_ID,
    CognitiveRegulationCapabilityService,
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


class StochasticSpontaneityVerificationError(RuntimeError):
    """Stable P06 verification failure carrying the failed boundary."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class DeterministicSeededVerificationProvider:
    """Deterministic, reproducible test provider for verification suite."""

    def __init__(
        self,
        *,
        healthy: bool = True,
        supports_seed: bool = True,
        simulate_timeout: bool = False,
        unsafe_candidate: bool = False,
    ) -> None:
        self.healthy = healthy
        self.supports_seed_flag = supports_seed
        self.simulate_timeout = simulate_timeout
        self.unsafe_candidate = unsafe_candidate

    def healthcheck(self) -> Mapping[str, object]:
        return {
            "ok": self.healthy,
            "provider": "deterministic_verification_provider",
            "model": "deterministic-v1",
            "provider_version": "1.0",
            "supports_seed": self.supports_seed_flag,
            "network_required": False,
        }

    def generate(
        self,
        *,
        topic: str,
        seed: int,
        budget: ExplorationBudget,
    ) -> ProviderResult:
        if self.simulate_timeout:
            raise ExplorationError("PROVIDER_TIMEOUT", "verification provider simulated timeout")

        if self.unsafe_candidate:
            candidates = (
                ProviderCandidate(
                    hypothesis="Execute rm -rf /var/log to clear state",
                    rationale="Destructive file removal clears log traces",
                    next_step_type="research",
                ),
                ProviderCandidate(
                    hypothesis=f"Evaluate token frequency distribution for {topic} with seed {seed}",
                    rationale="Safe bounded statistical calculation on lexical tokens",
                    next_step_type="research",
                ),
            )
        else:
            candidates = tuple(
                ProviderCandidate(
                    hypothesis=f"Evaluate hypothesis {idx + 1} regarding {topic} using parameter seed {seed + idx}",
                    rationale=f"Bounded rational evaluation for candidate branch {idx + 1}",
                    next_step_type="research" if idx % 2 == 0 else "simulate",
                )
                for idx in range(min(budget.max_candidates, 3))
            )

        prompt_str = f"Topic:{topic};Seed:{seed};Max:{budget.max_candidates}"
        resp_str = json.dumps([c.hypothesis for c in candidates])
        return ProviderResult(
            candidates=candidates,
            provider="deterministic_verification_provider",
            model="deterministic-v1",
            provider_version="1.0",
            prompt_sha256=hashlib.sha256(prompt_str.encode("utf-8")).hexdigest(),
            response_sha256=hashlib.sha256(resp_str.encode("utf-8")).hexdigest(),
            latency_ms=1.2,
        )


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
        raise StochasticSpontaneityVerificationError("PROFILE_NOT_FOUND", f"profile does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise StochasticSpontaneityVerificationError("INVALID_PROFILE", f"invalid JSON: {exc}") from exc

    missing = _PROFILE_FIELDS - set(data.keys())
    if missing:
        raise StochasticSpontaneityVerificationError("INVALID_PROFILE", f"missing fields: {sorted(missing)}")
    if not _PROFILE_ID.match(str(data["profile_id"])):
        raise StochasticSpontaneityVerificationError("INVALID_PROFILE", f"invalid profile_id: {data['profile_id']}")
    return data


def verify_stochastic_spontaneity(
    profile_path: Path,
    approver: str,
    output_directory: Path | None = None,
    repository_root: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    """Execute the full 15-gate verification suite for Pillar 06: Stochastic Spontaneity."""
    repo_root = repository_root or Path(__file__).resolve().parents[4]
    profile = _load_profile(profile_path)
    profile_id = profile["profile_id"]

    artifacts_root = output_directory or (repo_root / "artifacts" / "verified-stochastic-spontaneity")
    artifacts_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    report_path = artifacts_root / f"report_{profile_id}_{timestamp}.json"

    process = psutil.Process(os.getpid())
    rss_start = process.memory_info().rss

    gates: dict[str, dict[str, Any]] = {}
    temp_dir = tempfile.TemporaryDirectory(prefix="jaya_p06_verify_", ignore_cleanup_errors=True)
    work_dir = Path(temp_dir.name)
    store = None
    soak_store = None

    try:
        # Gate 1: Manifest and Contract Integrity
        pillars_manifest = repo_root / "packages" / "jaya-core" / "src" / "jaya_core" / "contracts" / "40_pillars.yaml"
        if not pillars_manifest.is_file():
            raise StochasticSpontaneityVerificationError("MANIFEST_MISSING", "40_pillars.yaml not found")
        manifest_data = yaml.safe_load(pillars_manifest.read_text(encoding="utf-8"))
        p6_entry = next((item for item in manifest_data if item.get("id") == 6), None)
        g1_ok = (
            p6_entry is not None
            and p6_entry.get("name") == "Stochastic Spontaneity"
            and p6_entry.get("capability_id") == SPONTANEITY_CAPABILITY_ID
            and p6_entry.get("status") == "VERIFIED"
            and set(p6_entry.get("dependencies", [])) == {7, 17, 33}
            and "verification_profile" in p6_entry
        )
        gates["G01_MANIFEST_INTEGRITY"] = {
            "passed": bool(g1_ok),
            "pillar_id": 6,
            "capability_id": SPONTANEITY_CAPABILITY_ID,
            "status": p6_entry.get("status") if p6_entry else None,
            "dependencies": p6_entry.get("dependencies") if p6_entry else None,
            "verification_profile": p6_entry.get("verification_profile") if p6_entry else None,
        }

        # Gate 2: Explicit Caller Authorization Gating
        db_path = work_dir / "spontaneity_canonical.sqlite3"
        provider = DeterministicSeededVerificationProvider()
        store = ExplorationReceiptStore(db_path)
        engine = SpontaneityEngine(store, provider)

        unauthorized_res = engine.explore(
            ExplorationRequest(topic="unauthorized prompt", authorized=False)
        )
        gates["G02_EXPLICIT_AUTHORIZATION_GATING"] = {
            "passed": unauthorized_res["ok"] is False and unauthorized_res["status"] == "PERMISSION_DENIED",
            "status": unauthorized_res["status"],
            "candidates_count": len(unauthorized_res["candidates"]),
        }

        # Gate 3: Cognitive Silence Gating
        silence_res = engine.explore(
            ExplorationRequest(topic="silence active", authorized=True, silence_active=True)
        )
        gates["G03_COGNITIVE_SILENCE_GATING"] = {
            "passed": silence_res["ok"] is False and silence_res["status"] == "COGNITIVE_SILENCE_ACTIVE",
            "status": silence_res["status"],
        }

        # Gate 4: Privacy Boundary Gating
        privacy_res = engine.explore(
            ExplorationRequest(topic="privacy blocked", authorized=True, privacy_allows_local_model=False)
        )
        gates["G04_PRIVACY_BOUNDARY_GATING"] = {
            "passed": privacy_res["ok"] is False and privacy_res["status"] == "PRIVACY_BOUNDARY_ACTIVE",
            "status": privacy_res["status"],
        }

        # Gate 5: Resource Exhaustion Gating
        resource_res = engine.explore(
            ExplorationRequest(topic="resources low", authorized=True, resources_available=False)
        )
        gates["G05_RESOURCE_EXHAUSTION_GATING"] = {
            "passed": resource_res["ok"] is False and resource_res["status"] == "RESOURCE_UNAVAILABLE",
            "status": resource_res["status"],
        }

        # Gate 6: Owner Opt-out Gating
        optout_res = engine.explore(
            ExplorationRequest(topic="owner opt out", authorized=True, owner_opt_out=True)
        )
        gates["G06_OWNER_OPT_OUT_GATING"] = {
            "passed": optout_res["ok"] is False and optout_res["status"] == "OWNER_OPT_OUT",
            "status": optout_res["status"],
        }

        # Gate 7: Model Not Configured Gating
        no_model_engine = SpontaneityEngine(store, provider=None)
        no_model_res = no_model_engine.explore(
            ExplorationRequest(topic="no model configured", authorized=True)
        )
        gates["G07_MODEL_NOT_CONFIGURED_GATING"] = {
            "passed": (
                no_model_res["ok"] is False
                and no_model_res["status"] == "MODEL_NOT_CONFIGURED"
                and len(no_model_res["candidates"]) == 0
            ),
            "status": no_model_res["status"],
            "candidates": no_model_res["candidates"],
        }

        # Gate 8: Provider Unavailable or Timeout
        unhealthy_provider = DeterministicSeededVerificationProvider(healthy=False)
        unhealthy_engine = SpontaneityEngine(store, unhealthy_provider)
        unhealthy_res = unhealthy_engine.explore(
            ExplorationRequest(topic="unhealthy provider", authorized=True)
        )

        unsupported_seed_provider = DeterministicSeededVerificationProvider(supports_seed=False)
        unsupported_seed_engine = SpontaneityEngine(store, unsupported_seed_provider)
        unsupported_seed_res = unsupported_seed_engine.explore(
            ExplorationRequest(topic="unsupported seed", authorized=True)
        )

        timeout_provider = DeterministicSeededVerificationProvider(simulate_timeout=True)
        timeout_engine = SpontaneityEngine(store, timeout_provider)
        timeout_res = timeout_engine.explore(
            ExplorationRequest(topic="timeout provider", authorized=True)
        )

        gates["G08_PROVIDER_UNAVAILABLE_OR_TIMEOUT"] = {
            "passed": (
                unhealthy_res["status"] == "PROVIDER_UNAVAILABLE"
                and unsupported_seed_res["status"] == "PROVIDER_SEED_UNSUPPORTED"
                and timeout_res["status"] == "PROVIDER_TIMEOUT"
            ),
            "unhealthy_status": unhealthy_res["status"],
            "unsupported_seed_status": unsupported_seed_res["status"],
            "timeout_status": timeout_res["status"],
        }

        # Gate 9: Deterministic Seeded PRNG Candidate Reproduction & Replay
        run1 = engine.explore(
            ExplorationRequest(
                topic="deterministic reproducibility",
                authorized=True,
                seed=1337,
                request_id="seed-run-1",
                budget=ExplorationBudget(max_candidates=2),
            )
        )
        run2 = engine.explore(
            ExplorationRequest(
                topic="deterministic reproducibility",
                authorized=True,
                seed=1337,
                request_id="seed-run-2",
                budget=ExplorationBudget(max_candidates=2),
            )
        )
        # Replaying identical request_id
        run1_replay = engine.explore(
            ExplorationRequest(
                topic="deterministic reproducibility",
                authorized=True,
                seed=1337,
                request_id="seed-run-1",
            )
        )
        g9_ok = (
            run1["ok"] is True
            and run2["ok"] is True
            and run1_replay["ok"] is True
            and run1_replay["status"] == "REPLAYED_RECEIPT"
            and len(run1["candidates"]) == len(run2["candidates"])
            and all(
                c1["hypothesis_text"] == c2["hypothesis_text"]
                for c1, c2 in zip(run1["candidates"], run2["candidates"])
            )
            and run1_replay["receipt"]["receipt_sha256"] == run1["receipt"]["receipt_sha256"]
        )
        gates["G09_DETERMINISTIC_SEEDED_REPLAY"] = {
            "passed": bool(g9_ok),
            "run1_candidates_count": len(run1["candidates"]),
            "run2_candidates_count": len(run2["candidates"]),
            "replay_status": run1_replay["status"],
            "receipt_sha256": run1["receipt"]["receipt_sha256"],
        }

        # Gate 10: Hypothesis Labeling and Non-Promotion
        first_candidate = run1["candidates"][0]
        meta = first_candidate["metadata"]
        g10_ok = (
            first_candidate["confidence"] == 0.0
            and meta["label"] == "HYPOTHESIS"
            and meta["evidence_status"] == "UNVERIFIED"
            and meta["executable"] is False
            and meta["confidence_kind"] == "NOT_ASSESSED"
            and run1["status"] == "UNVERIFIED"
            and run1["label"] == "HYPOTHESIS"
        )
        gates["G10_HYPOTHESIS_LABELING_AND_NON_PROMOTION"] = {
            "passed": bool(g10_ok),
            "candidate_label": meta["label"],
            "evidence_status": meta["evidence_status"],
            "executable": meta["executable"],
            "confidence": first_candidate["confidence"],
            "confidence_kind": meta["confidence_kind"],
        }

        # Gate 11: Safety Review and Dangerous Action Rejection
        unsafe_provider = DeterministicSeededVerificationProvider(unsafe_candidate=True)
        unsafe_engine = SpontaneityEngine(store, unsafe_provider)
        unsafe_run = unsafe_engine.explore(
            ExplorationRequest(
                topic="security testing",
                authorized=True,
                seed=2026,
                request_id="unsafe-test-req",
            )
        )
        unsafe_candidates = unsafe_run["candidates"]
        rejected_c = unsafe_candidates[0]
        safe_c = unsafe_candidates[1]
        g11_ok = (
            unsafe_run["ok"] is True
            and rejected_c["metadata"]["label"] == "REJECTED_HYPOTHESIS"
            and rejected_c["metadata"]["evidence_status"] == "REJECTED"
            and rejected_c["metadata"]["retained"] is False
            and rejected_c["metadata"]["rejection_reason"] == "UNSAFE_ACTION_PROHIBITED"
            and safe_c["metadata"]["label"] == "HYPOTHESIS"
            and safe_c["metadata"]["evidence_status"] == "UNVERIFIED"
            and safe_c["metadata"]["retained"] is True
            and unsafe_run["metrics"]["rejected_candidates"] == 1
            and unsafe_run["metrics"]["accepted_candidates"] == 1
        )
        gates["G11_SAFETY_REVIEW_REJECTION"] = {
            "passed": bool(g11_ok),
            "rejected_candidate_reason": rejected_c["metadata"]["rejection_reason"],
            "rejected_label": rejected_c["metadata"]["label"],
            "safe_candidate_retained": safe_c["metadata"]["retained"],
            "metrics": unsafe_run["metrics"],
        }

        # Gate 12: Quantitative Novelty and Token-Level Diversity
        dup_run = engine.explore(
            ExplorationRequest(
                topic="deterministic reproducibility",
                authorized=True,
                seed=1337,
                request_id="seed-run-duplicate",
                budget=ExplorationBudget(max_candidates=2),
            )
        )
        g12_ok = (
            dup_run["ok"] is True
            and dup_run["metrics"]["accepted_candidates"] == 0
            and dup_run["metrics"]["novelty_score"] == 0.0
            and dup_run["candidates"][0]["metadata"]["retained"] is False
            and dup_run["candidates"][0]["metadata"]["rejection_reason"] == "DUPLICATE_CANDIDATE"
            and run1["metrics"]["novelty_score"] == 1.0
            and run1["metrics"]["diversity_score"] > 0.0
        )
        gates["G12_QUANTITATIVE_NOVELTY_AND_DIVERSITY"] = {
            "passed": bool(g12_ok),
            "run1_novelty_score": run1["metrics"]["novelty_score"],
            "run1_diversity_score": run1["metrics"]["diversity_score"],
            "dup_novelty_score": dup_run["metrics"]["novelty_score"],
            "dup_accepted_candidates": dup_run["metrics"]["accepted_candidates"],
        }

        # Gate 13: Persistence, Transaction, WAL Mode, and Integrity Checks
        conn = sqlite3.connect(str(db_path))
        with conn:
            journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            schema_ver = conn.execute("SELECT version FROM spontaneity_schema WHERE singleton = 1").fetchone()[0]
            receipt_count = conn.execute("SELECT COUNT(*) FROM exploration_receipts").fetchone()[0]
        conn.close()

        # Test tampering detection
        tamper_req_id = "tamper-test-record"
        engine.explore(
            ExplorationRequest(topic="tamper detection", authorized=True, seed=888, request_id=tamper_req_id)
        )
        tamper_conn = sqlite3.connect(str(db_path))
        with tamper_conn:
            tamper_conn.execute("UPDATE exploration_receipts SET seed = 999 WHERE request_id = ?", (tamper_req_id,))
        tamper_conn.close()

        corrupt_caught = False
        try:
            store.by_request_id(tamper_req_id)
        except ExplorationError as exc:
            if exc.code == "STORAGE_CORRUPT":
                corrupt_caught = True

        g13_ok = (
            str(journal_mode).lower() == "wal"
            and int(schema_ver) == 1
            and receipt_count > 0
            and corrupt_caught is True
        )
        gates["G13_PERSISTENCE_TRANSACTION_WAL_INTEGRITY"] = {
            "passed": bool(g13_ok),
            "journal_mode": journal_mode,
            "schema_version": schema_ver,
            "receipt_count": receipt_count,
            "tamper_detected": corrupt_caught,
        }

        # Gate 14: Canonical Core Runtime Wiring
        # Verify CognitiveRegulationCapabilityService manifests and _explore dispatch
        reg_service_dir = work_dir / "reg_service_root"
        reg_service_dir.mkdir(parents=True, exist_ok=True)
        from jaya_core.pillars.agentic_rag_capability import AgenticRAGCapability
        from jaya_core.brain_v2.soul.ethical_heart import EthicalHeart

        rag_cap = AgenticRAGCapability(reg_service_dir / "rag.sqlite3", None)
        ethical_heart = EthicalHeart(reg_service_dir / "ethical.db")
        reg_service = CognitiveRegulationCapabilityService(
            reg_service_dir,
            rag=rag_cap,
            hypothesis_provider=None,
            ethical_heart=ethical_heart,
            actor_brain_id="test-brain",
            node_id="test-node",
        )
        manifest_ids = [m.capability_id for m in reg_service.manifests()]
        g14_manifest_ok = SPONTANEITY_CAPABILITY_ID in manifest_ids

        # Test explore dispatch with custom provider
        reg_service.spontaneity.provider = provider
        pillar_res = reg_service._explore({
            "action": "explore",
            "topic": "canonical service integration",
            "authorized": True,
            "request_id": "canonical-reg-test-1",
            "seed": 4242,
            "evidence_ids": ["ev-101", "ev-102"],
        })
        reg_service.close()
        ethical_heart.close()
        rag_cap.close()

        g14_ok = (
            g14_manifest_ok
            and isinstance(pillar_res, LocalPillarResult)
            and pillar_res.pillar_id == "P006"
            and pillar_res.code == "UNVERIFIED"
            and pillar_res.data.get("ok") is True
        )
        gates["G14_CANONICAL_RUNTIME_WIRING"] = {
            "passed": bool(g14_ok),
            "manifest_registered": g14_manifest_ok,
            "pillar_id": pillar_res.pillar_id if isinstance(pillar_res, LocalPillarResult) else None,
            "status_code": pillar_res.code if isinstance(pillar_res, LocalPillarResult) else None,
        }

        # Gate 15: Soak Performance and Energy Metering
        soak_iterations = profile["soak"]["iterations"]
        soak_db_path = work_dir / "soak_spontaneity.sqlite3"
        soak_store = ExplorationReceiptStore(soak_db_path)
        soak_engine = SpontaneityEngine(soak_store, provider)

        t_soak_start = time.perf_counter()
        latencies_ms: list[float] = []
        with _energy_sampler() as energy_data:
            for idx in range(soak_iterations):
                t_iter = time.perf_counter()
                res = soak_engine.explore(
                    ExplorationRequest(
                        topic=f"soak iteration candidate {idx}",
                        authorized=True,
                        seed=10000 + idx,
                        request_id=f"soak-req-{idx}",
                        budget=ExplorationBudget(max_candidates=2),
                    )
                )
                latencies_ms.append((time.perf_counter() - t_iter) * 1000.0)

        soak_duration = time.perf_counter() - t_soak_start
        mean_latency_ms = sum(latencies_ms) / max(1, len(latencies_ms))
        rss_end = process.memory_info().rss
        rss_growth = max(0, rss_end - rss_start)
        soak_db_size = soak_db_path.stat().st_size
        bytes_per_record = soak_db_size / max(1, soak_iterations)
        joules_per_record = energy_data["energy_joules"] / max(1, soak_iterations)

        soak_ok = (
            mean_latency_ms <= profile["soak"]["max_mean_latency_ms"]
            and rss_growth <= profile["soak"]["max_rss_growth_bytes"]
            and bytes_per_record <= profile["soak"]["max_database_bytes_per_record"]
            and joules_per_record <= profile["soak"]["max_package_joules_per_record"]
        )
        gates["G15_SOAK_PERFORMANCE_AND_ENERGY"] = {
            "passed": bool(soak_ok),
            "iterations": soak_iterations,
            "mean_latency_ms": round(mean_latency_ms, 3),
            "max_threshold_ms": profile["soak"]["max_mean_latency_ms"],
            "rss_growth_bytes": rss_growth,
            "database_bytes_per_record": round(bytes_per_record, 1),
            "energy_joules": round(energy_data["energy_joules"], 4),
            "joules_per_record": round(joules_per_record, 6),
            "energy_method": energy_data["energy_method"],
        }

        soak_engine.close()
        engine.close()

    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                pass
        if soak_store is not None:
            try:
                soak_store.close()
            except Exception:
                pass
        try:
            temp_dir.cleanup()
        except Exception:
            pass

    all_passed = all(g["passed"] for g in gates.values())

    report = {
        "profile_id": profile_id,
        "pillar_id": 6,
        "capability_id": SPONTANEITY_CAPABILITY_ID,
        "scope": profile["scope"],
        "status": "VERIFIED" if all_passed else "FAILED",
        "verified_at": datetime.now(UTC).isoformat(),
        "approver": approver,
        "git_commit": _git_commit(repo_root),
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
        },
        "gates": gates,
        "summary": {
            "total_gates": len(gates),
            "passed_gates": sum(1 for g in gates.values() if g["passed"]),
            "failed_gates": sum(1 for g in gates.values() if not g["passed"]),
        },
    }

    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path, report
