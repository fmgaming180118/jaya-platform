# Phase 3: Dynamic Specification Generation

## Objective
Enable the brain to generate **formal specifications** (UI specs, feature specs, task specs, action specs) that the house compiles, validates, and mounts — maintaining strict brain/house boundary.

---

## Scope
- **In scope**: Spec models, brain-side generators, house-side compilers/registries, 10 built-in UI templates
- **Out of scope**: Proactive intelligence (Phase 4), advanced multimodal specs

---

## Deliverables

| # | Deliverable | File | Status |
|---|---|---|---|
| 1 | SceneGraph / WidgetSpec / StyleTokens | `src/os_kernel/ui_spec.py` | ✅ |
| 2 | FeatureManifest / FeatureCompiler | `src/os_kernel/feature_compiler.py` | ✅ |
| 3 | FeatureRegistry | `src/os_kernel/feature_registry.py` | ✅ |
| 4 | JayaBridge (mount/dispatch) | `src/os_kernel/feature_bridge.py` | ✅ |
| 5 | IntentToUIPipeline (Phase 3C) | `src/os_kernel/intent_to_ui.py` | ✅ |
| 6 | 10 Built-in UI Templates | `src/os_kernel/intent_to_ui.py` | ✅ |
| 7 | SpecGenerators (brain-side) | `src/brain_v2/engine/spec_generators.py` | 🔄 Planned |
| 8 | UITemplateRegistry | `src/brain_v2/engine/spec_generators.py` | 🔄 Planned |
| 9 | FeatureSpecGenerator | `src/brain_v2/engine/spec_generators.py` | 🔄 Planned |
| 10 | TaskSpecGenerator | `src/brain_v2/engine/spec_generators.py` | 🔄 Planned |
| 11 | ActionSpecGenerator | `src/brain_v2/engine/spec_generators.py` | 🔄 Planned |
| 12 | SpecGeneratorRouter | `src/brain_v2/engine/spec_generators.py` | 🔄 Planned |
| 13 | Phase 3 integration tests | `tests/test_phase3_spec_generation.py` | 🔄 Planned |

---

## Architecture

### Current (Phase 3C - House-Side Pipeline)
```
Intent → IntentToUIPipeline (os_kernel) → SceneGraph → FeatureCompiler → JayaBridge → Mounted Feature
```

### Target (Phase 3 - Brain Generates, House Compiles)
```
Intent → SpecGeneratorRouter (brain_v2) → SpecBundle {ui_spec?, feature_spec?, task_spec?, action_spec?}
                                              │
                                              ▼ SPECS (JSON)
                                    ┌─────────────────────────┐
                                    │ HOUSE COMPILES & MOUNTS │
                                    │  • FeatureCompiler      │
                                    │  • FeatureRegistry      │
                                    │  • JayaBridge           │
                                    │  • IPC                  │
                                    └─────────────────────────┘
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

## Brain-Side Spec Generators (To Implement)

### UISpecGenerator
```python
class UISpecGenerator(SpecGenerator):
    def __init__(self, template_registry: UITemplateRegistry):
        self.templates = template_registry
    
    def can_handle(self, intent: IntentMatch) -> bool:
        return intent.suggested_ui is not None
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        template = self.templates.get(intent.suggested_ui)
        scene = template.builder(**intent.parameters)
        return SpecBundle(ui_spec=scene, metadata={"template": intent.suggested_ui})
```

### FeatureSpecGenerator
```python
class FeatureSpecGenerator(SpecGenerator):
    def can_handle(self, intent: IntentMatch) -> bool:
        return intent.intent_type in {"run_analysis", "process_data", "sync_knowledge", "train_model"}
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        manifest = FEATURE_MAP[intent.intent_type]
        manifest.config_schema.update(intent.parameters)
        return SpecBundle(feature_spec=manifest)
```

### TaskSpecGenerator
```python
class TaskSpecGenerator(SpecGenerator):
    def can_handle(self, intent: IntentMatch) -> bool:
        return any(t in intent.intent_type for t in ["compute", "calculate", "simulate", "optimize"])
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        # Delegate to TaskPlanner via JayaIR
        plan = self.task_planner.plan(intent_to_jaya_ir(intent))
        return SpecBundle(task_spec=plan)
```

### ActionSpecGenerator
```python
class ActionSpecGenerator(SpecGenerator):
    def can_handle(self, intent: IntentMatch) -> bool:
        return intent.intent_type in {"shutdown", "restart", "status", "config_get", "config_set"}
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        return SpecBundle(action_spec=ACTION_MAP[intent.intent_type](intent.parameters))
```

---

## House-Side Compilation (Already Implemented)

### FeatureCompiler
```python
class FeatureCompiler:
    def compile(self, scene: SceneGraph) -> CompiledFeature:
        # SceneGraph → Python feature code
        ...
    
    def save_feature(self, scene: SceneGraph, dir: str, name: str) -> str:
        # Compile + write to disk
        ...
```

### FeatureRegistry
```python
class FeatureRegistry:
    def discover_features(self) -> List[FeatureManifest]:
        # Scan directory for manifests
        ...
```

### JayaBridge
```python
class JayaBridge:
    def mount_feature(self, manifest: FeatureManifest) -> FeatureInstance:
        # Compile, sandbox, mount
        ...
    
    def dispatch_action(self, feature_id: str, action: str, payload: Dict) -> Any:
        # Route action to feature
        ...
```

---

## Configuration

```python
@dataclass
class AgiConfig:
    # Spec Generation
    spec_generation_enabled: bool = True
    max_spec_size_kb: int = 100
    spec_validation_strict: bool = True
    
    # Feature Compiler
    feature_sandbox_timeout: int = 30
    feature_allowed_imports: List[str] = field(default_factory=lambda: [
        "json", "math", "datetime", "typing", "dataclasses", "enum", "collections"
    ])
    feature_blocked_builtins: List[str] = field(default_factory=lambda: [
        "__import__", "eval", "exec", "open", "compile", "input"
    ])
    
    # JayaBridge
    bridge_mount_timeout: int = 10
    bridge_max_features: int = 50
```

---

## Verification Commands

```bash
# Phase 3C (Current - House-side pipeline)
python -m pytest tests/test_phase3c_intent_to_ui.py -v

# Phase 3 (Future - Brain-side generators)
python -m pytest tests/test_phase3_spec_generation.py -v

# Feature compiler tests
python -m pytest tests/ -k "feature_compiler" -v

# Feature registry tests
python -m pytest tests/ -k "feature_registry" -v

# JayaBridge tests
python -m pytest tests/ -k "bridge" -v
```

---

## Success Criteria

- [ ] SpecGeneratorRouter routes intents to correct generators
- [ ] UISpecGenerator produces valid SceneGraph for all 10 templates
- [ ] FeatureSpecGenerator produces valid FeatureManifest for 4 feature types
- [ ] TaskSpecGenerator integrates with TaskPlanner
- [ ] ActionSpecGenerator produces valid ActionSpec for 5 system actions
- [ ] House compiles all spec types without modification
- [ ] End-to-end: intent → brain specs → house compile → mount → dispatch works
- [ ] Spec validation catches malformed specs before compilation
- [ ] Sandbox prevents unsafe feature code execution

---

## Handoff to Phase 4

**Key Contracts:**
- SpecBundle schema stable
- SceneGraph/FeatureManifest/ExecutionPlan/ActionSpec schemas frozen
- FeatureCompiler/JayaBridge APIs stable
- Brain/house boundary enforced (no direct imports)

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [API Reference](../02-architecture/api-reference.md)
- [Dynamic Spec Generation Features](../03-features/dynamic-spec-gen.md)
- [Spec Generators Research Notes](../05-research-notes/spec-generators.md)
- [Roadmap Overview](../06-roadmap/README.md)