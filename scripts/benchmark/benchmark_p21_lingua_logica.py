#!/usr/bin/env python3
"""benchmark_p21_lingua_logica.py — Performance & Resource Benchmark for P21 Lingua Logica.

Measures:
- Natural language to AST/JayaIR compile latency across English and Indonesian prompts.
- JayaIR execution latency (cold execution vs cached replay).
- RSS Memory consumption before and after 1,000 runs.
- Artifact and AST sizes (serialized JSON bytes, instruction count).
- Structured failure path latency (fail-closed unknown capability, divide-by-zero).
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
from jaya_core.brain_v2.engine.jaya_ir import (  # noqa: E402
    IRFailureCode,
    IRInstruction,
    JayaIRGraph,
    OpCode,
)
from jaya_core.brain_v2.engine.jaya_ir_exec import JayaIRExecutor  # noqa: E402
from jaya_core.brain_v2.engine.jaya_ir_translator import (  # noqa: E402
    logic_expr_to_ir,
    text_to_ir,
)
from jaya_core.brain_v2.soul.lingua_logica import LinguaLogica  # noqa: E402


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

    lingua = LinguaLogica()
    executor = JayaIRExecutor(cache_size=256, ttl_s=300.0)

    # Test sample prompts (Bilingual EN & ID)
    prompts = [
        "open desktop",
        "tutup aplikasi",
        "what is 144 / 12",
        "hitung 25 * 4",
        "create document",
        "hapus cache",
    ]

    # 1. Compilation Latency: Text -> AST -> JayaIR Graph
    compile_latencies_us: list[float] = []
    sample_artifacts: dict[str, object] = {}
    for i in range(iterations):
        prompt = prompts[i % len(prompts)]
        start = time.perf_counter()
        expr, graph = text_to_ir(prompt, lingua=lingua)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        compile_latencies_us.append(elapsed_us)
        if i < len(prompts):
            graph_payload = {
                "version": graph.version,
                "source": graph.source,
                "instructions": [inst.canonical() for inst in graph.instructions],
            }
            sample_artifacts[prompt] = {
                "ast": str(expr),
                "instructions_count": len(graph.instructions),
                "signature": graph.signature,
                "json_size_bytes": len(json.dumps(graph_payload).encode("utf-8")),
            }

    # 2. Execution Latency: Cold execution vs Cached Replay
    # Prompt: "what is 144 / 12" -> ARITH_DIV
    arith_expr, arith_graph = text_to_ir("what is 144 / 12", lingua=lingua)

    # Cold execution
    executor.clear_cache()
    cold_start = time.perf_counter()
    cold_res = executor.execute_graph(arith_graph)
    cold_latency_us = (time.perf_counter() - cold_start) * 1_000_000
    assert cold_res["ok"] is True
    assert cold_res["result"] == 12.0
    assert cold_res["cache_hit"] is False

    # Cached replay (1,000 iterations)
    cached_latencies_us: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        cached_res = executor.execute_graph(arith_graph)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        cached_latencies_us.append(elapsed_us)
        assert cached_res["cache_hit"] is True

    # 3. Action Execution (e.g. open desktop)
    action_expr, action_graph = text_to_ir("open desktop", lingua=lingua)
    executor.clear_cache()
    action_res = executor.execute_graph(action_graph)
    assert action_res["ok"] is True
    assert action_res["result"]["target"] == "desktop"

    # 4. Typed Failure Latencies
    failure_bench = {}
    # Divide by zero
    div0_expr, div0_graph = text_to_ir("what is 10 / 0", lingua=lingua)
    start = time.perf_counter()
    div0_res = executor.execute_graph(div0_graph)
    failure_bench["divide_by_zero_us"] = round((time.perf_counter() - start) * 1_000_000, 2)
    assert div0_res["ok"] is False
    assert div0_res["error"] == IRFailureCode.DIVIDE_BY_ZERO.value

    # Unsupported action fails closed (dependency unavailable)
    unsupported_graph = logic_expr_to_ir(("ACTION", "TELEPORT", "mars"))
    start = time.perf_counter()
    unsupported_res = executor.execute_graph(unsupported_graph)
    failure_bench["unsupported_action_fail_closed_us"] = round((time.perf_counter() - start) * 1_000_000, 2)
    assert unsupported_res["ok"] is False
    assert unsupported_res["error"] == IRFailureCode.DEPENDENCY_UNAVAILABLE.value

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
        "compilation_latency_text_to_ir_us": quantiles(compile_latencies_us),
        "execution_latency_us": {
            "cold_execution_us": round(cold_latency_us, 2),
            "cached_replay_us": quantiles(cached_latencies_us),
            "cache_speedup_ratio": round(cold_latency_us / statistics.mean(cached_latencies_us), 2),
        },
        "typed_failures_us": failure_bench,
        "sample_compiled_artifacts": sample_artifacts,
    }


def main() -> int:
    print("=" * 65)
    print("       JAYA BENCHMARK: PILAR P21 LINGUA LOGICA COMPILER")
    print("=" * 65)

    result = run_benchmark(iterations=1000)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
