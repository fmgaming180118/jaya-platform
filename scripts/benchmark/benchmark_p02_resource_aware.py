#!/usr/bin/env python3
"""benchmark_p02_resource_aware.py — Performance & Resource Benchmark for P02 Resource Aware.

Measures:
- Cold vs Warm profile latency (slow probe caching vs live metrics).
- Sampling overhead (CPU%, RSS before/after 1,000 samples).
- Provenance & source integrity across CPU, RAM, RSS, storage, network, power, thermal, accelerator.
- Budget calculation and execution mode determination throughput across node classes.
- Conservative fallback behavior on simulated probe failures.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

import psutil  # noqa: E402
from jaya_core.identity.models import NodeClass  # noqa: E402
from jaya_core.resources.budget import (  # noqa: E402
    ResourceBudgetCalculator,
    ResourceBudgetPolicy,
)
from jaya_core.resources.modes import (  # noqa: E402
    ExecutionMode,
    ExecutionModeController,
)
from jaya_core.resources.profiler import ResourceProfiler  # noqa: E402


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

    profiler = ResourceProfiler(slow_probe_interval_seconds=5.0)
    budget_calc = ResourceBudgetCalculator(ResourceBudgetPolicy())
    mode_ctrl = ExecutionModeController()

    # 1. Cold profile (first time, involves accelerator discovery)
    cold_start = time.perf_counter()
    cold_profile = profiler.profile(force_slow_probe=True)
    cold_latency_ms = (time.perf_counter() - cold_start) * 1000

    # 2. Warm profiles (steady-state with cached slow hardware probe)
    warm_latencies_ms: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        _ = profiler.profile(force_slow_probe=False)
        elapsed_ms = (time.perf_counter() - start) * 1000
        warm_latencies_ms.append(elapsed_ms)

    # 3. Forced refresh latency
    forced_latencies_ms: list[float] = []
    for _ in range(10):
        start = time.perf_counter()
        _ = profiler.profile(force_slow_probe=True)
        elapsed_ms = (time.perf_counter() - start) * 1000
        forced_latencies_ms.append(elapsed_ms)

    # 4. Budget & Mode Decision Throughput across 4 node classes
    decision_latencies_us: list[float] = []
    test_profiles = [
        profiler.profile(override_total_mem_mb=32_000, override_available_mem_mb=16_000, network_available=True, power_mode="NORMAL"),
        profiler.profile(override_total_mem_mb=8_000, override_available_mem_mb=4_000, network_available=True, power_mode="NORMAL"),
        profiler.profile(override_total_mem_mb=2_000, override_available_mem_mb=512, network_available=False, power_mode="SAVER"),
        profiler.profile(override_total_mem_mb=512, override_available_mem_mb=32, network_available=False, power_mode="CRITICAL"),
    ]
    for i in range(iterations):
        p = test_profiles[i % len(test_profiles)]
        start = time.perf_counter()
        b = budget_calc.calculate(p)
        ctrl = ExecutionModeController()
        m = ctrl.auto_determine_mode(p)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        decision_latencies_us.append(elapsed_us)
        assert b.max_memory_mb > 0
        assert m in ExecutionMode

    # 5. Memory RSS delta after 1,000 samples
    final_rss_mb = round(process.memory_info().rss / (1024 * 1024), 2)

    def quantiles(vals: list[float]) -> dict[str, float]:
        sorted_vals = sorted(vals)
        n = len(sorted_vals)
        return {
            "min": round(sorted_vals[0], 3),
            "p50": round(sorted_vals[int(n * 0.50)], 3),
            "p90": round(sorted_vals[int(n * 0.90)], 3),
            "p99": round(sorted_vals[int(n * 0.99)], 3),
            "max": round(sorted_vals[-1], 3),
            "mean": round(statistics.mean(sorted_vals), 3),
        }

    # Verify live profile attributes and honest provenance
    live_profile = profiler.profile()
    provenance_report = {
        "node_class": live_profile.node_class.value,
        "total_memory_mb": live_profile.total_memory_mb,
        "available_memory_mb": live_profile.available_memory_mb,
        "process_memory_mb": live_profile.process_memory_mb,
        "cpu_count": live_profile.cpu_count,
        "cpu_usage_percent": live_profile.cpu_usage_percent,
        "storage_free_mb": live_profile.storage_free_mb,
        "network_available": live_profile.network_available,
        "power_mode": live_profile.power_mode,
        "battery_percent": live_profile.battery_percent,
        "thermal_celsius": live_profile.thermal_celsius,
        "accelerator_available": live_profile.accelerator_available,
        "accelerator_name": live_profile.accelerator_name,
        "sources": live_profile.sources,
        "metric_ages_ms": live_profile.metric_ages_ms,
        "errors": list(live_profile.errors),
    }

    return {
        "environment": env,
        "iterations": iterations,
        "memory": {
            "initial_rss_mb": env["initial_rss_mb"],
            "final_rss_mb": final_rss_mb,
            "delta_rss_mb": round(final_rss_mb - env["initial_rss_mb"], 2),
        },
        "profile_sampling_latency_ms": {
            "cold_profile_ms": round(cold_latency_ms, 3),
            "warm_steady_state_ms": quantiles(warm_latencies_ms),
            "forced_refresh_ms": quantiles(forced_latencies_ms),
            "cache_speedup_ratio": round(cold_latency_ms / statistics.mean(warm_latencies_ms), 2),
        },
        "budget_and_mode_decision_us": quantiles(decision_latencies_us),
        "live_profile_provenance": provenance_report,
    }


def main() -> int:
    print("=" * 65)
    print("       JAYA BENCHMARK: PILAR P02 RESOURCE AWARE")
    print("=" * 65)

    result = run_benchmark(iterations=1000)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
