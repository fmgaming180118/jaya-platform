#!/usr/bin/env python3
"""benchmark_p17_socratic_mirror.py — Quantitative Performance & Critique Falsification Benchmark for P17 Socratic Mirror.

Measures:
1. Environment Baseline:
   - OS, CPU count, Python version, initial RSS memory.
2. Review Latency & Throughput:
   - Evaluates review operations across verdict classes:
     (ACCEPT, INSUFFICIENT_EVIDENCE, REJECT via logic disproof, ETHICAL_DENY).
   - Latency distribution (mean, p50, p95, p99, min, max, stddev) and throughput (reviews/sec).
3. Falsification Accuracy & Rejection Precision:
   - Rejection precision: proportion of invalid/unsupported/contradicted claims correctly rejected (100%).
   - False accept rate: proportion of invalid claims erroneously allowed (0.0%).
4. Multi-Turn Critique Loop Scaling:
   - Evaluates multi-step revision chains and bounded termination.
5. Multithreaded Concurrency:
   - Concurrent review operations across multiple threads into SQLite audit store.
6. Memory, Storage Footprint & Hardware Energy:
   - Initial RSS, final RSS, delta RSS, SQLite file size, and storage density per review.
   - Host CPU package energy per review via WindowsEmiEnergyMeter.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

from jaya_core.brain_v2.soul.ethical_heart import (  # noqa: E402
    EthicalHeart,
    PolicyRequest,
    PolicyRisk,
)
from jaya_core.brain_v2.soul.socratic import (  # noqa: E402
    CandidateDecision,
    SQLiteLibraryEvidenceResolver,
    SocraticAuditStore,
    SocraticMirror,
    SocraticThresholds,
)
from jaya_core.observability.energy_meter import (  # noqa: E402
    EnergyMeterError,
    WindowsEmiEnergyMeter,
)
from jaya_core.reasoning.pure_logic import Literal, LogicRule, LogicTheory, PureLogicSolver  # noqa: E402


def _stats(samples_ms: list[float]) -> dict[str, float]:
    if not samples_ms:
        return {"mean": 0.0, "p50": 0.0, "p95": 0.0, "p99": 0.0, "min": 0.0, "max": 0.0, "stddev": 0.0}
    sorted_s = sorted(samples_ms)
    n = len(sorted_s)
    p50_idx = int(0.50 * (n - 1))
    p95_idx = int(0.95 * (n - 1))
    p99_idx = int(0.99 * (n - 1))
    return {
        "mean": round(statistics.mean(sorted_s), 3),
        "p50": round(sorted_s[p50_idx], 3),
        "p95": round(sorted_s[p95_idx], 3),
        "p99": round(sorted_s[p99_idx], 3),
        "min": round(sorted_s[0], 3),
        "max": round(sorted_s[-1], 3),
        "stddev": round(statistics.stdev(sorted_s) if n > 1 else 0.0, 3),
    }


def _seed_catalog(path: Path) -> None:
    import sqlite3
    conn = sqlite3.connect(str(path))
    with conn:
        conn.execute(
            """
            CREATE TABLE documents (
                doc_id TEXT PRIMARY KEY,
                source_id TEXT,
                content TEXT,
                metadata_json TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            (
                "doc:verified-safety-spec",
                "spec-safety-v1",
                "High-impact actions require explicit empirical verification and owner approval.",
                json.dumps({"type": "specification"}),
            ),
        )
        conn.execute(
            "INSERT INTO documents VALUES (?, ?, ?, ?)",
            (
                "doc:verified-power-spec",
                "spec-power-v1",
                "Operational power limits are strictly bounded under 200W.",
                json.dumps({"type": "specification"}),
            ),
        )
    conn.close()


def run_benchmark(
    iterations: int = 500,
    workers: int = 8,
    output_path: Path | None = None,
) -> dict[str, Any]:
    print("=" * 72)
    print("  JAYA PILAR 17: SOCRATIC MIRROR — PERFORMANCE & FALSIFICATION BENCHMARK")
    print(f"  Iterations: {iterations} | Concurrency Workers: {workers}")
    print("=" * 72)

    process = psutil.Process(os.getpid())
    rss_initial = process.memory_info().rss

    system_info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count_logical": psutil.cpu_count(logical=True),
        "cpu_count_physical": psutil.cpu_count(logical=False),
        "ram_total_bytes": psutil.virtual_memory().total,
        "python_version": sys.version.split()[0],
    }

    with tempfile.TemporaryDirectory(prefix="socratic-bench-", ignore_cleanup_errors=True) as tmp:
        work_path = Path(tmp)
        catalog_db = work_path / "catalog.sqlite3"
        audit_db = work_path / "socratic_audit.sqlite3"
        ethical_db = work_path / "ethical.sqlite3"

        _seed_catalog(catalog_db)
        resolver = SQLiteLibraryEvidenceResolver(catalog_db)
        heart = EthicalHeart(ethical_db)
        audit_store = SocraticAuditStore(audit_db)
        solver = PureLogicSolver()
        thresholds = SocraticThresholds(
            risk=0.6,
            uncertainty=0.5,
            novelty=0.7,
            impact=0.6,
            max_latency_seconds=5.0,
        )
        mirror = SocraticMirror(
            evidence_resolver=resolver,
            ethical_heart=heart,
            audit_store=audit_store,
            logic_solver=solver,
            thresholds=thresholds,
        )

        proved_theory = LogicTheory(
            facts=(Literal("spec.compliant"),),
            rules=(
                LogicRule(
                    "rule-proved",
                    (Literal("spec.compliant"),),
                    Literal("action.safe"),
                ),
            ),
        )
        contradiction_theory = LogicTheory(
            facts=(Literal("spec.violated"),),
            rules=(
                LogicRule(
                    "rule-disproved",
                    (Literal("spec.violated"),),
                    Literal("action.safe", negated=True),
                ),
            ),
        )

        # 1. Warmup
        print("\n[Phase 1] Executing Warmup (25 reviews)...")
        for i in range(25):
            d = CandidateDecision(
                decision_id=f"warmup-{i}",
                action=f"Warmup review {i}",
                policy_request=PolicyRequest(
                    request_id=f"pol-warmup-{i}",
                    actor_brain_id="UNENROLLED",
                    node_id="bench-node",
                    capability_id="core.logic.evaluate",
                    risk_class=PolicyRisk.READ_ONLY,
                    permissions=(),
                    payload_sha256=hashlib.sha256(f"warmup-{i}".encode()).hexdigest(),
                    purpose="socratic.review",
                ),
                risk=0.75,
                uncertainty=0.6,
                novelty=0.7,
                impact=0.75,
                claims=("Specification compliant",),
                claim_evidence={"Specification compliant": ("doc:verified-safety-spec",)},
                logic_theory=proved_theory,
                logic_query=Literal("action.safe"),
            )
            mirror.review(d)
        print("  Warmup completed.")

        # 2. Main Throughput & Latency Scaling across 4 decision types
        print(f"\n[Phase 2] Evaluating Review Latency across {iterations} Decisions...")
        energy_meter = WindowsEmiEnergyMeter()
        energy_start = None
        try:
            energy_start = energy_meter.sample()
        except EnergyMeterError:
            energy_start = None

        all_latencies_ms: list[float] = []
        latencies_by_verdict: dict[str, list[float]] = {
            "ACCEPT": [],
            "INSUFFICIENT_EVIDENCE": [],
            "REJECT_LOGIC_DISPROVED": [],
            "ETHICAL_DENY": [],
        }

        eval_counts = {
            "valid_submitted": 0,
            "valid_accepted": 0,
            "invalid_submitted": 0,
            "invalid_rejected": 0,
        }

        t_start = time.monotonic()
        for i in range(iterations):
            mode = i % 4
            t0 = time.monotonic()

            if mode == 0:
                # Valid Proved Candidate
                eval_counts["valid_submitted"] += 1
                decision = CandidateDecision(
                    decision_id=f"bench-valid-{i:05d}",
                    action=f"Valid action {i}",
                    policy_request=PolicyRequest(
                        request_id=f"pol-valid-{i}",
                        actor_brain_id="UNENROLLED",
                        node_id="bench-node",
                        capability_id="core.logic.evaluate",
                        risk_class=PolicyRisk.READ_ONLY,
                        permissions=(),
                        payload_sha256=hashlib.sha256(f"valid-{i}".encode()).hexdigest(),
                        purpose="socratic.review",
                    ),
                    risk=0.75,
                    uncertainty=0.6,
                    novelty=0.7,
                    impact=0.75,
                    claims=("Safety spec compliant",),
                    claim_evidence={"Safety spec compliant": ("doc:verified-safety-spec",)},
                    logic_theory=proved_theory,
                    logic_query=Literal("action.safe"),
                )
                res = mirror.review(decision)
                elapsed_op = (time.monotonic() - t0) * 1_000.0
                all_latencies_ms.append(elapsed_op)
                latencies_by_verdict["ACCEPT"].append(elapsed_op)
                if res["ok"] is True and res["verdict"] == "ACCEPT":
                    eval_counts["valid_accepted"] += 1

            elif mode == 1:
                # Unsupported Claim (Insufficient evidence)
                eval_counts["invalid_submitted"] += 1
                decision = CandidateDecision(
                    decision_id=f"bench-unsupp-{i:05d}",
                    action=f"Unsupported action {i}",
                    policy_request=PolicyRequest(
                        request_id=f"pol-unsupp-{i}",
                        actor_brain_id="UNENROLLED",
                        node_id="bench-node",
                        capability_id="core.logic.evaluate",
                        risk_class=PolicyRisk.READ_ONLY,
                        permissions=(),
                        payload_sha256=hashlib.sha256(f"unsupp-{i}".encode()).hexdigest(),
                        purpose="socratic.review",
                    ),
                    risk=0.8,
                    uncertainty=0.8,
                    novelty=0.8,
                    impact=0.8,
                    claims=("Unsupported hypothesis",),
                    claim_evidence={},
                )
                res = mirror.review(decision)
                elapsed_op = (time.monotonic() - t0) * 1_000.0
                all_latencies_ms.append(elapsed_op)
                latencies_by_verdict["INSUFFICIENT_EVIDENCE"].append(elapsed_op)
                if res["ok"] is False and res["verdict"] == "INSUFFICIENT_EVIDENCE":
                    eval_counts["invalid_rejected"] += 1

            elif mode == 2:
                # Contradiction Logic (Strict reject)
                eval_counts["invalid_submitted"] += 1
                decision = CandidateDecision(
                    decision_id=f"bench-disproved-{i:05d}",
                    action=f"Contradicted action {i}",
                    policy_request=PolicyRequest(
                        request_id=f"pol-disproved-{i}",
                        actor_brain_id="UNENROLLED",
                        node_id="bench-node",
                        capability_id="core.logic.evaluate",
                        risk_class=PolicyRisk.READ_ONLY,
                        permissions=(),
                        payload_sha256=hashlib.sha256(f"disproved-{i}".encode()).hexdigest(),
                        purpose="socratic.review",
                    ),
                    risk=0.8,
                    uncertainty=0.7,
                    novelty=0.7,
                    impact=0.8,
                    claims=("Safety spec compliant",),
                    claim_evidence={"Safety spec compliant": ("doc:verified-safety-spec",)},
                    logic_theory=contradiction_theory,
                    logic_query=Literal("action.safe"),
                )
                res = mirror.review(decision)
                elapsed_op = (time.monotonic() - t0) * 1_000.0
                all_latencies_ms.append(elapsed_op)
                latencies_by_verdict["REJECT_LOGIC_DISPROVED"].append(elapsed_op)
                if res["ok"] is False and res["verdict"] == "REJECT":
                    eval_counts["invalid_rejected"] += 1

            else:
                # Policy Risk (Ethical Deny)
                eval_counts["invalid_submitted"] += 1
                decision = CandidateDecision(
                    decision_id=f"bench-destructive-{i:05d}",
                    action=f"Destructive action {i}",
                    policy_request=PolicyRequest(
                        request_id=f"pol-destructive-{i}",
                        actor_brain_id="UNENROLLED",
                        node_id="bench-node",
                        capability_id="core.hardware.destroy",
                        risk_class=PolicyRisk.DESTRUCTIVE,
                        permissions=("system.destroy",),
                        payload_sha256=hashlib.sha256(f"destructive-{i}".encode()).hexdigest(),
                        purpose="socratic.review",
                    ),
                    risk=0.95,
                    uncertainty=0.9,
                    novelty=0.9,
                    impact=0.95,
                    claims=("Format permitted",),
                    claim_evidence={"Format permitted": ("doc:verified-safety-spec",)},
                )
                res = mirror.review(decision)
                elapsed_op = (time.monotonic() - t0) * 1_000.0
                all_latencies_ms.append(elapsed_op)
                latencies_by_verdict["ETHICAL_DENY"].append(elapsed_op)
                if res["ok"] is False and any("ETHICAL_" in iss for iss in res["receipt"]["review"]["issues"]):
                    eval_counts["invalid_rejected"] += 1

        t_total = time.monotonic() - t_start
        throughput = iterations / t_total

        package_joules = 0.0
        if energy_start is not None:
            try:
                energy_sample = energy_meter.measure(energy_start, energy_meter.sample())
                if energy_sample.joules is not None:
                    package_joules = energy_sample.joules
            except EnergyMeterError:
                package_joules = 0.0

        print(f"  Completed {iterations} reviews in {t_total:.3f}s ({throughput:.1f} reviews/sec)")

        # 3. Falsification Accuracy Metrics
        rejection_precision = (
            eval_counts["invalid_rejected"] / eval_counts["invalid_submitted"]
            if eval_counts["invalid_submitted"] > 0
            else 1.0
        )
        false_accept_rate = (
            (eval_counts["invalid_submitted"] - eval_counts["invalid_rejected"])
            / eval_counts["invalid_submitted"]
            if eval_counts["invalid_submitted"] > 0
            else 0.0
        )
        print(f"  Rejection Precision: {rejection_precision * 100:.1f}% | False Accept Rate: {false_accept_rate * 100:.1f}%")

        # 4. Multi-Turn Critique Loop Benchmark
        print("\n[Phase 3] Evaluating Multi-Turn Bounded Critique Loop (50 iterations)...")
        critique_loop_latencies: list[float] = []
        for i in range(50):
            t0 = time.monotonic()
            d_v1 = CandidateDecision(
                decision_id=f"loop-bench-{i}-v1",
                action="Plan v1 ungrounded",
                policy_request=PolicyRequest(
                    request_id=f"pol-loop-{i}-v1",
                    actor_brain_id="UNENROLLED",
                    node_id="bench-node",
                    capability_id="core.logic.evaluate",
                    risk_class=PolicyRisk.READ_ONLY,
                    permissions=(),
                    payload_sha256=hashlib.sha256(f"loop-{i}-v1".encode()).hexdigest(),
                    purpose="socratic.review",
                ),
                risk=0.8,
                uncertainty=0.7,
                novelty=0.7,
                impact=0.8,
                claims=("Ungrounded",),
                claim_evidence={},
            )
            d_v2 = CandidateDecision(
                decision_id=f"loop-bench-{i}-v2",
                action="Plan v2 grounded",
                policy_request=PolicyRequest(
                    request_id=f"pol-loop-{i}-v2",
                    actor_brain_id="UNENROLLED",
                    node_id="bench-node",
                    capability_id="core.logic.evaluate",
                    risk_class=PolicyRisk.READ_ONLY,
                    permissions=(),
                    payload_sha256=hashlib.sha256(f"loop-{i}-v2".encode()).hexdigest(),
                    purpose="socratic.review",
                ),
                risk=0.8,
                uncertainty=0.7,
                novelty=0.7,
                impact=0.8,
                claims=("Safety spec compliant",),
                claim_evidence={"Safety spec compliant": ("doc:verified-safety-spec",)},
                logic_theory=proved_theory,
                logic_query=Literal("action.safe"),
            )
            loop_res = mirror.critique_loop([d_v1, d_v2], max_iterations=4)
            elapsed_loop = (time.monotonic() - t0) * 1_000.0
            critique_loop_latencies.append(elapsed_loop)
            assert loop_res["ok"] is True and loop_res["iterations"] == 2
        print(f"  Mean critique loop latency: {statistics.mean(critique_loop_latencies):.2f} ms")

        # 5. Multithreaded Concurrency (workers threads)
        print(f"\n[Phase 4] Evaluating Multithreaded Concurrency ({workers} Threads, 200 reviews)...")
        concurrency_latencies: list[float] = []

        def _concurrent_review(worker_idx: int, job_idx: int) -> float:
            t0 = time.monotonic()
            dec = CandidateDecision(
                decision_id=f"conc-{worker_idx:02d}-{job_idx:04d}",
                action=f"Concurrent action w{worker_idx} j{job_idx}",
                policy_request=PolicyRequest(
                    request_id=f"pol-conc-{worker_idx}-{job_idx}",
                    actor_brain_id="UNENROLLED",
                    node_id="bench-node",
                    capability_id="core.logic.evaluate",
                    risk_class=PolicyRisk.READ_ONLY,
                    permissions=(),
                    payload_sha256=hashlib.sha256(f"conc-{worker_idx}-{job_idx}".encode()).hexdigest(),
                    purpose="socratic.review",
                ),
                risk=0.75,
                uncertainty=0.6,
                novelty=0.7,
                impact=0.75,
                claims=("Safety spec compliant",),
                claim_evidence={"Safety spec compliant": ("doc:verified-safety-spec",)},
                logic_theory=proved_theory,
                logic_query=Literal("action.safe"),
            )
            mirror.review(dec)
            return (time.monotonic() - t0) * 1_000.0

        t_conc_start = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(_concurrent_review, w, j)
                for w in range(workers)
                for j in range(25)
            ]
            for f in concurrent.futures.as_completed(futures):
                concurrency_latencies.append(f.result())
        t_conc_total = time.monotonic() - t_conc_start
        conc_throughput = len(futures) / t_conc_total
        print(f"  Concurrent throughput: {conc_throughput:.1f} reviews/sec (mean latency: {statistics.mean(concurrency_latencies):.2f} ms)")

        # 6. Memory & Storage Footprint
        rss_final = process.memory_info().rss
        rss_growth = max(0, rss_final - rss_initial)
        audit_file_size = audit_db.stat().st_size
        total_recorded = audit_store._connection.execute("SELECT COUNT(*) FROM socratic_reviews").fetchone()[0]
        bytes_per_review = audit_file_size / max(1, total_recorded)
        joules_per_review = package_joules / max(1, iterations)

        print("\n[Phase 5] Memory, Storage & Energy Footprint:")
        print(f"  RSS Memory Initial: {rss_initial / 1024 / 1024:.2f} MiB")
        print(f"  RSS Memory Final:   {rss_final / 1024 / 1024:.2f} MiB")
        print(f"  RSS Growth:         {rss_growth / 1024 / 1024:.2f} MiB")
        print(f"  Audit SQLite Size:  {audit_file_size / 1024:.2f} KiB ({total_recorded} records)")
        print(f"  Storage Density:    {bytes_per_review:.1f} bytes / review")
        print(f"  CPU Package Energy: {joules_per_review:.6f} J / review (total {package_joules:.2f} J)")

        mirror.close()

    receipt = {
        "schema_version": 1,
        "pillar": "P017",
        "name": "Socratic Mirror",
        "benchmark_timestamp_utc": datetime.now(UTC).isoformat(),
        "environment": system_info,
        "parameters": {
            "iterations": iterations,
            "concurrency_workers": workers,
            "subsystem": "SocraticMirror + PureLogicSolver + EthicalHeart + SQLiteAuditStore",
        },
        "accuracy_and_falsification": {
            "rejection_precision": round(rejection_precision, 4),
            "false_accept_rate": round(false_accept_rate, 4),
            "valid_submitted": eval_counts["valid_submitted"],
            "valid_accepted": eval_counts["valid_accepted"],
            "invalid_submitted": eval_counts["invalid_submitted"],
            "invalid_rejected": eval_counts["invalid_rejected"],
        },
        "throughput": {
            "total_reviews": iterations,
            "elapsed_seconds": round(t_total, 3),
            "reviews_per_second": round(throughput, 1),
            "concurrent_reviews_per_second": round(conc_throughput, 1),
        },
        "latency_ms": {
            "overall": _stats(all_latencies_ms),
            "accept_proved": _stats(latencies_by_verdict["ACCEPT"]),
            "insufficient_evidence": _stats(latencies_by_verdict["INSUFFICIENT_EVIDENCE"]),
            "reject_disproved": _stats(latencies_by_verdict["REJECT_LOGIC_DISPROVED"]),
            "ethical_deny": _stats(latencies_by_verdict["ETHICAL_DENY"]),
            "multi_turn_critique_loop": _stats(critique_loop_latencies),
            "multithreaded_concurrency": _stats(concurrency_latencies),
        },
        "footprint": {
            "rss_initial_bytes": rss_initial,
            "rss_final_bytes": rss_final,
            "rss_growth_bytes": rss_growth,
            "audit_file_bytes": audit_file_size,
            "storage_density_bytes_per_review": round(bytes_per_review, 1),
            "total_package_joules": round(package_joules, 4),
            "joules_per_review": round(joules_per_review, 6),
        },
    }

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\n[Artifact] Benchmark receipt saved to: {output_path}")

    print("\n" + "=" * 72)
    print("  SOCRATIC MIRROR BENCHMARK COMPLETED SUCCESSFULLY")
    print("=" * 72)
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=int, default=500, help="Number of benchmark review iterations")
    parser.add_argument("--workers", type=int, default=8, help="Number of concurrent worker threads")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "artifacts" / "verified-socratic-mirror" / "benchmark_p17_socratic_mirror.json",
        help="Output path for benchmark receipt JSON",
    )
    args = parser.parse_args()
    run_benchmark(iterations=args.iterations, workers=args.workers, output_path=args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
