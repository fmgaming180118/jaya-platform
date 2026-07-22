# Dynamic Specification Generation — JAYA_CORE

## Overview

The brain generates **specifications** (not executable code) for the house to compile, validate, and mount. This maintains the brain/house boundary while enabling dynamic UI/feature creation.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ BRAIN (brain_v2) — Generates Specs                                          │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ IntentToUIPipeline (os_kernel/intent_to_ui.py) — Phase 3C             │  │
│  │  • match_intent(user_input) → IntentMatch[]                           │  │
│  │  • extract_parameters(input, template) → Dict                         │  │
│  │  • build_scene(template, params) → SceneGraph                         │  │
│  │  • compile_and_mount(scene, name) → FeatureInstance                   │  │
│  │  • process_intent(input) → PipelineResult (end-to-end)                │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ SpecGenerators (brain_v2/engine/spec_generators.py) — Future Phase 3  │  │
│  │  • generate_ui_spec(intent) → SceneGraph                              │  │
│  │  • generate_feature_spec(intent) → FeatureManifest                    │  │
│  │  • generate_task_spec(intent) → ExecutionPlan                         │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ SPECS (JSON-serializable)
┌─────────────────────────────────────────────────────────────────────────────┐
│ HOUSE (os_kernel) — Compiles & Mounts                                       │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ FeatureCompiler (feature_compiler.py)                                 │  │
│  │  • compile(scene: SceneGraph) → CompiledFeature                       │  │
│  │  • save_feature(scene, dir, name) → path                              │  │
│  │  • validate_scene(scene) → ValidationResult                           │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ FeatureRegistry (feature_registry.py)                                 │  │
│  │  • discover_features() → FeatureManifest[]                            │  │
│  │  • get_manifest(name) → FeatureManifest                               │  │
│  │  • register(manifest) / unregister(name)                              │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ JayaBridge (feature_bridge.py)                                        │  │
│  │  • mount_feature(manifest) → FeatureInstance                          │  │
│  │  • dispatch_action(feature_id, action, payload) → result              │  │
│  │  • unmount_feature(feature_id) → bool                                 │  │
│  │  • get_feature_state(feature_id) → Dict                               │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Spec Types

### 1. UI Spec — SceneGraph

**Purpose:** Describe a user interface declaratively.

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

**StyleTokens (Design System):**
```python
@dataclass
class StyleTokens:
    color_primary: str = "#0066CC"
    color_background: str = "#FFFFFF"
    color_surface: str = "#F5F5F5"
    color_text: str = "#1A1A1A"
    color_text_secondary: str = "#666666"
    border_radius: str = "8px"
    spacing_unit: str = "8px"
    font_family: str = "Inter, system-ui, sans-serif"
    font_size_base: str = "14px"
    shadow_elevation_1: str = "0 1px 3px rgba(0,0,0,0.1)"
    shadow_elevation_2: str = "0 4px 6px rgba(0,0,0,0.1)"
```

---

### 2. Feature Spec — FeatureManifest

**Purpose:** Describe a runnable capability package.

```python
@dataclass
class FeatureManifest:
    name: str
    version: str
    entry_point: str              # "module:function"
    permissions: List[str]        # ["fs_read", "net_http", "ui_render"]
    dependencies: List[str]       # Other feature names
    ui_spec: Optional[SceneGraph] = None
    config_schema: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)
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

---

### 3. Task Spec — ExecutionPlan

**Purpose:** Describe a computational task for the house to schedule.

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

---

## Built-in UI Templates (10)

| Template | Intent Patterns | Parameters | Output |
|---|---|---|---|
| `login_dialog` | "show login", "sign in", "login dialog" | `title`, `show_remember`, `fields[]` | Username/password form |
| `dashboard` | "create dashboard", "show metrics", "dashboard" | `metrics[]`, `charts[]`, `refresh_interval` | Metric cards + charts |
| `settings_dialog` | "open settings", "preferences", "settings dialog" | `categories[]`, `show_reset` | Categorized settings panels |
| `file_explorer` | "show files", "file explorer", "browse files" | `root_path`, `show_hidden`, `multi_select` | Tree view + file ops |
| `chat_interface` | "chat with", "open chat", "conversation" | `history[]`, `placeholder`, `send_action` | Message list + input |
| `confirm_dialog` | "confirm", "are you sure", "confirm delete" | `message`, `title`, `danger`, `actions[]` | Yes/No/Cancel modal |
| `progress_dialog` | "show progress", "progress bar", "loading" | `title`, `max_value`, `cancellable`, `show_eta` | Progress bar + cancel |
| `list_view` | "list", "show list", "table view" | `items[]`, `columns[]`, `multi_select`, `actions[]` | Selectable list/table |
| `form` | "create form", "form for", "input form" | `fields[]`, `submit_action`, `validation` | Dynamic form |
| `generic_dialog` | "dialog", "popup", "modal" | `title`, `content_widgets[]`, `actions[]` | Flexible container |

---

## Template Builders

Each template has a builder function in `intent_to_ui.py`:

```python
def build_login_dialog(title: str = "Login", 
                       show_remember: bool = True,
                       fields: List[str] = None) -> SceneGraph:
    """Build login dialog SceneGraph."""
    fields = fields or ["username", "password"]
    children = []
    for field in fields:
        children.append(create_label(field.capitalize()))
        children.append(create_text_input(
            placeholder=f"Enter {field}",
            type="password" if field == "password" else "text",
            id=f"input_{field}"
        ))
    if show_remember:
        children.append(create_checkbox("Remember me", id="remember"))
    children.append(create_button("Sign In", on_click="submit_login", variant="primary"))
    
    return SceneGraph(
        name="Login Dialog",
        description="Username/password authentication dialog",
        root=create_window(
            title=title,
            width="400px",
            height="350px",
            children=[create_panel(layout=LayoutType.FLEX_COL, children=children)]
        )
    )
```

---

## End-to-End Example

```python
from src.brain_v2.engine.intent_engine import IntentEngine
from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.intent_to_ui import IntentToUIPipeline

# Setup
intent_engine = IntentEngine()
bridge = JayaBridge("./features")
pipeline = IntentToUIPipeline(bridge, intent_engine)

# Teach new patterns
intent_engine.learn("show login dialog with email and password")
intent_engine.learn("create a dashboard with CPU and memory charts")

# Process intent
result = pipeline.process_intent("show login dialog")

if result.success:
    feature = result.feature_instance
    print(f"Mounted: {feature.feature_id}")
    
    # Handle user interaction
    bridge.dispatch_action(feature.feature_id, "submit_login", {
        "username": "admin",
        "password": "secret123"
    })
else:
    print(f"Failed: {result.error}")
```

---

## Security Model

| Layer | Protection |
|---|---|
| **Spec Validation** | SceneGraph schema validation before compile |
| **Sandbox Compilation** | FeatureCompiler runs in restricted Python (blocked builtins, import whitelist) |
| **Permission System** | FeatureManifest declares required permissions; JayaBridge enforces |
| **Mount Isolation** | Each feature runs in separate namespace; no direct memory access |
| **Action Validation** | JayaBridge validates action payloads against config_schema |
| **Rollback** | Failed mounts auto-cleanup; feature state preserved for debugging |

---

## Testing

```bash
# Phase 3C: Intent → UI Pipeline
python -m pytest tests/test_phase3c_intent_to_ui.py -v

# Feature Compiler
python -m pytest tests/ -k "feature_compiler" -v

# Feature Registry
python -m pytest tests/ -k "feature_registry" -v

# JayaBridge
python -m pytest tests/ -k "bridge" -v
```

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md) — Spec generation in pipeline
- [API Reference](../02-architecture/api-reference.md) — SceneGraph, FeatureManifest, JayaBridge interfaces
- [Cognitive Features](cognitive-features.md) — Intent understanding that feeds spec gen
- [Roadmap Phase 3](../06-roadmap/phase-3-dynamic-specs.md) — Implementation plan