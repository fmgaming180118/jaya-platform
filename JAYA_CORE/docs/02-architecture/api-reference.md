# API Reference — JAYA_CORE

Complete interface definitions for JAYA_CORE cognitive core.

---

## Data Structures

### IntentMatch
```python
@dataclass
class IntentMatch:
    intent_type: str
    confidence: float
    suggested_ui: Optional[str] = None
    parameters: Dict[str, Any] = field(default_factory=dict)
    raw_input: str = ""
```

### JayaIR
```python
@dataclass
class JayaIR:
    opcode: str                   # Strict opcode from JayaIROpcode enum
    operands: List[Operand]       # Typed operands
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str: ...
    @classmethod
    def from_json(cls, json_str: str) -> 'JayaIR': ...
    def validate(self) -> ValidationResult: ...
```

### Operand
```python
@dataclass
class Operand:
    type: OperandType             # INT, FLOAT, STRING, BOOL, REF, VECTOR
    value: Any
    shape: Optional[Tuple[int]] = None  # For vectors/tensors
```

### ExecutionResult
```python
@dataclass
class ExecutionResult:
    success: bool
    output: Any
    latency_ms: float
    cache_hit: bool
    plan_hash: str
    error: Optional[str] = None
```

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
    props: Dict[str, Any]         # Type-specific properties
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
    entry_point: str              # Python module:function
    permissions: List[str]        # Required permissions
    dependencies: List[str]       # Other features
    ui_spec: Optional[SceneGraph] = None
    config_schema: Dict[str, Any] = field(default_factory=dict)
```

---

## Core Interfaces

### IntentEngine — `src/brain_v2/engine/intent_engine.py`
```python
class IntentEngine:
    def __init__(self, tfidf_max_features=5000, tfidf_ngram_range=(1,2), min_confidence=0.3, learning_enabled=True):
        ...

    def learn(self, text: str) -> None:
        """Learn new intent from user input (online learning)."""
        ...

    def predict_intent(self, text: str, top_k=5) -> List[Tuple[str, float]]:
        """Predict intent from text. Returns [(intent, confidence), ...]."""
        ...

    def classify(self, text: str) -> Optional[IntentMatch]:
        """Classify single intent. Returns IntentMatch or None."""
        ...

    def match(self, text: str) -> List[IntentMatch]:
        """Full intent matching with parameter extraction."""
        ...

    def get_status(self) -> Dict:
        """Engine status: vocab size, learned count, etc."""
        ...

    def save(self, path: str) -> None:
        """Persist model to disk."""
        ...

    @classmethod
    def load(cls, path: str) -> 'IntentEngine':
        """Load model from disk."""
        ...
```

### LinguaLogica — `src/brain_v2/soul/lingua_logica.py`
```python
class LinguaLogica:
    def normalize(self, intent: IntentMatch) -> SExpression:
        """Normalize intent to S-expression canonical form."""
        ...

    def validate(self, expr: SExpression) -> ValidationResult:
        """Validate S-expression structure & types."""
        ...

    def to_jaya_ir(self, expr: SExpression) -> JayaIR:
        """Convert validated S-expression to JayaIR."""
        ...
```

### JayaIRTranslator — `src/brain_v2/engine/jaya_ir.py`
```python
class JayaIRTranslator:
    def translate(self, expr: SExpression) -> JayaIR:
        """S-expression → JayaIR (strict opcode validation)."""
        ...

    def validate(self, ir: JayaIR) -> ValidationResult:
        """Validate JayaIR structure & operand types."""
        ...

    def serialize(self, ir: JayaIR) -> str:
        """JayaIR → JSON string."""
        ...

    def deserialize(self, json_str: str) -> JayaIR:
        """JSON string → JayaIR."""
        ...
```

### IronEngine (Runtime) — `src/brain_v2/engine/runtime.py`
```python
class IronEngine:
    def __init__(self, config: AgiConfig):
        self.config = config
        self.resource_monitor = ResourceMonitor()
        self.ethical_heart = EthicalHeart()
        self.plan_cache: Dict[str, Callable] = {}

    def execute_intent(self, intent: IntentMatch) -> ExecutionResult:
        """Full pipeline: intent → JayaIR → plan → execute."""
        ...

    def execute_jaya_ir(self, ir: JayaIR) -> ExecutionResult:
        """Execute pre-compiled JayaIR."""
        ...

    def get_cached_plan(self, ir_hash: str) -> Optional[Callable]:
        """Lookup cached execution plan."""
        ...

    def cache_plan(self, ir_hash: str, plan: Callable) -> None:
        """Cache compiled plan."""
        ...

    def enter_silence(self) -> None:
        """Enter cognitive silence mode (high CPU)."""
        ...

    def exit_silence(self) -> None:
        """Exit silence mode."""
        ...

    def status(self) -> Dict[str, Any]:
        """Runtime status: resource monitor, cache stats, ethical state."""
        ...
```

### ResourceMonitor — `src/brain_v2/organism/resource_monitor.py`
```python
def get_readings() -> Dict[str, float]:
    """Current readings: {'cpu_pct', 'mem_pct', 'battery_pct'}."""
    ...

class ResourceMonitor:
    def __init__(self, check_interval=5.0, high_cpu_threshold=85.0, low_cpu_threshold=40.0):
        ...

    def attach(self, engine: IronEngine) -> None:
        """Attach to engine for auto-adjustment."""
        ...

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def get_last_readings(self) -> Dict[str, float]: ...
```

### EthicalHeart — `src/brain_v2/soul/ethical_heart.py`
```python
class EthicalHeart:
    def evaluate(self, action: Dict[str, Any]) -> EthicalVerdict:
        """Evaluate action against moral vector."""
        ...

    def is_safe(self, action: Dict[str, Any]) -> bool:
        """Quick safety check (blocks bypass/exfiltration)."""
        ...
```

---

## Os_Kernel (Home Layer) — Core Interfaces

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

    def mount_feature(self, manifest: FeatureManifest) -> FeatureInstance:
        """Compile, sandbox, and mount feature."""
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
```

---

## Intent → UI Pipeline

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

### JayaIROpcode (Strict)
```python
class JayaIROpcode(str, Enum):
    # Control flow
    CALL = "call"
    BRANCH = "branch"
    LOOP = "loop"
    RETURN = "return"
    
    # Data operations
    LOAD = "load"
    STORE = "store"
    TRANSFORM = "transform"
    AGGREGATE = "aggregate"
    
    # Logic
    AND = "and"
    OR = "or"
    NOT = "not"
    COMPARE = "compare"
    
    # Memory
    MEM_READ = "mem_read"
    MEM_WRITE = "mem_write"
    MEM_CONSOLIDATE = "mem_consolidate"
    
    # Learning
    LEARN = "learn"
    ADAPT = "adapt"
    EVOLVE = "evolve"
    
    # I/O
    EMIT = "emit"
    RECEIVE = "receive"
    
    # Meta
    NOOP = "noop"
    CHECKPOINT = "checkpoint"
```

---

## Error Types

```python
class JayaError(Exception):
    """Base exception for JAYA_CORE."""

class ValidationError(JayaError):
    """Schema/validation failure."""

class CompilationError(JayaError):
    """Feature compilation failure."""

class MountError(JayaError):
    """Feature mounting failure."""

class ExecutionError(JayaError):
    """Runtime execution failure."""

class SecurityError(JayaError):
    """EthicalHeart/ZeroTrust violation."""

class ResourceError(JayaError):
    """ResourceMonitor threshold exceeded."""
```

---

## Configuration

### AgiConfig
```python
@dataclass
class AgiConfig:
    # Cognitive
    topk_ratio: float = 0.10
    silence_mode: bool = False
    
    # Resource
    resource_check_interval: float = 5.0
    high_cpu_threshold: float = 85.0
    low_cpu_threshold: float = 40.0
    
    # Security
    ethical_strict_mode: bool = True
    zero_trust_enabled: bool = True
    dna_anchor_required: bool = True
    
    # Evolution
    evolution_enabled: bool = True
    promotion_throughput_gain: float = 0.08
    promotion_ram_increase: float = 0.05
    
    # Cache
    plan_cache_size: int = 1000
    plan_cache_ttl: int = 3600
```

---

## Usage Example

```python
from src.brain_v2.engine.intent_engine import IntentEngine
from src.brain_v2.engine.runtime import IronEngine, AgiConfig
from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.intent_to_ui import IntentToUIPipeline

# Setup
config = AgiConfig()
engine = IronEngine(config)
intent_engine = IntentEngine()
bridge = JayaBridge("./features")
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

---

### `FeatureRegistry` — `src/os_kernel/feature_registry.py`

```python
class FeatureRegistry:
    def __init__(self, features_dir: str):
        ...

    def discover_features(self) -> List[FeatureManifest]:
        """Discover all feature packages in features_dir."""
        ...

    def get_feature(self, feature_name: str) -> Optional[FeatureManifest]:
        """Get feature manifest by name."""
        ...

    def register_feature(self, manifest: FeatureManifest) -> None:
        """Register feature (add to index)."""
        ...

    def unregister_feature(self, feature_name: str) -> None:
        """Unregister feature."""
        ...
```

---

### `JayaBridge` — `src/os_kernel/feature_bridge.py`

```python
class JayaBridge:
    def __init__(self, features_dir: str, mount_timeout=10, max_features=50):
        ...

    def mount_feature(self, feature_name: str, config: Dict = None) -> str:
        """Mount feature in sandbox. Return feature_id."""
        ...

    def unmount_feature(self, feature_id: str) -> bool:
        """Unmount feature by ID."""
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

---

### `IntentToUIPipeline` — `src/os_kernel/intent_to_ui.py`

```python
class IntentToUIPipeline:
    def __init__(self, bridge: JayaBridge, intent_engine: IntentEngine):
        ...

    def match_intent(self, user_input: str) -> List[IntentMatch]:
        """Match user input to UI templates."""
        ...

    def extract_parameters(self, user_input: str, template_name: str) -> Dict:
        """Extract parameters from user input for template."""
        ...

    def process_intent(self, user_input: str) -> PipelineResult:
        """Full pipeline: match → extract → build SceneGraph → compile → mount."""
        ...

    def list_templates(self) -> List[Dict]:
        """List available UI templates."""
        ...

    # Built-in templates (10):
    # login_dialog, dashboard, settings_dialog, file_explorer,
    # chat_interface, confirm_dialog, progress_dialog, list_view, form, generic_dialog
```

---

### `SceneGraph` / `WidgetSpec` — `src/os_kernel/ui_spec.py`

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
    type: WidgetType
    props: Dict = field(default_factory=dict)
    children: List['WidgetSpec'] = field(default_factory=list)
    events: List[EventHandler] = field(default_factory=list)
    bindings: List[Binding] = field(default_factory=list)
    style: StyleTokens = field(default_factory=StyleTokens)

class WidgetType(Enum):
    WINDOW = "window"
    PANEL = "panel"
    BUTTON = "button"
    LABEL = "label"
    TEXT_INPUT = "text_input"
    TEXTAREA = "textarea"
    SELECT = "select"
    LIST = "list"
    TABLE = "table"
    CHART = "chart"
    PROGRESS = "progress"
    TAB = "tab"
    MODAL = "modal"
```

**Factory Functions:**
```python
def create_window(title: str, width: str, height: str, children: List[WidgetSpec] = None, **props) -> WidgetSpec: ...
def create_panel(layout: LayoutType = LayoutType.FLEX_COL, children: List[WidgetSpec] = None, **props) -> WidgetSpec: ...
def create_button(label: str, on_click: str = None, **props) -> WidgetSpec: ...
def create_label(text: str, **props) -> WidgetSpec: ...
def create_text_input(placeholder: str = "", on_change: str = None, **props) -> WidgetSpec: ...
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

## Shared Language Layer — `src/jaya_language/`

```python
# Contracts & IR definitions shared between brain_v2 and os_kernel
# - JayaIR schema (OpCode, Operand, validation)
# - IntentMatch, PipelineResult dataclasses
# - UI Spec types (WidgetType, LayoutType, StyleTokens)
# - Feature Manifest schema
# - Action/Event types (JayaActions)
```

---

## 🔗 Lanjutkan ke

- [Components](components.md) — Module-by-module breakdown
- [Cognitive Features](../03-features/cognitive-features.md) — Intent, Reasoning, Planning, Memory
- [Dynamic Spec Generation](../03-features/dynamic-spec-gen.md) — Intent → UI/Feature/Task specs