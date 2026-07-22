# Benchmark — JAYA_OS

## Overview

JAYA_OS benchmarks measure the **runtime performance** of the house layer: feature compilation, mounting, action dispatch, and UI rendering. These are separate from JAYA_CORE's cognitive benchmarks.

---

## Benchmark Categories

### 1. Feature Compilation Benchmark

**What it measures**: Time to compile SceneGraph → Python feature package.

```bash
python scripts/benchmark_compile.py --rounds 100 --scene login_dialog
```

**Metrics:**
| Metric | Target |
|---|---|
| Cold compile (first time) | < 500ms |
| Warm compile (cached) | < 50ms |
| SceneGraph validation | < 10ms |
| Code generation | < 100ms |
| Disk write | < 50ms |

### 2. Feature Mount Benchmark

**What it measures**: Time to mount a compiled feature in sandbox.

```bash
python scripts/benchmark_mount.py --rounds 100 --feature login_dialog
```

**Metrics:**
| Metric | Target |
|---|---|
| Mount (cold) | < 200ms |
| Mount (warm, cached module) | < 50ms |
| Sandbox setup | < 30ms |
| Module load | < 20ms |
| Capability proxy injection | < 10ms |

### 3. Action Dispatch Benchmark

**What it measures**: Latency of dispatching action to mounted feature.

```bash
python scripts/benchmark_dispatch.py --rounds 1000 --feature login_dialog --action submit
```

**Metrics:**
| Metric | Target |
|---|---|
| Dispatch (p50) | < 5ms |
| Dispatch (p95) | < 20ms |
| Feature execution | < 10ms |
| Result serialization | < 2ms |
| IPC round-trip | < 5ms |

### 4. UI Rendering Benchmark

**What it measures**: Time to render widget tree to window.

```bash
python scripts/benchmark_ui_render.py --rounds 100 --scene dashboard
```

**Metrics:**
| Metric | Target |
|---|---|
| Window creation | < 100ms |
| Widget tree layout | < 50ms |
| Initial paint | < 200ms |
| Layout recalculation | < 10ms |
| Style resolution | < 5ms |

### 5. IPC Throughput Benchmark

**What it measures**: Message throughput between brain/house/features.

```bash
python scripts/benchmark_ipc.py --rounds 10000 --channel brain
```

**Metrics:**
| Metric | Target |
|---|---|
| Messages/sec (single thread) | > 10,000 |
| Latency (p50) | < 1ms |
| Latency (p99) | < 10ms |
| Max message size | 1MB |

---

## Running Benchmarks

### Individual Benchmarks
```bash
# Compile benchmark
python scripts/benchmark_compile.py --rounds 100

# Mount benchmark
python scripts/benchmark_mount.py --rounds 100

# Dispatch benchmark
python scripts/benchmark_dispatch.py --rounds 1000

# UI render benchmark
python scripts/benchmark_ui_render.py --rounds 100

# IPC benchmark
python scripts/benchmark_ipc.py --rounds 10000
```

### Full Benchmark Suite
```bash
python scripts/benchmark_all.py --rounds 100 --json-out benchmark_results.json
```

### Continuous Benchmarking (CI)
```bash
python scripts/benchmark_all.py --rounds 50 --gate --fail-on-gate \
  --max-compile-ms 500 --max-mount-ms 200 --max-dispatch-p50-ms 5 \
  --max-render-ms 200 --min-ipc-throughput 10000
```

---

## Benchmark Gate Thresholds

| Benchmark | Threshold | Rationale |
|---|---|---|
| Feature compile (cold) | ≤ 500ms | Acceptable first-time cost |
| Feature compile (warm) | ≤ 50ms | Fast iteration |
| Feature mount (cold) | ≤ 200ms | Reasonable startup |
| Feature mount (warm) | ≤ 50ms | Fast re-mount |
| Action dispatch (p50) | ≤ 5ms | Responsive UI |
| Action dispatch (p95) | ≤ 20ms | Predictable tail |
| UI render (initial) | ≤ 200ms | Perceived instant |
| IPC throughput | ≥ 10,000 msg/s | High-throughput communication |

---

## Benchmark Output

### Console
```
============================================================
JAYA_OS Benchmark Suite
============================================================
Configuration:
  Rounds: 100
  Gate: True
  Max compile: 500ms
  Max mount: 200ms
  Max dispatch p50: 5ms
  Max render: 200ms
  Min IPC throughput: 10000 msg/s

Running benchmarks...

Feature Compile:
  Cold: p50=234ms, p95=412ms, max=487ms
  Warm: p50=12ms, p95=28ms, max=45ms
  ✅ PASS

Feature Mount:
  Cold: p50=87ms, p95=156ms, max=189ms
  Warm: p50=23ms, p95=41ms, max=52ms
  ✅ PASS

Action Dispatch:
  p50=2.1ms, p95=8.7ms, p99=15.3ms
  ✅ PASS

UI Render:
  Initial: p50=112ms, p95=178ms, max=195ms
  ✅ PASS

IPC Throughput:
  12,450 msg/s
  ✅ PASS

============================================================
Overall: PASSED ✅
============================================================
```

### JSON Snapshot (`benchmark_results.json`)
```json
{
  "timestamp": "2026-07-21T10:30:45.123Z",
  "version": "1.0",
  "config": {
    "rounds": 100,
    "max_compile_ms": 500,
    "max_mount_ms": 200,
    "max_dispatch_p50_ms": 5,
    "max_render_ms": 200,
    "min_ipc_throughput": 10000
  },
  "results": {
    "compile": {
      "cold": {"p50_ms": 234, "p95_ms": 412, "max_ms": 487},
      "warm": {"p50_ms": 12, "p95_ms": 28, "max_ms": 45}
    },
    "mount": {
      "cold": {"p50_ms": 87, "p95_ms": 156, "max_ms": 189},
      "warm": {"p50_ms": 23, "p95_ms": 41, "max_ms": 52}
    },
    "dispatch": {
      "p50_ms": 2.1,
      "p95_ms": 8.7,
      "p99_ms": 15.3
    },
    "render": {
      "initial": {"p50_ms": 112, "p95_ms": 178, "max_ms": 195}
    },
    "ipc": {
      "throughput_msg_per_sec": 12450
    }
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

## Historical Benchmarks

| Date | Version | Compile (warm) | Mount (warm) | Dispatch p50 | Render | IPC Throughput | Gate |
|---|---|---|---|---|---|---|---|
| 2026-07-21 | OS-0 | 12ms | 23ms | 2.1ms | 112ms | 12,450/s | ✅ |

---

## Custom Benchmarks

### Adding New Benchmark
```python
# scripts/benchmark_my_feature.py
import time
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.ui_spec import create_window, create_button, SceneGraph

def benchmark_my_feature(rounds=100):
    compiler = FeatureCompiler()
    
    scene = SceneGraph(
        name="Benchmark",
        description="Benchmark scene",
        root=create_window(title="Test", children=[
            create_button(label="Click", on_click="test")
        ])
    )
    
    # Warmup
    for _ in range(5):
        compiler.save_feature(scene, "./features", "bench")
    
    # Measure
    latencies = []
    for _ in range(rounds):
        start = time.perf_counter()
        compiler.save_feature(scene, "./features", "bench")
        latencies.append((time.perf_counter() - start) * 1000)
    
    latencies.sort()
    p50 = latencies[len(latencies)//2]
    p95 = latencies[int(len(latencies)*0.95)]
    
    print(f"p50: {p50:.1f}ms, p95: {p95:.1f}ms")
    return {"p50": p50, "p95": p95}

if __name__ == "__main__":
    benchmark_my_feature()
```

---

## CI Integration

### GitHub Actions
```yaml
# .github/workflows/jaya-os-benchmark.yml
name: JAYA_OS Benchmark Gate
on: [push, pull_request]
jobs:
  benchmark:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install deps
        run: |
          cd JAYA_OS
          pip install -r requirements.txt
      - name: Run benchmark gate
        run: |
          cd JAYA_OS
          python scripts/benchmark_all.py --rounds 50 --gate --fail-on-gate \
            --max-compile-ms 500 --max-mount-ms 200 --max-dispatch-p50-ms 5 \
            --max-render-ms 200 --min-ipc-throughput 10000
      - name: Upload Benchmark Snapshot
        uses: actions/upload-artifact@v4
        with:
          name: jaya-os-benchmark
          path: JAYA_OS/benchmark_results.json
```

---

## Interpreting Results

### Gate PASSED ✅
- Runtime meets performance targets
- Safe to deploy

### Gate FAILED ❌
**Common Causes:**
| Symptom | Likely Cause | Fix |
|---|---|---|
| High compile time | Complex SceneGraph, no caching | Optimize compiler, add caching |
| High mount time | Slow sandbox setup | Optimize sandbox initialization |
| High dispatch latency | Slow IPC, feature blocking | Optimize IPC, check feature code |
| Slow render | Complex widget tree | Simplify UI, optimize layout |
| Low IPC throughput | Serialization bottleneck | Use faster serialization (msgpack) |

**Debug Steps:**
```bash
# Verbose benchmark
python scripts/benchmark_compile.py --rounds 10 -v

# Profile specific benchmark
python -m cProfile -o compile.prof scripts/benchmark_compile.py --rounds 10
python -m pstats compile.prof
```

---

## 🔗 Related Docs

- [Testing](testing.md) — Test suite that validates benchmarks
- [Architecture Overview](../02-architecture/overview.md) — Benchmarked components
- [CLI Commands](../../01-getting-started/cli-commands.md) — Benchmark commands