#!/usr/bin/env python3
"""benchmark_p05_logical_homeostasis.py — Performance & Safety Benchmark for P05 Logical Homeostasis.

Measures:
- Steady-state evaluation latency (evaluation without state change).
- State transition & SQLite append latency (digest computation, JSON serialization, SQLite insert).
- Hysteresis anti-oscillation efficiency (simulated boundary fluctuation).
- Tamper detection & recovery latency (SHA-256 digest validation, fail-closed, recovery).
- Concurrent thread-safety and SQLite transaction throughput.
- RSS memory consumption and event store file size.
"""

from __future__ import annotations

import json
import os
import platform
import sqlite3
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

import psutil  # noqa: E402
from jaya_core.brain_v2.organism.homeostasis import (  # noqa: E402
    HomeostasisEventStore,
    HomeostasisPolicy,
    HomeostasisState,
    LogicalHomeostasisController,
)
from jaya_core.identity.models import NodeClass  # noqa: E402
from jaya_core.resources.profiler import ResourceProfile  # noqa: E402


def _profile(
    available_memory_mb: int = 4096,
    storage_free_mb: int = 20480,
    thermal_celsius: float | None = 45.0,
    power_mode: str = "NORMAL",
) -> ResourceProfile:
    return ResourceProfile(
        node_class=NodeClass.CENTRAL,
        total_memory_mb=16384,
        available_memory_mb=available_memory_mb,
        process_memory_mb=128,
        cpu_count=8,
        storage_free_mb=storage_free_mb,
        network_available=True,
        power_mode=power_mode,
        thermal_celsius=thermal_celsius,
    )


def _measure_environment() -> dict[str, object]:
    process = psutil.Process(os.getpid())
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or "Unknown",
        "cpu_count_logical": os.cpu_count(),
        "python_version": platform.python_version(),
        "initial_rss_mb": round(process.memory_info().rss / (1024 * 1024), 2),
    }


def run_benchmark(iterations: int = 1000) -> dict[str, object]:
    env = _measure_environment()
    process = psutil.Process(os.getpid())

    scratch_dir = ROOT / "outputs" / "scratch" / "p05_bench"
    scratch_dir.mkdir(parents=True, exist_ok=True)
    db_path = scratch_dir / "benchmark_homeostasis.db"
    if db_path.exists():
        try:
            db_path.unlink()
        except OSError:
            pass
    store = HomeostasisEventStore(db_path)
    policy = HomeostasisPolicy()
    controller = LogicalHomeostasisController(store, policy)

    # 1. Steady-state evaluation latency (NORMAL -> NORMAL, no DB append)
    steady_profile = _profile()
    steady_latencies_us: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        d = controller.evaluate(steady_profile, logic_ready=True, memory_ready=True)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        steady_latencies_us.append(elapsed_us)
        assert d.state is HomeostasisState.NORMAL
        assert d.changed is False

    # 2. State transition & SQLite append latency
    # Alternating between NORMAL and DEGRADED
    transition_latencies_us: list[float] = []
    degraded_p = _profile(available_memory_mb=400)
    healthy_p = _profile(available_memory_mb=1000)
    for i in range(100):
        target_p = degraded_p if (i % 2 == 0) else healthy_p
        start = time.perf_counter()
        d = controller.evaluate(target_p, logic_ready=True, memory_ready=True)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        transition_latencies_us.append(elapsed_us)
        assert d.changed is True

    # 3. Hysteresis Anti-Oscillation Test
    # Memory fluctuating between 500 MB (below degraded 512 MB) and 600 MB (below recovery 768 MB)
    fluctuations = [500, 600, 520, 650, 510, 700, 500, 750]
    oscillation_transitions = 0
    for mem in fluctuations:
        d = controller.evaluate(_profile(available_memory_mb=mem), logic_ready=True, memory_ready=True)
        if d.changed:
            oscillation_transitions += 1
    # Now pass recovery threshold (800 MB >= 768 MB)
    recovery_decision = controller.evaluate(_profile(available_memory_mb=800), logic_ready=True, memory_ready=True)
    assert recovery_decision.state is HomeostasisState.NORMAL

    # 4. Tamper Detection & Recovery Latency
    controller.close()

    # Tamper with the last event in SQLite to break SHA-256 digest
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE homeostasis_transitions SET reasons_json = '[\"tampered\"]' WHERE transition_id = (SELECT MAX(transition_id) FROM homeostasis_transitions)"
        )
        conn.commit()
    finally:
        conn.close()

    # Restart controller to detect corruption
    tamper_start = time.perf_counter()
    restarted_store = HomeostasisEventStore(db_path)
    restarted_ctrl = LogicalHomeostasisController(restarted_store, policy)
    tamper_detection_us = (time.perf_counter() - tamper_start) * 1_000_000
    assert restarted_ctrl.state is HomeostasisState.SAFE_STOP
    assert restarted_store.corruption_count() >= 1

    # Recover upon validated healthy profile
    recovery_start = time.perf_counter()
    rec_d = restarted_ctrl.evaluate(_profile(available_memory_mb=2048), logic_ready=True, memory_ready=True)
    recovery_latency_us = (time.perf_counter() - recovery_start) * 1_000_000
    assert rec_d.state is HomeostasisState.NORMAL
    assert "ledger_recovered_after_health_validation" in rec_d.reasons

    # 5. Concurrent evaluations (4 worker threads)
    thread_errors: list[Exception] = []

    def worker(w_id: int) -> None:
        try:
            for j in range(50):
                p = _profile(available_memory_mb=1000 + (w_id * 100) + j)
                restarted_ctrl.evaluate(p, logic_ready=True, memory_ready=True)
        except Exception as e:
            thread_errors.append(e)

    threads = [threading.Thread(target=worker, args=(k,)) for k in range(4)]
    concurrent_start = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    concurrent_total_ms = (time.perf_counter() - concurrent_start) * 1000
    assert len(thread_errors) == 0

    total_events = restarted_store.count()
    total_corruptions = restarted_store.corruption_count()
    final_db_size_bytes = os.path.getsize(db_path)
    restarted_ctrl.close()
    final_rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)

    def quantiles(vals: list[float]) -> dict[str, float]:
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        return {
            "min": round(sorted_vals[0], 2),
            "p50": round(sorted_vals[int(n * 0.50)], 2),
            "p90": round(sorted_vals[int(n * 0.90)], 2),
            "p99": round(sorted_vals[int(n * 0.99)], 2),
            "max": round(sorted_vals[-1], 2),
            "mean": round(statistics.mean(sorted_vals), 2),
        }

    return {
        "environment": env,
        "iterations": iterations,
        "memory": {
            "initial_rss_mb": env["initial_rss_mb"],
            "final_rss_mb": final_rss_mb,
            "delta_rss_mb": round(final_rss_mb - env["initial_rss_mb"], 2),
        },
        "steady_state_evaluation_latency_us": quantiles(steady_latencies_us),
        "state_transition_persisted_latency_us": quantiles(transition_latencies_us),
        "hysteresis_defense": {
            "fluctuation_cycles": len(fluctuations),
            "spurious_transitions_prevented": len(fluctuations) - oscillation_transitions,
            "actual_transitions": oscillation_transitions,
        },
        "tamper_and_recovery_us": {
            "tamper_detection_and_safe_stop_us": round(tamper_detection_us, 2),
            "health_validation_recovery_us": round(recovery_latency_us, 2),
        },
        "concurrency": {
            "worker_threads": 4,
            "total_concurrent_evaluations": 200,
            "total_elapsed_ms": round(concurrent_total_ms, 2),
            "errors": len(thread_errors),
        },
        "event_store": {
            "total_recorded_events": total_events,
            "corruption_incidents_recorded": total_corruptions,
            "database_size_bytes": final_db_size_bytes,
        },
    }


def main() -> int:
    print("=" * 65)
    print("       JAYA BENCHMARK: PILAR P05 LOGICAL HOMEOSTASIS")
    print("=" * 65)

    result = run_benchmark(iterations=1000)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
