# API Reference — JAYA_OS

## Core Dataclasses

### SceneGraph (UI Spec)
```python
@dataclass
class SceneGraph:
    name: str
    description: str
    root: WidgetSpec
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)
```

### WidgetSpec
```python
@dataclass
class WidgetSpec:
    id: str
    type: WidgetType              # WINDOW, PANEL, BUTTON, LABEL, TEXT_INPUT, etc.
    props: Dict[str, Any] = field(default_factory=dict)
    children: List['WidgetSpec'] = field(default_factory=list)
    layout: Optional[LayoutSpec] = None
    style: Optional[StyleTokens] = None
    bindings: List[Binding] = field(default_factory=list)
    events: List[EventHandler] = field(default_factory=list)
```

### FeatureManifest
```python
@dataclass
class FeatureManifest:
    name: str
    version: str
    entry_point: str              # "module:function"
    permissions: List[str]        # Required permissions
    dependencies: List[str]       # Other features
    ui_spec: Optional[SceneGraph] = None
    config_schema: Dict[str, Any] = field(default_factory=dict)
```

### ExecutionPlan (Task Spec)
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

### ActionSpec
```python
@dataclass
class ActionSpec:
    channel: str                  # IPC channel
    action: str                   # Action name
    payload: Dict                 # Parameters
```

---

## Core Interfaces

### FeatureCompiler — `src/os_kernel/feature_compiler.py`
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

    def validate_feature(self, feature_path: str) -> ValidationResult:
        """Validate feature package (sandbox test)."""
        ...
```

### FeatureRegistry — `src/os_kernel/feature_registry.py`
```python
class FeatureRegistry:
    def __init__(self, features_dir: str):
        self.features_dir = features_dir

    def discover_features(self) -> List[FeatureManifest]:
        """Scan directory for feature manifests."""
        ...

    def get_manifest(self, feature_id: str) -> Optional[FeatureManifest]:
        """Load manifest by ID."""
        ...

    def register(self, manifest: FeatureManifest) -> bool:
        """Register new feature manifest."""
        ...
```

### JayaBridge — `src/os_kernel/feature_bridge.py`
```python
class JayaBridge:
    def __init__(self, features_dir: str = "./features"):
        self.features_dir = features_dir
        self.registry = FeatureRegistry(features_dir)
        self.mounted: Dict[str, FeatureInstance] = {}

    def mount_feature(self, feature_name: str, config: Dict = None) -> str:
        """Compile, sandbox, and mount feature. Returns feature_id."""
        ...

    def unmount_feature(self, feature_id: str) -> bool:
        """Unmount and cleanup feature."""
        ...

    def dispatch_action(self, feature_id: str, action: str, payload: Dict) -> Any:
        """Dispatch action to mounted feature."""
        ...

    def get_feature_state(self, feature_id: str) -> Optional[Dict]:
        """Get feature's current state."""
        ...

    def list_mounted_features(self) -> List[Dict]:
        """List all currently mounted features."""
        ...
```

### IntentToUIPipeline — `src/os_kernel/intent_to_ui.py`
```python
class IntentToUIPipeline:
    def __init__(self, bridge: JayaBridge, intent_engine: IntentEngine):
        self.bridge = bridge
        self.intent_engine = intent_engine
        self.templates: Dict[str, UITemplate] = {}
        self._register_builtin_templates()

    def match_intent(self, user_input: str) -> List[IntentMatch]:
        """Match user input to intent templates."""
        ...

    def extract_parameters(self, user_input: str, template_name: str) -> Dict[str, Any]:
        """Extract parameters for specific template."""
        ...

    def build_scene(self, template_name: str, params: Dict[str, Any]) -> SceneGraph:
        """Build SceneGraph from template + parameters."""
        ...

    def compile_and_mount(self, scene: SceneGraph, feature_name: str) -> FeatureInstance:
        """Full pipeline: SceneGraph → compile → mount via JayaBridge."""
        ...

    def process_intent(self, user_input: str) -> PipelineResult:
        """End-to-end: input → match → extract → build → compile → mount."""
        ...

    def list_templates(self) -> List[Dict[str, Any]]:
        """List available UI templates."""
        ...
```

### UITemplate
```python
@dataclass
class UITemplate:
    name: str
    description: str
    patterns: List[str]              # Regex patterns for intent matching
    builder: Callable[..., SceneGraph]  # Function(params) → SceneGraph
    required_params: List[str]
    optional_params: Dict[str, Any] = field(default_factory=dict)
```

### Built-in Templates (10)
| Template | Patterns | Builder |
|---|---|---|
| `login_dialog` | "show login", "login dialog", "sign in" | `build_login_dialog()` |
| `dashboard` | "create dashboard", "show dashboard", "metrics view" | `build_dashboard()` |
| `settings_dialog` | "open settings", "settings dialog", "preferences" | `build_settings_dialog()` |
| `file_explorer` | "show files", "file explorer", "browse files" | `build_file_explorer()` |
| `chat_interface` | "chat with", "open chat", "conversation" | `build_chat_interface()` |
| `confirm_dialog` | "confirm", "are you sure", "confirm delete" | `build_confirm_dialog()` |
| `progress_dialog` | "show progress", "progress bar", "loading" | `build_progress_dialog()` |
| `list_view` | "list", "show list", "table view" | `build_list_view()` |
| `form` | "create form", "form for", "input form" | `build_form()` |
| `generic_dialog` | "dialog", "popup", "modal" | `build_generic_dialog()` |

### PipelineResult
```python
@dataclass
class PipelineResult:
    success: bool
    intent_match: Optional[IntentMatch]
    scene_graph: Optional[SceneGraph]
    feature_instance: Optional[FeatureInstance]
    error: Optional[str] = None
    latency_ms: float = 0.0
```

---

## Window Manager — `src/os_kernel/window_manager.py`

```python
class WindowManager:
    def __init__(self, default_width="800px", default_height="600px", theme="light"):
        ...

    def create_window(self, spec: WidgetSpec) -> WindowInstance:
        """Create window from WidgetSpec."""
        ...

    def destroy_window(self, window_id: str) -> bool:
        """Destroy window."""
        ...

    def focus_window(self, window_id: str) -> bool:
        """Focus window."""
        ...

    def get_window_state(self, window_id: str) -> Optional[Dict]:
        """Get window state."""
        ...

    def list_windows(self) -> List[Dict]:
        """List all windows."""
        ...
```

---

## IPC (Inter-Process Communication) — `src/os_kernel/ipc.py`

```python
class IPCChannel:
    def __init__(self, channel_name: str):
        ...

    def send(self, message: Dict) -> bool:
        """Send message to channel."""
        ...

    def receive(self, timeout: float = 5.0) -> Optional[Dict]:
        """Receive message from channel."""
        ...

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register handler for message type."""
        ...

# Global IPC registry
def get_ipc_channel(name: str) -> IPCChannel: ...
def register_ipc_handler(channel: str, msg_type: str, handler: Callable) -> None: ...
def dispatch_ipc(channel: str, msg_type: str, payload: Dict) -> Any: ...
```

---

## Enums

### WidgetType
```python
class WidgetType(str, Enum):
    WINDOW = "window"
    PANEL = "panel"
    BUTTON = "button"
    LABEL = "label"
    TEXT_INPUT = "text_input"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO = "radio"
    SLIDER = "slider"
    PROGRESS = "progress"
    LIST = "list"
    TABLE = "table"
    CHART = "chart"
    IMAGE = "image"
    TAB = "tab"
    SPLITTER = "splitter"
```

### LayoutType
```python
class LayoutType(str, Enum):
    FLEX_ROW = "flex_row"
    FLEX_COL = "flex_col"
    GRID = "grid"
    ABSOLUTE = "absolute"
    STACK = "stack"
```

### Permission
```python
class Permission(str, Enum):
    FS_READ = "fs_read"
    FS_WRITE = "fs_write"
    NET_HTTP = "net_http"
    UI_RENDER = "ui_render"
    IPC_SEND = "ipc_send"
    MEMORY_READ = "memory_read"
    MEMORY_WRITE = "memory_write"
```

---

## Error Types

```python
class JayaOSError(Exception):
    """Base exception for JAYA_OS."""

class ValidationError(JayaOSError):
    """Schema/validation failure."""

class CompilationError(JayaOSError):
    """Feature compilation failure."""

class MountError(JayaOSError):
    """Feature mounting failure."""

class DispatchError(JayaOSError):
    """Action dispatch failure."""

class SandboxError(JayaOSError):
    """Sandbox execution failure."""

class PermissionError(JayaOSError):
    """Permission denied."""

class IPCError(JayaOSError):
    """IPC communication failure."""
```

---

## Configuration

### OSConfig
```python
@dataclass
class OSConfig:
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
    
    # Window Manager
    window_default_width: str = "800px"
    window_default_height: str = "600px"
    window_theme: str = "light"
    window_animations: bool = True
    window_max_windows: int = 20
    
    # IPC
    ipc_default_timeout: float = 5.0
    ipc_max_message_size: int = 1048576
    
    # Sandbox
    sandbox_cpu_limit_percent: int = 50
    sandbox_memory_limit_mb: int = 200
    sandbox_network_allowed: bool = False
```

---

## Usage Example

```python
from src.os_kernel.ui_spec import create_window, create_button, SceneGraph
from src.os_kernel.feature_compiler import FeatureCompiler
from src.os_kernel.feature_bridge import JayaBridge
from src.brain_v2.engine.intent_engine import IntentEngine
from src.os_kernel.intent_to_ui import IntentToUIPipeline

# Setup
compiler = FeatureCompiler()
bridge = JayaBridge("./features")
intent_engine = IntentEngine()
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