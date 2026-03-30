"""Unit tests for benchmark gate logic."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.benchmark_phase1_ir import BenchmarkResult, GateConfig, evaluate_gate


class TestPhase1BenchmarkGate(unittest.TestCase):
    def test_gate_passes_for_healthy_metrics(self):
        results = [
            BenchmarkResult(
                label="cache=512,ttl=300",
                cold_p50_ms=0.0200,
                cold_p95_ms=0.0300,
                warm_p50_ms=0.0090,
                warm_p95_ms=0.0100,
                cache_hit_rate=0.988,
                cache_items=10,
            )
        ]
        gate = GateConfig(max_warm_p50_ms=0.05, max_warm_p95_ms=0.1, min_hit_rate=0.95)
        status = evaluate_gate(results, gate)
        self.assertTrue(status.passed)
        self.assertEqual(len(status.failures), 0)

    def test_gate_fails_for_bad_metrics(self):
        results = [
            BenchmarkResult(
                label="cache=bad",
                cold_p50_ms=0.0200,
                cold_p95_ms=0.0300,
                warm_p50_ms=0.0700,
                warm_p95_ms=0.2000,
                cache_hit_rate=0.800,
                cache_items=10,
            )
        ]
        gate = GateConfig(max_warm_p50_ms=0.05, max_warm_p95_ms=0.1, min_hit_rate=0.95)
        status = evaluate_gate(results, gate)
        self.assertFalse(status.passed)
        self.assertGreaterEqual(len(status.failures), 3)


if __name__ == "__main__":
    unittest.main()
