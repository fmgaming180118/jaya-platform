# Runtime Features — JAYA_OS

## Overview

JAYA_OS provides the **runtime infrastructure** for executing specifications emitted by JAYA_CORE. The core runtime features are:

1. **FeatureCompiler** — Compiles SceneGraph (UI specs) into runnable Python feature packages
2. **FeatureRegistry** — Discovers, versions, and manages feature packages
3. **JayaBridge** — Mounts features in sandbox, dispatches actions, manages state

---

## 1. FeatureCompiler

### Purpose
Transform declarative `SceneGraph` specifications into executable Python feature packages that can be safely mounted and run.

### Input: SceneGraph
```python
@dataclass
class SceneGraph:
    name: str
    description: str
    root: WidgetSpec
    version: str = "1.0"
    metadata: Dict = field(default_factory=dict)
```

### Output: CompiledFeature
```python
@dataclass
class CompiledFeature:
    name: str
    version: str
    entry_point: str              # "module:function"
    source_code: str              # Python source
    manifest: FeatureManifest
    sandbox_policy: SandboxPolicy
```

### Compilation Process
```
SceneGraph
    │
    ▼
Validate SceneGraph (schema, widget types, bindings)
    │
    ▼
Generate Python module:
  - Imports (whitelisted only)
  - Widget class definitions
  - Event handlers
  - State management
  - Entry point function
    │
    ▼
Write to disk: ./features/{name}/
  - __init__.py (entry point)
  - manifest.json (FeatureManifest)
  - sandbox_policy.json
  - widget_modules/
```

### Security: Sandbox Policy
```python
@dataclass
class SandboxPolicy:
    allowed_imports: List[str] = field(default_factory=lambda: [
        "json", "math", "datetime", "typing", "dataclasses", "enum", "collections"
    ])
    blocked_builtins: List[str] = field(default_factory=lambda: [
        "__import__", "eval", "exec", "open", "compile", "input"
    ])
    cpu_limit_percent: int = 50
    memory_limit_mb: int = 200
    network_allowed: bool = False
    filesystem_read: List[str] = field(default_factory=lambda: ["./features", "./data"])
    filesystem_write: List[str] = field(default_factory=lambda: ["./features/tmp"])
```

### API
```python
class FeatureCompiler:
    def __init__(self, sandbox_timeout=30, allowed_imports=None, blocked_builtins=None):
        ...

    def compile_feature(self, scene: SceneGraph) -> CompiledFeature:
        """Compile SceneGraph → runnable Python feature code."""
        ...

    def save_feature(self, scene: SceneGraph, features_dir: str, feature_name: str) -> str:
        """Compile & save feature package to disk. Returns path."""
        ...

    def validate_scene(self, scene: SceneGraph) -> ValidationResult:
        """Validate SceneGraph before compilation."""
        ...
```

---

## 2. FeatureRegistry

### Purpose
Manages the lifecycle of feature packages: discovery, versioning, dependency resolution, and registration.

### FeatureManifest
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
    metadata: Dict = field(default_factory=dict)
    signature: Optional[bytes] = None  # PQC signature for verified features
```

### API
```python
class FeatureRegistry:
    def __init__(self, features_dir: str):
        self.features_dir = features_dir

    def discover_features(self) -> List[FeatureManifest]:
        """Scan directory for feature manifests."""
        ...

    def get_manifest(self, feature_id: str) -> Optional[FeatureManifest]:
        """Load manifest by feature ID."""
        ...

    def register(self, manifest: FeatureManifest) -> bool:
        """Register new feature manifest (write to index)."""
        ...

    def unregister(self, feature_name: str) -> bool:
        """Unregister feature."""
        ...

    def resolve_dependencies(self, feature_name: str) -> List[str]:
        """Return ordered list of dependencies (topological sort)."""
        ...
```

### Discovery
Features are stored as directories:
```
features/
├── login_dialog/
│   ├── __init__.py
│   ├── manifest.json
│   ├── sandbox_policy.json
│   └── widget_modules/
├── dashboard/
│   └── ...
└── index.json          # Registry index (optional)
```

---

## 3. JayaBridge

### Purpose
Runtime bridge that mounts compiled features in sandbox, dispatches actions, and manages feature state.

### FeatureInstance
```python
@dataclass
class FeatureInstance:
    feature_id: str
    manifest: FeatureManifest
    module: ModuleType          # Loaded Python module
    state: Dict = field(default_factory=dict)
    mounted_at: datetime
    sandbox: SandboxContext
```

### API
```python
class JayaBridge:
    def __init__(self, features_dir: str = "./features",
                 mount_timeout: int = 10, max_features: int = 50):
        self.features_dir = features_dir
        self.registry = FeatureRegistry(features_dir)
        self.mounted: Dict[str, FeatureInstance] = {}

    def mount_feature(self, feature_name: str, config: Dict = None) -> str:
        """Compile (if needed), sandbox, and mount feature. Returns feature_id."""
        ...

    def unmount_feature(self, feature_id: str) -> bool:
        """Unmount and cleanup feature."""
        ...

    def dispatch_action(self, feature_id: str, action: str, payload: Dict) -> Any:
        """Dispatch action to mounted feature (button click, form submit, etc)."""
        ...

    def get_feature_state(self, feature_id: str) -> Optional[Dict]:
        """Get current state of mounted feature."""
        ...

    def list_mounted_features(self) -> List[Dict]:
        """List all currently mounted features."""
        ...
```

### Action Dispatch Flow
```
User clicks button in UI
        │
        ▼
Widget event handler → JayaBridge.dispatch_action(feature_id, "submit", {"username": "user"})
        │
        ▼
JayaBridge looks up feature_id → gets FeatureInstance
        │
        ▼
Calls feature_module.handle_action(action, payload, state)
        │
        ▼
Feature executes logic, updates state, returns result
        │
        ▼
Result returned to UI via IPC/callback
```

---

## Integration with JAYA_CORE

### IntentToUIPipeline (Phase 3C)
```python
from src.os_kernel.intent_to_ui import IntentToUIPipeline
from src.brain_v2.engine.intent_engine import IntentEngine
from src.os_kernel.feature_bridge import JayaBridge

bridge = JayaBridge("./features")
intent_engine = IntentEngine()
pipeline = IntentToUIPipeline(bridge, intent_engine)

# End-to-end: natural language → mounted feature
result = pipeline.process_intent("show login dialog")
```

---

## Testing

```bash
# Feature Compiler tests
python -m pytest tests/ -k "feature_compiler" -v

# Feature Registry tests
python -m pytest tests/ -k "feature_registry" -v

# JayaBridge tests
python -m pytest tests/ -k "bridge" -v

# Phase 3C integration test
python -m pytest tests/test_phase3c_intent_to_ui.py -v
```

---

## 🔗 Related Docs

- [UI Runtime](../03-features/ui-runtime.md) — WindowManager, Widget Runtime
- [IPC Bridge](../03-features/ipc-bridge.md) — Inter-process communication
- [Sandbox Security](../03-features/sandbox-security.md) — Capability-based permissions
- [Architecture Overview](../02-architecture/overview.md)
- [API Reference](../02-architecture/api-reference.md)