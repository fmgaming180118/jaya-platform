"""Benchmark Phase 1 JayaIR pipeline.

Measures cold and warm latency for repeated desktop/action intents,
then compares cache policies to help tune defaults.

Usage:
    python JAYA_CORE/scripts/benchmark_phase1_ir.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.brain_v2.engine.jaya_ir_exec import JayaIRExecutor  # noqa: E402
from src.brain_v2.soul.lingua_logica import LinguaLogica  # noqa: E402

DESKTOP_ACTION_INTENTS: Sequence[str] = (
    "open desktop",
    "create new window",
    "show window",
    "move window left",
    "copy window profile",
    "close window",
    "open file explorer",
    "search project files",
    "list open windows",
    "reset window layout",
)


@dataclass
class BenchmarkResult:
    label: str
    cold_p50_ms: float
    cold_p95_ms: float
    warm_p50_ms: float
    warm_p95_ms: float
    cache_hit_rate: float
    cache_items: int


@dataclass
class GateConfig:
    max_warm_p50_ms: float = 0.0500
    max_warm_p95_ms: float = 0.1000
    min_hit_rate: float = 0.95


@dataclass
class GateStatus:
    passed: bool
    failures: List[str]


DEFAULT_POLICIES: Tuple[Tuple[int, float], ...] = (
    (128, 120.0),
    (256, 300.0),
    (512, 300.0),
    (768, 600.0),
)


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[idx]


def run_once(cache_size: int, ttl_s: float, rounds: int) -> BenchmarkResult:
    lingua = LinguaLogica(cache_size=1024)
    ex = JayaIRExecutor(cache_size=cache_size, ttl_s=ttl_s)

    cold_latencies: List[float] = []
    warm_latencies: List[float] = []

    # Cold run: first pass over intents.
    for text in DESKTOP_ACTION_INTENTS:
        expr = lingua.encode(text)
        t0 = time.perf_counter()
        out = ex.execute_logic_expr(expr)
        dt_ms = (time.perf_counter() - t0) * 1000.0
        if not out.get("ok"):
            raise RuntimeError(f"execution failed in cold run: {out}")
        cold_latencies.append(dt_ms)

    # Warm run: repeated rounds over the same intents.
    for _ in range(rounds):
        for text in DESKTOP_ACTION_INTENTS:
            expr = lingua.encode(text)
            t0 = time.perf_counter()
            out = ex.execute_logic_expr(expr)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            if not out.get("ok"):
                raise RuntimeError(f"execution failed in warm run: {out}")
            warm_latencies.append(dt_ms)

    st = ex.status()
    return BenchmarkResult(
        label=f"cache={cache_size},ttl={int(ttl_s)}",
        cold_p50_ms=percentile(cold_latencies, 50),
        cold_p95_ms=percentile(cold_latencies, 95),
        warm_p50_ms=percentile(warm_latencies, 50),
        warm_p95_ms=percentile(warm_latencies, 95),
        cache_hit_rate=float(st["hit_rate"]),
        cache_items=int(st["cache_size"]),
    )


def summarize(results: Sequence[BenchmarkResult]) -> None:
    print("JAYA Phase 1 Benchmark (desktop/action repeated)")
    print("=" * 72)
    for r in results:
        print(
            f"{r.label:20} | "
            f"cold p50/p95={r.cold_p50_ms:.4f}/{r.cold_p95_ms:.4f} ms | "
            f"warm p50/p95={r.warm_p50_ms:.4f}/{r.warm_p95_ms:.4f} ms | "
            f"hit_rate={r.cache_hit_rate:.3f} | items={r.cache_items}"
        )

    best = min(results, key=lambda x: (x.warm_p50_ms, x.warm_p95_ms))
    print("-" * 72)
    print(
        "BEST POLICY: "
        f"{best.label} (warm p50={best.warm_p50_ms:.4f} ms, "
        f"warm p95={best.warm_p95_ms:.4f} ms, hit_rate={best.cache_hit_rate:.3f})"
    )


def evaluate_gate(results: Sequence[BenchmarkResult], gate: GateConfig) -> GateStatus:
    failures: List[str] = []
    for r in results:
        if r.warm_p50_ms > gate.max_warm_p50_ms:
            failures.append(
                f"{r.label}: warm_p50_ms={r.warm_p50_ms:.4f} > "
                f"{gate.max_warm_p50_ms:.4f}"
            )
        if r.warm_p95_ms > gate.max_warm_p95_ms:
            failures.append(
                f"{r.label}: warm_p95_ms={r.warm_p95_ms:.4f} > "
                f"{gate.max_warm_p95_ms:.4f}"
            )
        if r.cache_hit_rate < gate.min_hit_rate:
            failures.append(
                f"{r.label}: hit_rate={r.cache_hit_rate:.3f} < {gate.min_hit_rate:.3f}"
            )
        if r.warm_p50_ms > r.cold_p50_ms:
            failures.append(
                f"{r.label}: warm_p50_ms={r.warm_p50_ms:.4f} worse than "
                f"cold_p50_ms={r.cold_p50_ms:.4f}"
            )
        if r.warm_p95_ms > r.cold_p95_ms:
            failures.append(
                f"{r.label}: warm_p95_ms={r.warm_p95_ms:.4f} worse than "
                f"cold_p95_ms={r.cold_p95_ms:.4f}"
            )
    return GateStatus(passed=(len(failures) == 0), failures=failures)


def print_gate_status(status: GateStatus) -> None:
    if status.passed:
        print("BENCHMARK GATE: PASS")
        return
    print("BENCHMARK GATE: FAIL")
    for line in status.failures:
        print(f"  - {line}")


def run_policy_grid(
    policies: Sequence[Tuple[int, float]], rounds: int
) -> List[BenchmarkResult]:
    return [run_once(cache_size=c, ttl_s=t, rounds=rounds) for c, t in policies]


def _parse_policy(raw: str) -> Tuple[int, float]:
    if ":" not in raw:
        raise ValueError(f"invalid policy format: {raw}; expected <cache>:<ttl>")
    cache_s, ttl_s = raw.split(":", 1)
    return (int(cache_s), float(ttl_s))


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Benchmark JayaIR desktop/action latency")
    p.add_argument(
        "--rounds",
        type=int,
        default=80,
        help="warm rounds per intent (default: 80)",
    )
    p.add_argument(
        "--policy",
        action="append",
        default=[],
        help="policy in format <cache>:<ttl>, may be repeated",
    )
    p.add_argument(
        "--json-out",
        default="",
        help="optional path to save benchmark result JSON",
    )
    p.add_argument(
        "--gate",
        action="store_true",
        help="evaluate benchmark gate thresholds",
    )
    p.add_argument(
        "--max-warm-p50-ms",
        type=float,
        default=0.0500,
        help="gate threshold for warm p50 latency in milliseconds",
    )
    p.add_argument(
        "--max-warm-p95-ms",
        type=float,
        default=0.1000,
        help="gate threshold for warm p95 latency in milliseconds",
    )
    p.add_argument(
        "--min-hit-rate",
        type=float,
        default=0.95,
        help="gate threshold for minimum cache hit rate",
    )
    p.add_argument(
        "--fail-on-gate",
        action="store_true",
        help="exit code 2 when gate fails",
    )
    return p


def _write_json(path: str, results: Sequence[BenchmarkResult]) -> None:
    data = {
        "results": [asdict(r) for r in results],
        "best": asdict(min(results, key=lambda x: (x.warm_p50_ms, x.warm_p95_ms))),
    }
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    args = _build_parser().parse_args()
    policies = (
        tuple(_parse_policy(raw) for raw in args.policy)
        if args.policy
        else DEFAULT_POLICIES
    )
    results = run_policy_grid(policies=policies, rounds=max(1, args.rounds))
    summarize(results)
    if args.json_out:
        _write_json(args.json_out, results)
    if args.gate:
        gate = GateConfig(
            max_warm_p50_ms=float(args.max_warm_p50_ms),
            max_warm_p95_ms=float(args.max_warm_p95_ms),
            min_hit_rate=float(args.min_hit_rate),
        )
        gate_status = evaluate_gate(results, gate)
        print_gate_status(gate_status)
        if args.fail_on_gate and not gate_status.passed:
            sys.exit(2)
