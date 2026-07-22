# CLI Commands Reference — JAYA_OS

Semua command dijalankan dari root `JAYA_OS/`.

---

## 🏗️ Feature Development

### Compile UI Spec → Feature Package
```python
# Di Python REPL atau script
from src.os_kernel.ui_spec import create_window, create_button, SceneGraph
from src.os_kernel.feature_compiler import FeatureCompiler

scene = SceneGraph(
    name="My Feature",
    description="Custom feature",
    root=create_window(
        title="Test",
        width="400px",
        height="300px",
        children=[
            create_button(label="Click Me", on_click="jaya:run_task")
        ]
    )
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

## 🧠 Intent → UI Pipeline (Phase 3C)

### Process Intent End-to-End
```python
from src.brain_v2.engine.intent_engine import IntentEngine
from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.intent_to_ui import IntentToUIPipeline

# Setup
intent_engine = IntentEngine()
bridge = JayaBridge(features_dir="./features")
pipeline = IntentToUIPipeline(bridge, intent_engine)

# Learn from user
intent_engine.learn("show login dialog with username and password")
intent_engine.learn("create a dashboard with metrics")

# Process intent end-to-end
result = pipeline.process_intent("show login dialog")

if result.success:
    print(f"Mounted feature: {result.feature_instance.feature_id}")
    # Dispatch actions
    bridge.dispatch_action(result.feature_instance.feature_id, "submit", {
        "username": "user",
        "password": "pass"
    })
else:
    print(f"Failed: {result.error}")
```

### List Available Templates
```python
pipeline = IntentToUIPipeline(bridge, intent_engine)
templates = pipeline.list_templates()
for t in templates:
    print(f"  - {t['name']}: {t['description']}")
    print(f"    Patterns: {t['patterns'][:3]}...")
```

---

## 🧪 Testing & Benchmarking

### `python -m pytest tests/test_phase3c_intent_to_ui.py -v`
Validasi Phase 3C: Intent → UI Pipeline (SceneGraph → FeatureCompiler → JayaBridge).

### `python -m pytest tests/ -v --tb=short`
Jalankan **semua test** (jika tersedia).

---

## 📦 Utility Scripts

### `python scripts/validate_feature.py --feature <feature_name>`
Validasi feature package (sandbox test).

```bash
python scripts/validate_feature.py --feature my_feature
```

### `python scripts/list_features.py`
List all discovered features.

```bash
python scripts/list_features.py
```

### `python scripts/inspect_feature.py --feature <feature_name>`
Inspect feature manifest and compiled code.

```bash
python scripts/inspect_feature.py --feature my_feature
```

---

## 🔧 Development & Debug

### Verbose Test Output
```bash
python -m pytest tests/test_phase3c_intent_to_ui.py -v -s
```

### Run Single Test Function
```bash
python -m pytest tests/test_phase3c_intent_to_ui.py::test_intent_to_ui_pipeline -v
```

### With Coverage
```bash
pip install pytest-cov
python -m pytest tests/ --cov=src --cov-report=term-missing
```

### Profile Feature Compilation
```bash
python -m cProfile -o compile.prof -c "
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.ui_spec import create_window, create_button, SceneGraph
scene = SceneGraph(name='Test', description='Test', root=create_window(title='Test', children=[create_button(label='Click')]))
compiler = FeatureCompiler()
compiler.save_feature(scene, './features', 'profile_test')
"
python -m pstats compile.prof
```

---

## 📋 Quick Reference Card

| Task | Command |
|---|---|
| Compile UI spec | `python -c "from src.os_kernel.feature_compiler import FeatureCompiler; ..."` |
| Mount feature | `python -c "from src.os_kernel.feature_bridge import JayaBridge; bridge = JayaBridge('./features'); bridge.mount_feature('my_feature')"` |
| Dispatch action | `python -c "bridge.dispatch_action('feature_id', 'action', {'param': 'value'})"` |
| Process intent | `python -c "from src.os_kernel.intent_to_ui import IntentToUIPipeline; pipeline.process_intent('show login dialog')"` |
| List templates | `python -c "pipeline.list_templates()"` |
| Test Phase 3C | `python -m pytest tests/test_phase3c_intent_to_ui.py -v` |
| All tests | `python -m pytest tests/ -v` |
| Validate feature | `python scripts/validate_feature.py --feature my_feature` |
| List features | `python scripts/list_features.py` |
| Inspect feature | `python scripts/inspect_feature.py --feature my_feature` |