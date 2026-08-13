"""Benchmark regression guard for Phase 1 JayaIR.

This test is intentionally lightweight and focuses on stable invariants:
- warm cache latency should not be worse than cold latency,
- cache hit-rate should stay high for repeated desktop/action intents.
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.benchmark_phase1_ir import run_once


class TestPhase1BenchmarkGuard(unittest.TestCase):
    def test_warm_path_is_faster_and_cache_hits_high(self):
        # Keep rounds modest for CI/local speed while preserving signal.
        result = run_once(cache_size=768, ttl_s=600.0, rounds=20)

        self.assertLessEqual(
            result.warm_p50_ms,
            result.cold_p50_ms,
            f"warm p50 {result.warm_p50_ms:.4f} should be <= cold p50 {result.cold_p50_ms:.4f}",
        )
        self.assertLessEqual(
            result.warm_p95_ms,
            result.cold_p95_ms,
            f"warm p95 {result.warm_p95_ms:.4f} should be <= cold p95 {result.cold_p95_ms:.4f}",
        )
        self.assertGreaterEqual(
            result.cache_hit_rate,
            0.90,
            f"cache hit-rate too low: {result.cache_hit_rate:.3f}",
        )


if __name__ == "__main__":
    unittest.main()
