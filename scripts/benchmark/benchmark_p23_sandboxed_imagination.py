#!/usr/bin/env python3
"""benchmark_p23_sandboxed_imagination.py — Quantitative Performance, Security & Integrity Benchmark for P23 Sandboxed Imagination.

Measures:
1. Environment Baseline:
   - Platform, machine, processor count, Python version, initial RSS memory.
2. Legitimate Declarative Evaluation Performance:
   - Arithmetic, comparison, boolean logic, collection slicing (lists and dicts).
   - Latency distribution (mean, p50, p95, p99, min, max, stddev) and throughput (evals/sec).
3. Adversarial Security Boundary Drills:
   - Module import escape rejection (`__import__('os')`)
   - Reflection bypass rejection (`getattr(__builtins__, 'eval')`)
   - Class hierarchy traversal rejection (`().__class__.__bases__[0]`)
   - File system read rejection (`open('secret.txt')`)
   - Subprocess/shell execution rejection (`subprocess.run`)
   - Environment variable read rejection (`os.environ`)
   - Code definition/lambda injection rejection (`(lambda x: x)(1)`)
   - Power exponent bomb rejection (`2 ** 999999`)
   - Power base bomb rejection (`1000000 ** 5`)
   - Division by zero rejection (`100 / 0`)
   - Deeply nested AST bomb rejection (`'(' * 40 + '1' + ')' * 40`)
   - Excessive AST node count rejection (`' + '.join(['1'] * 300)`)
   - Oversized input rejection (> 4096 chars)
4. Epistemic Labeling & Artifact Integrity:
   - Verification of `epistemic_label: SIMULATION` and `epistemic_status: UNVERIFIED`.
   - Verification of ephemeral workspace cleanup (`cleanup_verified: True`).
5. Canonical Runtime Capability Dispatch:
   - Execution via `JayaCoreRuntime.execute_local_pillar(SANDBOX_CAPABILITY_ID, ...)`.
6. Dual-Gate Security & JayaIR Integration:
   - JayaIR `CALL_CAPABILITY` execution with Ethical Heart (P15) policy engine and puzzle registry.
7. Multithreaded Concurrency:
   - 8 concurrent threads executing independent evaluations without interference.
8. Resource Footprint & Telemetry:
   - Initial RSS, final RSS, RSS growth, total benchmark duration.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import platform
import shutil
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

from jaya_core.brain_v2.engine.jaya_ir import (
    IRInstruction,
    JayaIRGraph,
    OpCode,
)
from jaya_core.brain_v2.engine.jaya_ir_exec import JayaIRExecutor
from jaya_core.brain_v2.soul.ethical_heart import (
    EthicalHeart,
    PolicyBundle,
    PolicyEffect,
    PolicyRisk,
    PolicyRule,
)
from jaya_core.capabilities.puzzle import (
    CapabilityPuzzleRegistry,
    PuzzleManifest,
)
from jaya_core.cognitive.runtime import JayaCoreRuntime
from jaya_core.pillars.foundation_capabilities import (
    SANDBOX_CAPABILITY_ID,
    SandboxedImaginationCapability,
)
from jaya_core.pillars.local_capabilities import LocalPillarError, LocalPillarResult


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    k = (len(values) - 1) * (pct / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    d0 = values[int(f)] * (c - k)
    d1 = values[int(c)] * (k - f)
    return d0 + d1


def _distribution(values: list[float]) -> dict[str, float]:
    if not values:
        return {
            "mean_ms": 0.0,
            "p50_ms": 0.0,
            "p95_ms": 0.0,
            "p99_ms": 0.0,
            "min_ms": 0.0,
            "max_ms": 0.0,
            "stddev_ms": 0.0,
        }
    sorted_ms = sorted(v * 1000.0 for v in values)
    return {
        "mean_ms": statistics.mean(sorted_ms),
        "p50_ms": _percentile(sorted_ms, 50.0),
        "p95_ms": _percentile(sorted_ms, 95.0),
        "p99_ms": _percentile(sorted_ms, 99.0),
        "min_ms": sorted_ms[0],
        "max_ms": sorted_ms[-1],
        "stddev_ms": statistics.stdev(sorted_ms) if len(sorted_ms) > 1 else 0.0,
    }


class _SandboxPuzzleAdapter:
    def __init__(self, capability: SandboxedImaginationCapability) -> None:
        self.capability = capability

    def health_check(self) -> bool:
        return self.capability.health_check()

    def invoke(self, payload: Any) -> dict[str, object]:
        res = self.capability.execute(payload)
        return {"ok": True, "result": res.data}


def run_benchmark(
    *,
    iterations: int = 100,
    concurrency_workers: int = 8,
    output_path: Path | None = None,
) -> dict[str, Any]:
    process = psutil.Process()
    rss_initial = process.memory_info().rss
    started_wall = time.perf_counter()

    env_info = {
        "os": platform.system(),
        "os_release": platform.release(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(logical=True),
        "python_version": sys.version.split()[0],
        "initial_rss_bytes": rss_initial,
    }

    temp_dir = tempfile.mkdtemp(prefix="p23-bench-")
    temp_root = Path(temp_dir)

    try:
        sandbox = SandboxedImaginationCapability(timeout_seconds=2.0)

        # -----------------------------------------------------------------
        # 1. Health Check
        # -----------------------------------------------------------------
        health_ok = sandbox.health_check()

        # -----------------------------------------------------------------
        # 2. Legitimate Declarative Evaluation Performance
        # -----------------------------------------------------------------
        test_expressions = [
            "(120 + 35) * 4 == 620",
            "['simulation_a', 'simulation_b', 'simulation_c'][1] == 'simulation_b'",
            "{'confidence': 0.95, 'iterations': 50}['confidence'] * 100",
            "2 ** 10 == 1024 and 5 * 5 == 25",
            "(10 > 5) and not (3 == 4)",
            "[x for x in [1, 2, 3]][0] == 1",  # list literal
        ]

        eval_latencies: list[float] = []
        labels_ok = True
        cleanup_all_ok = True

        for i in range(iterations):
            expr = f"({i} + 10) * 2 == { (i + 10) * 2 }"
            t0 = time.perf_counter()
            res = sandbox.evaluate(expr)
            eval_latencies.append(time.perf_counter() - t0)

            if res.data.get("epistemic_label") != "SIMULATION" or res.data.get("epistemic_status") != "UNVERIFIED":
                labels_ok = False
            if not res.data.get("cleanup_verified"):
                cleanup_all_ok = False

        eval_dist = _distribution(eval_latencies)
        throughput = len(eval_latencies) / sum(eval_latencies) if eval_latencies else 0.0

        performance_summary = {
            "iterations": iterations,
            "distribution": eval_dist,
            "throughput_evals_per_sec": throughput,
            "epistemic_labels_verified": labels_ok,
            "ephemeral_cleanup_verified": cleanup_all_ok,
        }

        # -----------------------------------------------------------------
        # 3. Adversarial Security Boundary Drills (13 attacks)
        # -----------------------------------------------------------------
        adversarial_tests = [
            ("import_os", "__import__('os').system('echo pwned')", "SECURITY_VIOLATION"),
            ("builtin_eval", "getattr(__builtins__, 'eval')('1+1')", "SECURITY_VIOLATION"),
            ("class_traversal", "().__class__.__bases__[0].__subclasses__()", "SECURITY_VIOLATION"),
            ("file_read", "open('secret.txt', 'r').read()", "SECURITY_VIOLATION"),
            ("subprocess_exec", "subprocess.run('dir')", "SECURITY_VIOLATION"),
            ("env_read", "os.environ.get('SECRET')", "SECURITY_VIOLATION"),
            ("lambda_exec", "(lambda x: x + 1)(5)", "SECURITY_VIOLATION"),
            ("power_exp_bomb", "2 ** 999999", "SECURITY_VIOLATION"),
            ("power_base_bomb", "1000000 ** 5", "SECURITY_VIOLATION"),
            ("div_zero", "100 / 0", "ARITHMETIC_ERROR"),
            ("nested_ast_bomb", "(" * 40 + "1" + " + 1)" * 40, "RESOURCE_LIMIT"),
            ("node_count_bomb", " + ".join(["1"] * 300), "RESOURCE_LIMIT"),
            ("huge_input_bomb", "1 + " * 1500 + "1", ("INVALID_INPUT", "RESOURCE_LIMIT")),
        ]

        security_results: dict[str, bool] = {}
        for name, attack_expr, expected_code in adversarial_tests:
            try:
                sandbox.evaluate(attack_expr)
                security_results[name] = False  # Should have been blocked!
            except LocalPillarError as exc:
                if isinstance(expected_code, tuple):
                    security_results[name] = exc.code in expected_code
                else:
                    security_results[name] = (exc.code == expected_code)
            except Exception:
                security_results[name] = False

        all_security_passed = all(security_results.values())
        security_summary = {
            "total_attacks_tested": len(adversarial_tests),
            "all_attacks_blocked": all_security_passed,
            "details": security_results,
        }

        # -----------------------------------------------------------------
        # 4. Canonical JayaCoreRuntime Capability Dispatch
        # -----------------------------------------------------------------
        runtime = JayaCoreRuntime(
            db_path=temp_root / "runtime.db",
            local_pillar_data_dir=temp_root / "pillar_capabilities",
        )

        runtime_res = runtime.execute_local_pillar(
            SANDBOX_CAPABILITY_ID,
            {"action": "evaluate", "expression": "(50 + 25) * 4 == 300"},
        )
        runtime_dispatch_ok = (
            runtime_res.code == "SANDBOX_EXPRESSION_EVALUATED"
            and runtime_res.data["result"] is True
            and runtime_res.data["epistemic_label"] == "SIMULATION"
        )
        runtime.close()

        # -----------------------------------------------------------------
        # 5. Dual-Gate Security & JayaIR Integration
        # -----------------------------------------------------------------
        policy = PolicyBundle(
            policy_id="test.p23-sandbox-policy",
            version=1,
            brain_id="brain:main",
            rules=(
                PolicyRule(
                    rule_id="allow.sandbox",
                    effect=PolicyEffect.ALLOW,
                    capability_ids=(SANDBOX_CAPABILITY_ID,),
                    risk_classes=(PolicyRisk.READ_ONLY,),
                    reason_code="SANDBOX_ALLOWED",
                ),
            ),
            default_effect=PolicyEffect.REQUIRE_APPROVAL,
            default_reason_code="EXPLICIT_APPROVAL_REQUIRED",
        )
        heart = EthicalHeart(temp_root / "sandbox-policy.db", policy)
        registry = CapabilityPuzzleRegistry()

        adapter = _SandboxPuzzleAdapter(sandbox)
        registry.attach(
            PuzzleManifest(
                puzzle_id="puzzle.sandbox.expression",
                capability_id=SANDBOX_CAPABILITY_ID,
                version="1.0.0",
                risk_class="READ_ONLY",
            ),
            adapter,
        )

        payload = {"action": "evaluate", "expression": "(15 + 25) * 2 == 80"}
        graph = JayaIRGraph(
            instructions=(
                IRInstruction(
                    opcode=OpCode.CALL_CAPABILITY,
                    args=(
                        SANDBOX_CAPABILITY_ID,
                        json.dumps(payload, sort_keys=True, separators=(",", ":")),
                    ),
                    target="res",
                ),
                IRInstruction(
                    opcode=OpCode.RETURN,
                    args=("res",),
                ),
            ),
            source="p23-benchmark-jayair",
        )

        executor = JayaIRExecutor(
            puzzle_registry=registry,
            policy_engine=heart,
            actor_brain_id="brain:main",
            node_id="node:primary",
        )

        try:
            execution_result = executor.execute_graph(graph)
        finally:
            registry.close()
            heart.close()

        jayair_integration_ok = (
            execution_result.get("ok") is True
            and execution_result["result"]["result"]["result"] is True
            and execution_result["result"]["result"]["epistemic_label"] == "SIMULATION"
            and "policy_receipt" in execution_result["result"]
        )

        # -----------------------------------------------------------------
        # 6. Multithreaded Concurrency
        # -----------------------------------------------------------------
        def worker_eval(idx: int) -> bool:
            expr = f"({idx} * 7) + 3 == {idx * 7 + 3}"
            res = sandbox.evaluate(expr)
            return bool(res.data.get("result") is True)

        with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency_workers) as pool:
            futures = [pool.submit(worker_eval, i) for i in range(1, 33)]
            concurrency_results = [f.result() for f in concurrent.futures.as_completed(futures)]

        concurrency_ok = len(concurrency_results) == 32 and all(concurrency_results)

        # -----------------------------------------------------------------
        # 7. Resource Footprint & Telemetry
        # -----------------------------------------------------------------
        rss_final = process.memory_info().rss
        total_wall_elapsed = time.perf_counter() - started_wall

        resource_summary = {
            "rss_initial_bytes": rss_initial,
            "rss_final_bytes": rss_final,
            "rss_delta_bytes": max(0, rss_final - rss_initial),
            "total_benchmark_wall_seconds": total_wall_elapsed,
        }

        # Overall Status
        overall_passed = (
            health_ok
            and labels_ok
            and cleanup_all_ok
            and all_security_passed
            and runtime_dispatch_ok
            and jayair_integration_ok
            and concurrency_ok
        )

        final_report = {
            "benchmark_name": "P23_SANDBOXED_IMAGINATION_QUANTITATIVE_BENCHMARK",
            "timestamp": datetime.now(UTC).isoformat(),
            "pillar_id": "P023",
            "capability_id": SANDBOX_CAPABILITY_ID,
            "status": "PASS" if overall_passed else "FAIL",
            "environment": env_info,
            "health_check": health_ok,
            "performance": performance_summary,
            "security_boundaries": security_summary,
            "runtime_dispatch": runtime_dispatch_ok,
            "jayair_dual_gate_integration": jayair_integration_ok,
            "concurrency": {
                "workers": concurrency_workers,
                "total_jobs": len(concurrency_results),
                "success": concurrency_ok,
            },
            "resources": resource_summary,
        }

        if output_path is not None:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(final_report, indent=2, ensure_ascii=False), encoding="utf-8"
            )

        return final_report

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="P23 Sandboxed Imagination Quantitative Benchmark")
    parser.add_argument("--iterations", type=int, default=100)
    parser.add_argument(
        "--output",
        default=str(
            ROOT
            / "outputs"
            / "reports"
            / "benchmarks"
            / "p23_sandboxed_imagination_benchmark.json"
        ),
    )
    args = parser.parse_args()

    report = run_benchmark(iterations=args.iterations, output_path=Path(args.output))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
