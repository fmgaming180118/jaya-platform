# Architecture Overview — JAYA_OS

## High-Level: House/Body Layer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           JAYA OS (The House)                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  os_kernel (Home Layer) — Body, Sensors, Actuators                    │  │
│  │  • Device runtime, windowing, feature mounting                        │  │
│  │  • Hardware abstraction, resource monitoring                          │  │
│  │  • Policy enforcement, sandbox execution                              │  │
│  │  • FeatureCompiler, FeatureRegistry, JayaBridge, IPC                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Specs (JSON)
                              │
┌─────────────────────────────────────────────────────────────────────────────┐
│                    JAYA_CORE (The Brain)                                    │
│  • IntentEngine → LinguaLogica → JayaIR → IronEngine                       │
│  • SpecGenerators: UI, Feature, Task, Action                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Principle**: The brain (`JAYA_CORE`) **reasons and emits specifications**; the house (`JAYA_OS`) **validates, compiles, and executes**. The brain never directly controls hardware.

---

## Spec Pipeline (Brain → House)

```
Intent (Natural Language)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. INTENT CAPTURE — JAYA_CORE/IntentEngine                                  │
│    • TF-IDF + n-gram matching                                               │
│    • Online learning (learn/predict)                                        │
│    • Output: IntentMatch {intent_type, confidence, suggested_ui, params}    │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. SPEC GENERATION — JAYA_CORE/SpecGenerators                               │
│    • UISpecGenerator → SceneGraph (WidgetTree + StyleTokens)               │
│    • FeatureSpecGenerator → FeatureManifest                                │
│    • TaskSpecGenerator → ExecutionPlan                                     │
│    • ActionSpecGenerator → ActionSpec                                      │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. HOUSE COMPILES & MOUNTS (JAYA_OS)                                        │
│    • FeatureCompiler: SceneGraph → Runnable Python feature                  │
│    • FeatureRegistry: Versioned discovery & mounting                        │
│    • JayaBridge: Sandbox mount, action dispatch, state management           │
│    • WindowManager: Window lifecycle, z-order, focus                        │
│    • Widget Runtime: Render WidgetSpec, handle events                       │
│    • IPC Bridge: Structured Brain ↔ House communication                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Spec Types

### 1. UI Spec — SceneGraph
```python
@dataclass
class SceneGraph:
    name: str
    description: str
    root: WidgetSpec
    version: str = "1.0"
    metadata: Dict = field(default_factory=dict)

@dataclass
class WidgetSpec:
    id: str
    type: WidgetType          # WINDOW, PANEL, BUTTON, LABEL, TEXT_INPUT, etc.
    props: Dict = field(default_factory=dict)
    children: List['WidgetSpec'] = field(default_factory=list)
    layout: Optional[LayoutSpec] = None
    style: Optional[StyleTokens] = None
    bindings: List[Binding] = field(default_factory=list)
    events: List[EventHandler] = field(default_factory=list)
```

**Widget Types:**
| Type | Props | Events |
|---|---|---|
| `WINDOW` | title, width, height, resizable | on_close, on_resize |
| `PANEL` | layout (FLEX_ROW/FLEX_COL/GRID) | - |
| `BUTTON` | label, variant (primary/secondary/danger) | on_click |
| `LABEL` | text, wrap | - |
| `TEXT_INPUT` | placeholder, type (text/password/number) | on_change, on_submit |
| `SELECT` | options[], multiple | on_change |
| `LIST` | items[], selectable | on_select |
| `PROGRESS` | value, max, indeterminate | - |
| `CHART` | type (line/bar/pie), data[] | - |

### 2. Feature Spec — FeatureManifest
```python
@dataclass
class FeatureManifest:
    name: str
    version: str
    entry_point: str              # "module:function"
    permissions: List[str]        # ["fs_read", "net_http", "ui_render", ...]
    dependencies: List[str]       # Other feature names
    ui_spec: Optional[SceneGraph] = None
    config_schema: Dict = field(default_factory=dict)
```

**Permissions:**
| Permission | Scope |
|---|---|
| `fs_read` | Read files in allowed directories |
| `fs_write` | Write files in allowed directories |
| `net_http` | Outbound HTTP requests (vetted domains) |
| `ui_render` | Mount UI via JayaBridge |
| `ipc_send` | Send IPC messages |
| `memory_read` | Read shared memory |
| `memory_write` | Write shared memory |

### 3. Task Spec — ExecutionPlan
```python
@dataclass
class ExecutionPlan:
    steps: List[ExecutionStep]
    dependencies: Dict[str, List[str]]
    parallel_groups: List[List[str]]
    estimated_latency_ms: float
    required_resources: Dict[str, float]
    priority: int = 0
    deadline: Optional[datetime] = None
```

### 4. Action Spec — ActionSpec
```python
@dataclass
class ActionSpec:
    channel: str                  # IPC channel
    action: str                   # Action name
    payload: Dict                 # Parameters
```

---

## Built-in UI Templates (10)

| Template | Intent Patterns | Parameters | Output |
|---|---|---|---|
| `login_dialog` | "show login", "sign in" | title, show_remember, fields[] | Username/password form |
| `dashboard` | "create dashboard", "show metrics" | metrics[], charts[], refresh_interval | Metric cards + charts |
| `settings_dialog` | "open settings", "preferences" | categories[], show_reset | Categorized settings panels |
| `file_explorer` | "show files", "browse files" | root_path, show_hidden, multi_select | Tree view + file ops |
| `chat_interface` | "chat with", "open chat" | history[], placeholder, send_action | Message list + input |
| `confirm_dialog` | "confirm", "are you sure" | message, title, danger, actions[] | Yes/No/Cancel modal |
| `progress_dialog` | "show progress", "loading" | title, max_value, cancellable, show_eta | Progress bar + cancel |
| `list_view` | "list", "show list" | items[], columns[], multi_select, actions[] | Selectable list/table |
| `form` | "create form", "input form" | fields[], submit_action, validation | Dynamic form |
| `generic_dialog` | "dialog", "popup", "modal" | title, content_widgets[], actions[] | Flexible container |

---

## Security Model

| Layer | Protection |
|---|---|
| **Spec Validation** | SceneGraph/FeatureManifest schema validation before compile |
| **Sandbox Compilation** | FeatureCompiler runs in restricted Python (blocked builtins, import whitelist) |
| **Permission System** | FeatureManifest declares required permissions; JayaBridge enforces |
| **Mount Isolation** | Each feature runs in separate namespace; no direct memory access |
| **Action Validation** | JayaBridge validates action payloads against config_schema |
| **Rollback** | Failed mounts auto-cleanup; feature state preserved for debugging |

---

## Resource-Aware Operation

JAYA_OS integrates with JAYA_CORE's `ResourceMonitor`:

```python
from src.brain_v2.organism.resource_monitor import get_readings

readings = get_readings()  # {'cpu_pct': 25.3, 'mem_pct': 45.1, 'battery_pct': 87.0}

# Auto-adjust feature behavior
if readings['cpu_pct'] > 85:
    # Reduce feature complexity, disable animations
    pass
```

---

## Module Map (Key Files)

```
JAYA_OS/src/
├── os_kernel/                   # HOME LAYER (BODY)
│   ├── feature_compiler.py      # SceneGraph → Feature package
│   ├── feature_registry.py      # Versioned feature mounting
│   ├── feature_bridge.py        # JayaBridge (mount/dispatch)
│   ├── intent_to_ui.py          # Intent → UI Pipeline (Phase 3C)
│   ├── ui_spec.py               # SceneGraph, WidgetSpec, templates
│   ├── ipc.py                   # Inter-process communication
│   └── window_manager.py        # Window management
│
└── jaya_language/               # SHARED LANGUAGE LAYER
    └── (contracts, IR definitions)
```

---

## 🔗 Lanjutkan ke

- [API Reference](api-reference.md) — Detailed interfaces & dataclasses
- [Components](components.md) — Module-by-module breakdown
- [Runtime Features](../03-features/runtime-features.md) — FeatureCompiler, Registry, Bridge
- [UI Runtime](../03-features/ui-runtime.md) — WindowManager, Widget Runtime
- [IPC Bridge](../03-features/ipc-bridge.md) — Inter-process communication
- [Sandbox Security](../03-features/sandbox-security.md) — Capability-based permissions
- [Roadmap OS-1 to OS-5](../06-roadmap/README.md)