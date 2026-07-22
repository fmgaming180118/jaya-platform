# Testing — JAYA_OS

## Test Suite Overview

JAYA_OS tests are organized by component and integration level.

```bash
# Run all tests
python -m pytest tests/ -v --tb=short

# Run with coverage
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=term-missing
```

---

## Test Categories

### Unit Tests

| Test File | Focus | Tests |
|---|---|---|
| `test_feature_compiler.py` | SceneGraph → Feature compilation | (planned) |
| `test_feature_registry.py` | Feature discovery & versioning | (planned) |
| `test_jaya_bridge.py` | Mount/dispatch/unmount | (planned) |
| `test_window_manager.py` | Window lifecycle | (planned) |
| `test_widget_runtime.py` | Widget rendering & layout | (planned) |
| `test_event_loop.py` | Event handling | (planned) |
| `test_ipc.py` | IPC communication | (planned) |
| `test_sandbox.py` | Sandbox security | (planned) |

### Integration Tests

| Test File | Focus | Tests |
|---|---|---|
| `test_phase3c_intent_to_ui.py` | Intent → UI Pipeline | 1 |
| `test_feature_lifecycle.py` | Compile → Mount → Dispatch → Unmount | (planned) |
| `test_ui_integration.py` | Window + Widget + Event loop | (planned) |
| `test_ipc_integration.py` | Brain ↔ House ↔ Feature | (planned) |

### Security Tests

| Test File | Focus | Tests |
|---|---|---|
| `test_sandbox_import.py` | Import whitelist enforcement | (planned) |
| `test_sandbox_builtin.py` | Blocked builtins | (planned) |
| `test_sandbox_fs.py` | Filesystem proxy | (planned) |
| `test_sandbox_net.py` | Network proxy | (planned) |
| `test_sandbox_resource.py` | CPU/Memory limits | (planned) |

---

## Running Specific Test Groups

```bash
# Phase 3C only
python -m pytest tests/test_phase3c_intent_to_ui.py -v

# Feature compiler tests
python -m pytest tests/ -k "feature_compiler" -v

# Feature registry tests
python -m pytest tests/ -k "feature_registry" -v

# JayaBridge tests
python -m pytest tests/ -k "bridge" -v

# Window manager tests
python -m pytest tests/ -k "window_manager" -v

# Widget runtime tests
python -m pytest tests/ -k "widget_runtime" -v

# IPC tests
python -m pytest tests/ -k "ipc" -v

# Sandbox tests
python -m pytest tests/ -k "sandbox" -v

# Pattern match
python -m pytest tests/ -k "compile or mount" -v
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
# tests/test_my_component.py
import pytest
from src.os_kernel.my_component import MyClass

class TestMyComponent:
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
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.feature_bridge import JayaBridge
from src.brain_v2.engine.intent_engine import IntentEngine

@pytest.fixture
def compiler():
    return FeatureCompiler()

@pytest.fixture
def bridge():
    return JayaBridge("./test_features")

@pytest.fixture
def intent_engine():
    return IntentEngine()

@pytest.fixture
def pipeline(bridge, intent_engine):
    from src.os_kernel.intent_to_ui import IntentToUIPipeline
    return IntentToUIPipeline(bridge, intent_engine)
```

---

## CI Integration

### GitHub Actions
```yaml
# .github/workflows/jaya-os-tests.yml
name: JAYA_OS Tests
on: [push, pull_request]
jobs:
  test:
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
      - name: Run tests
        run: |
          cd JAYA_OS
          python -m pytest tests/ -v --tb=short
```

---

## Debugging Test Failures

```bash
# Verbose output
python -m pytest tests/test_phase3c_intent_to_ui.py -v -s

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
│   ├── sample_scenegraph.json
│   ├── sample_feature_manifest.json
│   └── sample_execution_plan.json
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