# Phase OS-1: Extract os_kernel to Standalone JAYA_OS

## Objective
Extract `os_kernel` from `JAYA_CORE` into standalone `JAYA_OS` project with independent build, test, and release pipeline.

---

## Scope
- **In scope**: Repository structure, build system, CI/CD, documentation, migration from JAYA_CORE
- **Out of scope**: New runtime features (WindowManager, IPC, etc.) — those are OS-2+

---

## Prerequisites
- ✅ JAYA_CORE os_kernel modules stable (FeatureCompiler, FeatureRegistry, JayaBridge, IntentToUIPipeline, UI Spec)
- ✅ Phase 3C complete (Intent → UI Pipeline working)
- ✅ All 211 JAYA_CORE tests passing

---

## Deliverables

| # | Deliverable | File/Location | Status |
|---|---|---|---|
| 1 | Independent JAYA_OS repository structure | `JAYA_OS/` | 🔄 Planned |
| 2 | `pyproject.toml` with dependencies | `JAYA_OS/pyproject.toml` | 🔄 Planned |
| 3 | Build system (wheel, sdist) | `JAYA_OS/` | 🔄 Planned |
| 4 | CI/CD pipeline (tests, lint, type-check) | `.github/workflows/` | 🔄 Planned |
| 5 | Documentation site (mkdocs) | `JAYA_OS/docs/` | 🔄 Planned |
| 6 | Release automation | `.github/workflows/release.yml` | 🔄 Planned |
| 7 | Migration guide | `JAYA_OS/docs/migration.md` | 🔄 Planned |

---

## Technical Implementation

### 1.1 Repository Structure
```
JAYA_OS/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── src/
│   └── jaya_os/
│       ├── __init__.py
│       ├── feature_compiler.py
│       ├── feature_registry.py
│       ├── feature_bridge.py
│       ├── intent_to_ui.py
│       ├── ui_spec.py
│       ├── ipc.py
│       └── window_manager.py
├── tests/
│   ├── test_phase3c_intent_to_ui.py
│   ├── conftest.py
│   └── fixtures/
├── scripts/
│   ├── benchmark_compile.py
│   ├── benchmark_mount.py
│   └── validate_feature.py
├── docs/
├── config/
│   ├── os.yaml
│   └── sandbox.yaml
└── .github/
    └── workflows/
        ├── test.yml
        ├── benchmark.yml
        └── release.yml
```

### 1.2 pyproject.toml
```toml
[project]
name = "jaya-os"
version = "0.1.0"
description = "JAYA OS - The House (Execution Environment for JAYA_CORE)"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.12"
authors = [
    {name = "JAYA Team", email = "jaya@example.com"}
]
classifiers = [
    "Development Status :: 3 - Alpha",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.12",
    "Operating System :: OS Independent",
]
dependencies = [
    "pydantic>=2.0",
    "numpy>=1.24",
    "psutil>=5.9",
    "requests>=2.31",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.1",
    "mypy>=1.5",
    "ruff>=0.1",
    "mkdocs>=1.5",
    "mkdocs-material>=9.0",
]

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.ruff]
line-length = 100
target-version = "py312"
```

### 1.3 Migration from JAYA_CORE

#### Step 1: Copy os_kernel
```bash
# From JAYA_CORE root
cp -r src/os_kernel/* ../JAYA_OS/src/jaya_os/
```

#### Step 2: Update Imports
```python
# Before (in JAYA_CORE)
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.intent_to_ui import IntentToUIPipeline
from src.os_kernel.ui_spec import SceneGraph, create_window

# After (in JAYA_OS)
from jaya_os.feature_compiler import FeatureCompiler
from jaya_os.feature_bridge import JayaBridge
from jaya_os.intent_to_ui import IntentToUIPipeline
from jaya_os.ui_spec import SceneGraph, create_window
```

#### Step 3: Update JAYA_CORE to Use JAYA_OS
```python
# In JAYA_CORE, replace direct imports with:
try:
    from jaya_os.feature_compiler import FeatureCompiler
    from jaya_os.feature_bridge import JayaBridge
    from jaya_os.intent_to_ui import IntentToUIPipeline
    from jaya_os.ui_spec import SceneGraph, create_window
except ImportError:
    # Fallback for development
    from src.os_kernel.feature_compiler import FeatureCompiler
    from src.os_kernel.feature_bridge import JayaBridge
    from src.os_kernel.intent_to_ui import IntentToUIPipeline
    from src.os_kernel.ui_spec import SceneGraph, create_window
```

#### Step 4: Install JAYA_OS in Development
```bash
cd JAYA_OS
pip install -e .[dev]
```

### 1.4 CI/CD Pipeline

#### Test Workflow (`.github/workflows/test.yml`)
```yaml
name: JAYA_OS Tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ${{ matrix.os }}
    strategy:
      matrix:
        os: [ubuntu-latest, windows-latest]
        python-version: ['3.12']
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - name: Install deps
        run: |
          pip install -e .[dev]
      - name: Run tests
        run: |
          python -m pytest tests/ -v --tb=short
      - name: Type check
        run: |
          mypy src/
      - name: Lint
        run: |
          ruff check src/
```

#### Benchmark Workflow (`.github/workflows/benchmark.yml`)
```yaml
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
          pip install -e .[dev]
      - name: Run benchmark gate
        run: |
          python scripts/benchmark_all.py --rounds 50 --gate --fail-on-gate \
            --max-compile-ms 500 --max-mount-ms 200 --max-dispatch-p50-ms 5 \
            --max-render-ms 200 --min-ipc-throughput 10000
      - name: Upload Benchmark Snapshot
        uses: actions/upload-artifact@v4
        with:
          name: jaya-os-benchmark
          path: benchmark_results.json
```

#### Release Workflow (`.github/workflows/release.yml`)
```yaml
name: Release
on:
  push:
    tags:
      - 'v*'
jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install deps
        run: |
          pip install -e .[dev] build twine
      - name: Build
        run: |
          python -m build
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          password: ${{ secrets.PYPI_API_TOKEN }}
```

---

## Verification Checklist

### Functional
- [ ] JAYA_OS builds independently (`pip install -e .`)
- [ ] All Phase 3C tests pass (`python -m pytest tests/test_phase3c_intent_to_ui.py -v`)
- [ ] JAYA_CORE can import `jaya_os` as dependency
- [ ] FeatureCompiler compiles SceneGraph → feature
- [ ] FeatureRegistry discovers features
- [ ] JayaBridge mounts/dispatches/unmounts features
- [ ] IntentToUIPipeline processes natural language → mounted feature

### Quality
- [ ] Type checking passes (`mypy src/`)
- [ ] Linting passes (`ruff check src/`)
- [ ] Test coverage > 80% (`pytest --cov=jaya_os`)
- [ ] Documentation builds (`mkdocs build`)

### CI/CD
- [ ] Test workflow passes on Ubuntu + Windows
- [ ] Benchmark gate passes
- [ ] Release workflow publishes to PyPI

### Documentation
- [ ] README.md complete
- [ ] API reference generated
- [ ] Migration guide written
- [ ] Docs site deploys

---

## Success Criteria
- [ ] JAYA_OS builds independently as a package
- [ ] All Phase 3C tests pass (regression-free)
- [ ] JAYA_CORE can depend on `jaya-os` package
- [ ] CI/CD passes on push (Ubuntu + Windows)
- [ ] Benchmark gate passes
- [ ] Documentation site live

---

## Handoff to OS-2

**Contract**: OS-1 provides stable `jaya_os` package with:
- FeatureCompiler, FeatureRegistry, JayaBridge APIs
- IntentToUIPipeline for Phase 3C compatibility
- UI Spec types (SceneGraph, WidgetSpec, StyleTokens)
- Basic IPC channel infrastructure

**Files for OS-2**:
- `src/jaya_os/window_manager.py` (stub)
- `src/jaya_os/ipc.py` (basic channel)
- `pyproject.toml` with dev dependencies

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [Runtime Features](../03-features/runtime-features.md)
- [Roadmap Overview](../06-roadmap/README.md)