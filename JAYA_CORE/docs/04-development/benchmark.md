# Benchmark — JAYA_CORE

## Overview

JAYA_CORE uses **benchmark gates** to ensure cognitive performance meets strict thresholds. Benchmarks measure the **intent-to-action latency** of the reasoning pipeline, not raw model inference speed.

---

## Phase 1 Benchmark: JayaIR Pipeline

### What It Measures

```
Intent → Lingua Logica → JayaIR → TaskPlanner → IronEngine (cached) → Result
                    │                                    │
                    └──────────── Cache Hit ────────────┘
```

**Metrics:**
- **p50 latency (warm)**: Median latency on cache hits
- **p95 latency (warm)**: 95th percentile on cache hits  
- **Hit rate**: Percentage of executions using cached plans
- **Cold latency**: First execution (no cache)

### Running Benchmarks

```bash
# Smoke test (10 rounds, ~5 seconds)
python scripts/benchmark_phase1_ir.py --rounds 10

# CI Gate (40 rounds, strict thresholds)
python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate \
  --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95

# Documentation Snapshot (80 rounds)
python scripts/benchmark_phase1_ir.py --rounds 80 --gate \
  --json-out docs/phase1_benchmark_latest.json
```

### Thresholds (Phase 1 Gate)

| Metric | Threshold | Rationale |
|---|---|---|
| p50 warm | ≤ 0.05 ms | Sub-millisecond cognitive step |
| p95 warm | ≤ 0.10 ms | Predictable tail latency |
| Hit rate | ≥ 95% | Effective plan caching |
| p50 cold | ≤ 5.0 ms | Acceptable first-run cost |

### Benchmark Output

**Console:**
```
============================================================
JAYA Phase 1 Benchmark — JayaIR Pipeline
============================================================
Configuration:
  Rounds: 40
  Gate: True
  Max warm p50: 0.05 ms
  Max warm p95: 0.10 ms
  Min hit rate: 0.95

Warming up cache...
Running benchmark...

Results:
  Cold runs (first 5):     p50=2.34ms  p95=4.12ms
  Warm runs (cached):      p50=0.032ms p95=0.078ms
  Cache hit rate:          97.5%
  Total iterations:        40

Gate Status: PASSED ✅
  p50 warm (0.032ms) ≤ 0.05ms ✅
  p95 warm (0.078ms) ≤ 0.10ms ✅
  Hit rate (97.5%) ≥ 95% ✅
```

**JSON Snapshot (`phase1_benchmark_latest.json`):**
```json
{
  "timestamp": "2026-07-21T10:30:45.123Z",
  "version": "1.0",
  "config": {
    "rounds": 80,
    "max_warm_p50_ms": 0.05,
    "max_warm_p95_ms": 0.10,
    "min_hit_rate": 0.95
  },
  "results": {
    "cold": {"p50_ms": 2.34, "p95_ms": 4.12, "count": 5},
    "warm": {"p50_ms": 0.032, "p95_ms": 0.078, "count": 75},
    "hit_rate": 0.975,
    "total_iterations": 80
  },
  "gate_passed": true,
  "environment": {
    "python": "3.12.7",
    "platform": "Windows-10",
    "cpu": "Intel i7-1165G7",
    "ram_gb": 16
  }
}
```

---

## Benchmark Methodology

### Warm-up Phase
1. Execute 5 unique intents to populate cache
2. Verify cache population via `engine.status()["cache_stats"]`

### Measurement Phase
1. Repeat same intents (cache hits expected)
2. Measure latency per iteration (high-resolution timer)
3. Track cache hits/misses

### Statistical Rigor
- **Outlier removal**: Trim top/bottom 5% before percentile calculation
- **Steady state**: Discard first 2 warm iterations (JIT warmup)
- **Confidence**: 40+ rounds for statistical significance

---

## Resource-Aware Benchmarking

### Under Load
```bash
# Simulate CPU load (separate terminal)
# Windows: start /b python -c "while True: pass"
# Linux: yes > /dev/null &

# Run benchmark under load
python scripts/benchmark_phase1_ir.py --rounds 20 --gate \
  --max-warm-p50-ms 0.10 --max-warm-p95-ms 0.20 --min-hit-rate 0.90
```

### Expected Behavior Under Load
- `ResourceMonitor` detects high CPU
- `topk_ratio` reduces automatically
- Latency may increase but hit rate maintained
- Silence mode activates at CPU ≥ 85%

---

## Historical Benchmarks

| Date | Version | p50 Warm (ms) | p95 Warm (ms) | Hit Rate | Gate |
|---|---|---|---|---|---|
| 2026-07-21 | Phase 3C | 0.032 | 0.078 | 97.5% | ✅ |
| 2026-06-15 | Phase 2 | 0.041 | 0.092 | 96.2% | ✅ |
| 2026-03-27 | Phase 1 | 0.048 | 0.105 | 94.8% | ❌ |

---

## Custom Benchmarks

### Adding New Benchmark
```python
# scripts/benchmark_my_feature.py
import time
from src.brain_v2.engine.runtime import IronEngine, AgiConfig

def benchmark_my_feature(rounds=100):
    engine = IronEngine(AgiConfig())
    
    # Warmup
    for i in range(5):
        engine.execute_intent(f"test intent {i}")
    
    # Measure
    latencies = []
    for i in range(rounds):
        start = time.perf_counter()
        engine.execute_intent("repeated intent")
        latencies.append((time.perf_counter() - start) * 1000)
    
    # Stats
    latencies.sort()
    p50 = latencies[len(latencies)//2]
    p95 = latencies[int(len(latencies)*0.95)]
    
    print(f"p50: {p50:.3f}ms, p95: {p95:.3f}ms")
    return {"p50": p50, "p95": p95}

if __name__ == "__main__":
    benchmark_my_feature()
```

---

## CI Integration

### GitHub Actions
```yaml
# .github/workflows/phase1-benchmark-gate.yml
- name: Run Phase 1 Benchmark Gate
  run: |
    cd JAYA_CORE
    python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate \
      --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

### Artifact Upload
```yaml
- name: Upload Benchmark Snapshot
  uses: actions/upload-artifact@v4
  with:
    name: phase1-benchmark
    path: JAYA_CORE/docs/phase1_benchmark_latest.json
```

---

## Interpreting Results

### Gate PASSED ✅
- Cognitive pipeline meets performance targets
- Plan caching effective
- Safe to promote/deploy

### Gate FAILED ❌
**Common Causes:**
| Symptom | Likely Cause | Fix |
|---|---|---|
| High p50/p95 | Cache not warming | Check `cache_plan()` calls |
| Low hit rate | Cache eviction | Increase `plan_cache_size` |
| High cold latency | Slow JayaIR compile | Optimize translator |
| Regression | Code change | Bisect recent commits |

**Debug Steps:**
```bash
# Verbose benchmark
python scripts/benchmark_phase1_ir.py --rounds 10 -v

# Check engine status
python -c "
from src.brain_v2.engine.runtime import IronEngine, AgiConfig
e = IronEngine(AgiConfig())
e.execute_intent('test')
print(e.status())
"
```

---

## 🔗 Related Docs

- [Testing](testing.md) — Test suite that validates benchmarks
- [Architecture Overview](../02-architecture/overview.md) — Benchmarked pipeline
- [CLI Commands](../../01-getting-started/cli-commands.md) — Benchmark commands
- [Roadmap Phase 1](../06-roadmap/phase-1-cognitive-foundation.md) — Benchmark gate in roadmap