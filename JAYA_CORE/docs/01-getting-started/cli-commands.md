# CLI Commands Reference — JAYA_CORE

Semua command dijalankan dari root `JAYA_CORE/`.

---

## 🧠 Chat & Interaction

### `python scripts/jaya_chat_cli.py`
Interactive chat dengan brain_v2 (Resident Layer).

```bash
python scripts/jaya_chat_cli.py
```

**Commands dalam chat:**
| Command | Fungsi |
|---|---|
| `exit` / `quit` | Keluar |
| `help` | Bantuan |
| `status` | Status engine, memory, resource |
| `benchmark` | Quick benchmark p50/p95 |
| `learn <text>` | Ajarkan intent baru ke IntentEngine |

---

## 🧪 Testing & Benchmarking

### `python -m pytest tests/test_phase1_jaya_ir.py -v`
Validasi pipeline Phase 1: Intent → Lingua Logica → JayaIR → Execution.

### `python -m pytest tests/test_phase3c_intent_to_ui.py -v`
Validasi Phase 3C: Intent → UI Pipeline (SceneGraph → FeatureCompiler → JayaBridge).

### `python -m pytest tests/ -v --tb=short`
Jalankan **semua 211 test** (≈ 3-4 menit).

### `python scripts/benchmark_phase1_ir.py [OPTIONS]`
Benchmark kognitif Phase 1.

```bash
# Smoke test cepat (10 rounds)
python scripts/benchmark_phase1_ir.py --rounds 10

# Gate ketat (CI standard)
python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95

# Snapshot untuk dokumentasi
python scripts/benchmark_phase1_ir.py --rounds 80 --gate --json-out docs/phase1_benchmark_latest.json
```

**Output JSON** (`phase1_benchmark_latest.json`):
```json
{
  "timestamp": "2026-07-21T...",
  "rounds": 80,
  "p50_ms": 0.032,
  "p95_ms": 0.078,
  "hit_rate": 0.97,
  "gate_passed": true
}
```

---

## 📚 Autonomous Learning

### `python scripts/run_autonomous_curriculum.py [OPTIONS]`
Jalankan kurikulum belajar otonom.

```bash
# Topik spesifik
python scripts/run_autonomous_curriculum.py --topics "Linguistik" "Fisika Quantum"

# Mode kontinu (background, Ctrl+C untuk stop)
python scripts/run_autonomous_curriculum.py --continuous

# Dengan interval custom (detik)
python scripts/run_autonomous_curriculum.py --continuous --interval 300
```

**Options:**
| Flag | Default | Deskripsi |
|---|---|---|
| `--topics` | `[]` | Daftar topik (space-separated) |
| `--continuous` | `false` | Loop forever |
| `--interval` | `600` | Detik antar iterasi (continuous) |
| `--max-depth` | `3` | Kedalaman recursive research |

---

## 🔧 Development & Debug

### `python scripts/validate_target_runtime.py`
Validasi target runtime (production readiness check).

```bash
python scripts/validate_target_runtime.py
```

### `python scripts/run_production_evidence_pack.py`
Generate evidence pack untuk production sign-off.

```bash
python scripts/run_production_evidence_pack.py
```

Output: `production_evidence_pack_<timestamp>.json`

---

## 🏗️ Feature Development (Phase 3C)

### Compile UI Spec → Feature Package
```python
# Di Python REPL atau script
from src.os_kernel.ui_spec import create_window, create_button, SceneGraph
from src.os_kernel.feature_compiler import FeatureCompiler

scene = SceneGraph(
    name="My Feature",
    description="Custom feature",
    root=create_window(title="Test", width="400px", height="300px", children=[
        create_button(label="Click Me", on_click="jaya:run_task")
    ])
)

compiler = FeatureCompiler()
output_path = compiler.save_feature(scene, "./features", "my_feature")
print(f"Feature saved to: {output_path}")
```

### Mount Feature via JayaBridge
```python
from src.os_kernel.feature_bridge import JayaBridge

bridge = JayaBridge(features_dir="./features")
feature_id = bridge.mount_feature("my_feature")
print(f"Mounted: {feature_id}")

# Dispatch action
result = bridge.dispatch_action(feature_id, "jaya:run_task", {"param": "value"})
print(result)

# Unmount
bridge.unmount_feature(feature_id)
```

---

## 📦 Utility Scripts

### `python scripts/inspect_jaya_jay.py --path jaya.jay`
Inspect binary identity file (DNA anchor, encrypted weights).

### `python scripts/forge_v17.py`
Forge V17 binary (advanced, untuk evolution pipeline).

---

## 🔍 Debugging Commands

```bash
# Verbose test output
python -m pytest tests/test_phase1_jaya_ir.py -v -s

# Run single test function
python -m pytest tests/test_phase1_jaya_ir.py::test_jaya_ir_parse -v

# With coverage
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=term-missing

# Profile benchmark
python -m cProfile -o bench.prof scripts/benchmark_phase1_ir.py --rounds 10
python -m pstats bench.prof
```

---

## 📋 Quick Reference Card

| Task | Command |
|---|---|
| Chat dengan JAYA | `python scripts/jaya_chat_cli.py` |
| Test Phase 1 | `python -m pytest tests/test_phase1_jaya_ir.py -v` |
| Test Phase 3C | `python -m pytest tests/test_phase3c_intent_to_ui.py -v` |
| All tests | `python -m pytest tests/ -v` |
| Benchmark smoke | `python scripts/benchmark_phase1_ir.py --rounds 10` |
| Benchmark gate | `python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95` |
| Benchmark snapshot | `python scripts/benchmark_phase1_ir.py --rounds 80 --gate --json-out docs/phase1_benchmark_latest.json` |
| Learn topics | `python scripts/run_autonomous_curriculum.py --topics "A" "B"` |
| Continuous learn | `python scripts/run_autonomous_curriculum.py --continuous` |
| Validate runtime | `python scripts/validate_target_runtime.py` |
| Evidence pack | `python scripts/run_production_evidence_pack.py` |