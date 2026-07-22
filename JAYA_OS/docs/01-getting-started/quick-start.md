# Quick Start — JAYA_OS (5 Menit)

## 1. Jalankan Feature Compiler & Bridge

```bash
cd JAYA_OS
python -c "
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.ui_spec import create_window, create_button, SceneGraph

# Create a simple UI spec
scene = SceneGraph(
    name='Test Window',
    description='Quick start test',
    root=create_window(
        title='JAYA_OS Test',
        width='400px',
        height='300px',
        children=[
            create_button(label='Click Me', on_click='jaya:test_action')
        ]
    )
)

# Compile to feature
compiler = FeatureCompiler()
output_path = compiler.save_feature(scene, './features', 'test_window')
print(f'Feature saved to: {output_path}')

# Mount via JayaBridge
bridge = JayaBridge(features_dir='./features')
feature_id = bridge.mount_feature('test_window')
print(f'Mounted feature: {feature_id}')

# Dispatch action
result = bridge.dispatch_action(feature_id, 'jaya:test_action', {'test': 'data'})
print(f'Action result: {result}')

# Unmount
bridge.unmount_feature(feature_id)
print('Unmounted successfully')
"
```

---

## 2. Jalankan Intent → UI Pipeline (Phase 3C)

```bash
python -c "
from src.brain_v2.engine.intent_engine import IntentEngine
from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.intent_to_ui import IntentToUIPipeline

# Setup
intent_engine = IntentEngine()
bridge = JayaBridge(features_dir='./features')
pipeline = IntentToUIPipeline(bridge, intent_engine)

# Teach some patterns
intent_engine.learn('show login dialog with username and password')
intent_engine.learn('create a dashboard with metrics')

# Process intent end-to-end
result = pipeline.process_intent('show login dialog')

if result.success:
    print(f'Mounted feature: {result.feature_instance.feature_id}')
    # Dispatch action
    bridge.dispatch_action(result.feature_instance.feature_id, 'submit_login', {
        'username': 'admin',
        'password': 'secret123'
    })
else:
    print(f'Failed: {result.error}')
"
```

---

## 3. Jalankan Test Suite

```bash
# Phase 3C test
python -m pytest tests/test_phase3c_intent_to_ui.py -v

# All tests (if available)
python -m pytest tests/ -v --tb=short
```

---

## 4. Generate Benchmark Snapshot

```bash
# Note: Benchmark script is in JAYA_CORE
cd ../JAYA_CORE
python scripts/benchmark_phase1_ir.py --rounds 80 --gate --json-out ../JAYA_OS/docs/phase1_benchmark_latest.json
```

---

## 🎯 Checklist "Done"

- [ ] Feature compiler creates valid Python feature package
- [ ] JayaBridge mounts feature in sandbox
- [ ] Action dispatch works (button click, form submit)
- [ ] Intent → UI pipeline processes natural language
- [ ] Test suite passes

---

## 🔗 Lanjutkan ke

- [Installation](installation.md) — Detail setup & troubleshooting
- [Configuration](configuration.md) — Env vars & config files
- [CLI Commands](cli-commands.md) — Semua script CLI
- [Architecture Overview](../02-architecture/overview.md) — Arsitektur lengkap