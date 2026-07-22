# Components — JAYA_OS Module Breakdown

## Os_Kernel (Home Layer) — The Body

### `src/os_kernel/` — Feature & UI Runtime

| Module | Purpose | Key Classes |
|---|---|---|
| `feature_compiler.py` | SceneGraph → runnable Python feature | `FeatureCompiler`, `CompiledFeature` |
| `feature_registry.py` | Versioned feature discovery & mounting | `FeatureRegistry`, `FeatureManifest` |
| `feature_bridge.py` | JayaBridge — mount/dispatch/unmount | `JayaBridge` |
| `intent_to_ui.py` | Intent → UI Pipeline (Phase 3C) | `IntentToUIPipeline`, `UITemplate`, `PipelineResult` |
| `ui_spec.py` | SceneGraph, WidgetSpec, StyleTokens, factories | `SceneGraph`, `WidgetSpec`, `WidgetType`, `LayoutType`, `StyleTokens`, `create_window`, `create_button`, ... |
| `ipc.py` | Inter-process communication | `IPCChannel`, `register_ipc_handler`, `dispatch_ipc` |
| `window_manager.py` | Window lifecycle management | `WindowManager` |

### `src/os_kernel/intent_to_ui.py` — Built-in UI Templates (10)

| Template | Description | Parameters |
|---|---|---|
| `login_dialog` | Username/password form | `title`, `show_remember`, `fields[]` |
| `dashboard` | Metric cards + charts | `metrics`, `charts`, `refresh_interval` |
| `settings_dialog` | Categorized settings panels | `categories`, `show_reset` |
| `file_explorer` | Tree view + file ops | `root_path`, `show_hidden`, `multi_select` |
| `chat_interface` | Message list + input | `history`, `placeholder`, `send_action` |
| `confirm_dialog` | Yes/No/Cancel modal | `message`, `title`, `danger`, `actions[]` |
| `progress_dialog` | Progress bar + cancel | `title`, `max_value`, `cancellable`, `show_eta` |
| `list_view` | Selectable item list | `items`, `columns`, `multi_select`, `actions[]` |
| `form` | Dynamic form from schema | `fields`, `submit_action`, `validation` |
| `generic_dialog` | Flexible content window | `title`, `content_widgets`, `actions[]` |

---

## Language Layer (Shared) — `src/jaya_language/`

| Module | Purpose |
|---|---|
| `ui_spec.py` | **Moved to os_kernel** — UI spec types shared via import |
| `contracts.py` | Cross-layer contracts: `IntentMatch`, `PipelineResult`, `JayaActions` |
| `ir_definitions.py` | JayaIR schema definitions (OpCode, Operand) |

> **Note**: `ui_spec.py` physically lives in `os_kernel/` but is imported by both layers as the shared UI specification language.

---

## Integration with JAYA_CORE (Brain)

### ResourceMonitor (from JAYA_CORE)
```python
from src.brain_v2.organism.resource_monitor import ResourceMonitor, get_readings

# JAYA_OS uses ResourceMonitor for adaptive behavior
readings = get_readings()  # {'cpu_pct': 25.3, 'mem_pct': 45.1, 'battery_pct': 87.0}
```

### IntentEngine (from JAYA_CORE)
```python
from src.brain_v2.engine.intent_engine import IntentEngine

# IntentToUIPipeline uses IntentEngine for matching
pipeline = IntentToUIPipeline(bridge, intent_engine)
```

---

## Test Coverage

| Test File | Area | Tests |
|---|---|---|
| `test_phase3c_intent_to_ui.py` | Intent→UI pipeline | 1 |
| `test_feature_compiler.py` | Feature compilation | (planned) |
| `test_feature_registry.py` | Feature discovery | (planned) |
| `test_jaya_bridge.py` | Mount/dispatch | (planned) |
| `test_window_manager.py` | Window lifecycle | (planned) |
| `test_ipc.py` | IPC communication | (planned) |

---

## 🔗 Lanjutkan ke

- [Runtime Features](../03-features/runtime-features.md) — FeatureCompiler, Registry, Bridge
- [UI Runtime](../03-features/ui-runtime.md) — WindowManager, Widget Runtime
- [IPC Bridge](../03-features/ipc-bridge.md) — Inter-process communication
- [Sandbox Security](../03-features/sandbox-security.md) — Capability-based permissions
- [Roadmap OS-1 to OS-5](../06-roadmap/README.md)