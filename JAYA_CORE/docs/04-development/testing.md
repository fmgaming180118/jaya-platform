# Testing — JAYA_CORE

## Test Suite Overview

**Total: 211 tests** across cognitive, safety, and integration domains.

```bash
# Run all tests
python -m pytest tests/ -v --tb=short

# Run with coverage
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=term-missing
```

---

## Test Categories

### Phase 1: Cognitive Foundation

| Test File | Focus | Tests |
|---|---|---|
| `test_phase1_jaya_ir.py` | JayaIR parse/validate/execute | 15 |
| `test_phase1_ir_benchmark.py` | IR execution benchmark | 8 |
| `test_phase1_benchmark_gate.py` | Gate pass/fail logic | 6 |
| `test_phase1_architecture_boundary.py` | Brain↔House isolation | 4 |
| `test_phase1_language_capability_gate.py` | Language stack | 5 |
| `test_phase1_adaptive_memory_gate.py` | Memory strategy | 4 |
| `test_phase1_procedural_ranking_gate.py` | Procedure ranking | 4 |
| `test_phase1_procedural_maintenance_gate.py` | Procedure maintenance | 4 |
| `test_phase1_adaptive_policy_tuning_gate.py` | Policy adaptation | 4 |
| `test_phase1_policy_feedback_loop_gate.py` | Feedback loops | 4 |
| `test_phase1_policy_drift_guard_gate.py` | Drift detection | 4 |
| `test_phase1_language_policy_override_gate.py` | Policy overrides | 4 |
| `test_phase1_agentic_rag_runtime_gate.py` | Agentic RAG | 12 | 12 |
| `test_phase1_collective_pulse_gate.py` | Collective pulse | 6 |
| `test_phase1_dynamic_moe_gate.py` | Dynamic MoE | 6 |
| `test_phase1_twin_protocol_gate.py` | Twin protocol | 6 |
| `test_phase1_activation_sparsity_gate.py` | Activation sparsity | 6 |

### Phase 2: Safe Evolution

| Test File | Focus | Tests |
|---|---|---|
| `test_phase2_evolution_gate.py` | Promotion gate | 5 |
| `test_phase2_rollback.py` | Deterministic rollback | 4 |
| `test_phase2_manifest.py` | Signed manifest | 3 |

### Phase 3C: Dynamic Spec Generation

| Test File | Focus | Tests |
|---|---|---|
| `test_phase3c_intent_to_ui.py` | Intent→UI pipeline | 1 |

### Core Pillars (40 Pillars Integration)

| Test File | Focus | Tests |
|---|---|---|
| `test_new_pillars.py` | Pillars 1-40 integration | 45 |
| `test_core_twin.py` | Digital twin | 12 |
| `test_speaker_id.py` | Voice identity | 9 |
| `test_connection_manager.py` | Connectivity hierarchy | 6 |
| `test_v18_nano.py` | NanoModel V18 | 18 |

---

## Running Specific Test Groups

```bash
# Phase 1 only
python -m pytest tests/test_phase1_*.py -v

# Phase 2 only
python -m pytest tests/test_phase2_*.py -v

# Phase 3C only
python -m pytest tests/test_phase3c_*.py -v

# Pillar integration
python -m pytest tests/test_new_pillars.py -v

# Single test
python -m pytest tests/test_phase1_jaya_ir.py::test_jaya_ir_parse -v

# Pattern match
python -m pytest tests/ -k "benchmark" -v
python -m pytest tests/ -k "evolution" -v
python -m pytest tests/ -k "resource" -v
```

---

## Benchmark Gates

### Phase 1 Benchmark Gate (Strict)
```bash
python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate \
  --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

**Thresholds:**
- p50 latency (warm): ≤ 0.05 ms
- p95 latency (warm): ≤ 0.10 ms
- Cache hit rate: ≥ 95%

### Phase 1 Benchmark Snapshot
```bash
python scripts/benchmark_phase1_ir.py --rounds 80 --gate \
  --json-out docs/phase1_benchmark_latest.json
```

---

## Test Configuration

### pytest.ini (if needed)
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

### Test Environment
```bash
# Required packages
pip install pytest pytest-asyncio psutil numpy pydantic

# Optional: coverage
pip install pytest-cov
```

---

## Writing New Tests

### Structure
```python
# tests/test_my_feature.py
import pytest
from src.brain_v2.engine.my_module import MyClass

class TestMyFeature:
    def test_basic_functionality(self):
        obj = MyClass()
        result = obj.method()
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_async_behavior(self):
        result = await obj.async_method()
        assert result.success
```

### Test Fixtures (conftest.py)
```python
# tests/conftest.py
import pytest
from src.brain_v2.engine.runtime import IronEngine, AgiConfig

@pytest.fixture
def engine():
    config = AgiConfig()
    return IronEngine(config)

@pytest.fixture
def intent_engine():
    from src.brain_v2.engine.intent_engine import IntentEngine
    return IntentEngine()
```

---

## CI Integration

### GitHub Actions (`.github/workflows/phase1-benchmark-gate.yml`)
```yaml
name: Phase 1 Benchmark Gate
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
          cd JAYA_CORE
          pip install -r requirements.txt
      - name: Run benchmark gate
        run: |
          cd JAYA_CORE
          python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate \
            --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
      - name: Run tests
        run: |
          cd JAYA_CORE
          python -m pytest tests/ -v --tb=short
```

---

## Debugging Test Failures

```bash
# Verbose output
python -m pytest tests/test_phase1_jaya_ir.py -v -s

# Stop on first failure
python -m pytest tests/ -x

# Show local variables on failure
python -m pytest tests/ --tb=long

# Run failed tests only
python -m pytest tests/ --lf

# Profile slow tests
python -m pytest tests/ --durations=10
```

---

## Test Data & Fixtures

### Test Data Location
```
tests/
├── fixtures/
│   ├── sample_intents.json
│   ├── sample_jaya_ir.json
│   └── sample_scenegraph.json
└── test_*.py
```

### Loading Fixtures
```python
import json
from pathlib import Path

FIXTURE_DIR = Path(__file__).parent / "fixtures"

def load_fixture(name: str) -> dict:
    with open(FIXTURE_DIR / f"{name}.json") as f:
        return json.load(f)
```

---

## 🔗 Related Docs

- [Benchmark](benchmark.md) — Detailed benchmark methodology
- [Architecture Overview](../02-architecture/overview.md) — Tested components
- [CLI Commands](../../01-getting-started/cli-commands.md) — Test commands reference