#!/usr/bin/env python3
"""benchmark_p01_pure_logic.py — Performance & Resource Benchmark for P01 Pure Logic.

Measures:
- Latency (min, p50, p90, p99, max) across 1,000 evaluations.
- RSS Memory consumption before and after.
- Proof size (steps, JSON serialization bytes).
- Multi-theory performance (Theory 1: Deep chain, Theory 2: Multi-premise mesh).
- All truth states: PROVED, DISPROVED, UNKNOWN, CONFLICT.
"""

from __future__ import annotations

import json
import os
import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_SRC = ROOT / "packages" / "jaya-core" / "src"
if str(CORE_SRC) not in sys.path:
    sys.path.insert(0, str(CORE_SRC))

import psutil  # noqa: E402
from jaya_core.reasoning.pure_logic import (  # noqa: E402
    Literal,
    LogicProofStore,
    LogicRule,
    LogicStatus,
    LogicTheory,
    PureLogicService,
    PureLogicSolver,
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

    # Prepare Theory 1: Deep Linear Inference Chain (Depth = 10)
    # a0 -> a1 -> a2 -> ... -> a10
    t1_rules = tuple(
        LogicRule(f"r{i}", (Literal(f"a{i}"),), Literal(f"a{i+1}"))
        for i in range(10)
    )
    t1_facts = (Literal("a0"),)
    t1_theory = LogicTheory(facts=t1_facts, rules=t1_rules)
    t1_query = Literal("a10")

    # Prepare Theory 2: Multi-Premise Mesh (3 premises per rule, 3 cascading rules)
    t2_rules = (
        LogicRule("mesh-1", (Literal("f1"), Literal("f2"), Literal("f3")), Literal("sub_goal_1")),
        LogicRule("mesh-2", (Literal("f4"), Literal("f5"), Literal("sub_goal_1")), Literal("sub_goal_2")),
        LogicRule("mesh-3", (Literal("sub_goal_2"), Literal("f6")), Literal("action_authorized")),
    )
    t2_facts = (Literal("f1"), Literal("f2"), Literal("f3"), Literal("f4"), Literal("f5"), Literal("f6"))
    t2_theory = LogicTheory(facts=t2_facts, rules=t2_rules)
    t2_query = Literal("action_authorized")

    solver = PureLogicSolver()

    # 1. Pure In-Memory Solver: Theory 1 Latency
    t1_latencies_us: list[float] = []
    t1_last_res = None
    for i in range(iterations):
        start = time.perf_counter()
        t1_last_res = solver.solve(f"t1-{i}", t1_theory, t1_query)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        t1_latencies_us.append(elapsed_us)
    assert t1_last_res is not None and t1_last_res.status is LogicStatus.PROVED

    # 2. Pure In-Memory Solver: Theory 2 Latency
    t2_latencies_us: list[float] = []
    t2_last_res = None
    for i in range(iterations):
        start = time.perf_counter()
        t2_last_res = solver.solve(f"t2-{i}", t2_theory, t2_query)
        elapsed_us = (time.perf_counter() - start) * 1_000_000
        t2_latencies_us.append(elapsed_us)
    assert t2_last_res is not None and t2_last_res.status is LogicStatus.PROVED

    # 3. Truth States Execution Times
    states_bench = {}
    # DISPROVED
    dis_theory = LogicTheory(facts=(Literal.parse("!a"),), rules=())
    start = time.perf_counter()
    dis_res = solver.solve("dis", dis_theory, Literal("a"))
    states_bench["DISPROVED_us"] = round((time.perf_counter() - start) * 1_000_000, 2)
    assert dis_res.status is LogicStatus.DISPROVED

    # UNKNOWN
    unk_theory = LogicTheory(facts=(Literal("b"),), rules=())
    start = time.perf_counter()
    unk_res = solver.solve("unk", unk_theory, Literal("a"))
    states_bench["UNKNOWN_us"] = round((time.perf_counter() - start) * 1_000_000, 2)
    assert unk_res.status is LogicStatus.UNKNOWN

    # CONFLICT
    conf_theory = LogicTheory(facts=(Literal("a"), Literal.parse("!a")), rules=())
    start = time.perf_counter()
    conf_res = solver.solve("conf", conf_theory, Literal("a"))
    states_bench["CONFLICT_us"] = round((time.perf_counter() - start) * 1_000_000, 2)
    assert conf_res.status is LogicStatus.CONFLICT

    # 4. Persistence Overhead (Solve + SQLite WAL Storage)
    persistence_latencies_ms: list[float] = []
    sample_proof_json = ""
    temp_dir = tempfile.mkdtemp(prefix="p01_bench_")
    db_path = Path(temp_dir) / "benchmark_logic.db"
    store = LogicProofStore(db_path)
    service = PureLogicService(store, solver)
    try:
        raw_t1_facts = ["a0"]
        raw_t1_rules = [{"id": f"r{i}", "if": [f"a{i}"], "then": f"a{i+1}"} for i in range(10)]
        for i in range(100):
            start = time.perf_counter()
            eval_res = service.evaluate(
                request_id=f"persist-{i}",
                facts=raw_t1_facts,
                rules=raw_t1_rules,
                query="a10",
            )
            elapsed_ms = (time.perf_counter() - start) * 1000
            persistence_latencies_ms.append(elapsed_ms)
            if i == 0:
                sample_proof_json = json.dumps(eval_res.to_dict())
    finally:
        service.close()
        # Clean up db cleanly
        for ext in ("", "-wal", "-shm"):
            f = Path(str(db_path) + ext)
            if f.exists():
                try:
                    f.unlink()
                except OSError:
                    pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

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
        "theory_1_deep_chain_us": quantiles(t1_latencies_us),
        "theory_2_mesh_us": quantiles(t2_latencies_us),
        "truth_states_single_call_us": states_bench,
        "persistence_with_sqlite_ms": quantiles(persistence_latencies_ms),
        "proof_size": {
            "chain_steps": len(t1_last_res.proof),
            "derived_literals": len(t1_last_res.derived_literals),
            "serialized_json_bytes": len(sample_proof_json.encode("utf-8")),
        },
    }


def main() -> int:
    print("=" * 65)
    print("       JAYA BENCHMARK: PILAR P01 PURE LOGIC INFERENCE")
    print("=" * 65)

    result = run_benchmark(iterations=1000)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
