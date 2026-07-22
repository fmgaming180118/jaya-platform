# Spec Generators — JAYA_CORE Intent → Specification

## Overview

Spec Generators are the **brain-side components** that convert understood intent into formal specifications (UI specs, feature specs, task specs) for the house to compile and mount.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ BRAIN (brain_v2/engine/spec_generators.py)                                  │
│                                                                             │
│  IntentMatch (from IntentEngine)                                            │
│        │                                                                    │
│        ▼                                                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ SpecGeneratorRouter                                                 │   │
│  │  • Analyzes intent_type, suggested_ui, parameters                   │   │
│  │  • Routes to appropriate generator                                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│        │                                                                    │
│        ├──────────────────┬──────────────────┬──────────────────┐         │
│        ▼                  ▼                  ▼                  ▼         │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐  │
│  │ UISpecGen   │   │ FeatureSpecGen│   │ TaskSpecGen │   │ ActionSpecGen│ │
│  │             │   │             │   │             │   │             │  │
│  │ SceneGraph  │   │ FeatureMani-  │   │ Execution-  │   │ ActionSpec  │  │
│  │ (UI spec)   │   │ fest          │   │ Plan        │   │ (IPC)       │  │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘  │
│        │                  │                  │                  │         │
│        └──────────────────┴──────────────────┴──────────────────┘         │
│                                    │                                        │
│                                    ▼                                        │
│                    SPEC BUNDLE (JSON-serializable)                          │
│                    {ui_spec?, feature_spec?, task_spec?, action_spec?}      │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼ SPECS
┌─────────────────────────────────────────────────────────────────────────────┐
│ HOUSE (os_kernel) — Compiles & Mounts                                       │
│  • FeatureCompiler: SceneGraph → Feature                                    │
│  • FeatureRegistry: FeatureManifest → Mount                                 │
│  • JayaBridge: FeatureInstance → Dispatch                                   │
│  • IPC: ActionSpec → Execute                                                │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Spec Generator Interface

```python
class SpecGenerator:
    """Base class for all spec generators."""
    
    def can_handle(self, intent: IntentMatch) -> bool:
        """Return True if this generator handles the intent."""
        ...
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        """Generate specification bundle from intent."""
        ...

@dataclass
class SpecBundle:
    ui_spec: Optional[SceneGraph] = None
    feature_spec: Optional[FeatureManifest] = None
    task_spec: Optional[ExecutionPlan] = None
    action_spec: Optional[ActionSpec] = None
    metadata: Dict = field(default_factory=dict)
```

---

## 1. UI Spec Generator

### Purpose
Generate `SceneGraph` (declarative UI) from intent.

### Implementation
```python
class UISpecGenerator(SpecGenerator):
    def __init__(self, template_registry: UITemplateRegistry):
        self.templates = template_registry
    
    def can_handle(self, intent: IntentMatch) -> bool:
        return intent.suggested_ui is not None
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        template = self.templates.get(intent.suggested_ui)
        if not template:
            return SpecBundle(metadata={"error": f"Unknown UI template: {intent.suggested_ui}"})
        
        # Build SceneGraph using template builder
        scene = template.builder(**intent.parameters)
        
        return SpecBundle(
            ui_spec=scene,
            metadata={"template": intent.suggested_ui, "generator": "UISpecGenerator"}
        )
```

### Template Registry
```python
class UITemplateRegistry:
    def __init__(self):
        self.templates: Dict[str, UITemplate] = {}
        self._register_builtin()
    
    def _register_builtin(self):
        self.register(UITemplate(
            name="login_dialog",
            description="Username/password authentication dialog",
            patterns=[r"show login", r"login dialog", r"sign in"],
            builder=build_login_dialog,
            required_params=[],
            optional_params={"title": "Login", "show_remember": True, "fields": ["username", "password"]}
        ))
        # ... 9 more templates
    
    def register(self, template: UITemplate):
        self.templates[template.name] = template
    
    def get(self, name: str) -> Optional[UITemplate]:
        return self.templates.get(name)
    
    def match(self, intent: IntentMatch) -> List[UITemplate]:
        """Find templates matching intent patterns."""
        matches = []
        for template in self.templates.values():
            for pattern in template.patterns:
                if re.search(pattern, intent.raw_input, re.IGNORECASE):
                    matches.append(template)
                    break
        return matches
```

---

## 2. Feature Spec Generator

### Purpose
Generate `FeatureManifest` for capabilities beyond UI (background tasks, data processing, etc.).

### Implementation
```python
class FeatureSpecGenerator(SpecGenerator):
    def can_handle(self, intent: IntentMatch) -> bool:
        feature_intents = {"run_analysis", "process_data", "sync_knowledge", "train_model"}
        return intent.intent_type in feature_intents
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        feature_map = {
            "run_analysis": FeatureManifest(
                name="analysis_runner",
                version="1.0",
                entry_point="features.analysis:run",
                permissions=["fs_read", "memory_read", "cpu_compute"],
                config_schema={"analysis_type": "str", "dataset": "str"}
            ),
            "process_data": FeatureManifest(
                name="data_processor",
                version="1.0",
                entry_point="features.data:process",
                permissions=["fs_read", "fs_write", "cpu_compute"],
                config_schema={"input_path": "str", "output_path": "str", "transform": "str"}
            ),
            "sync_knowledge": FeatureManifest(
                name="knowledge_sync",
                version="1.0",
                entry_point="features.sync:run",
                permissions=["net_http", "memory_read", "memory_write"],
                config_schema={"source": "str", "target": "str", "mode": "str"}
            ),
            "train_model": FeatureManifest(
                name="model_trainer",
                version="1.0",
                entry_point="features.training:train",
                permissions=["fs_read", "fs_write", "cpu_compute", "gpu_compute"],
                config_schema={"model_type": "str", "dataset": "str", "epochs": "int"}
            )
        }
        
        manifest = feature_map.get(intent.intent_type)
        if manifest:
            # Override config with intent parameters
            manifest.config_schema.update(intent.parameters)
        
        return SpecBundle(
            feature_spec=manifest,
            metadata={"generator": "FeatureSpecGenerator"}
        )
```

---

## 3. Task Spec Generator

### Purpose
Generate `ExecutionPlan` for computational tasks.

### Implementation
```python
class TaskSpecGenerator(SpecGenerator):
    def can_handle(self, intent: IntentMatch) -> bool:
        task_intents = {"compute", "calculate", "simulate", "optimize", "search"}
        return any(t in intent.intent_type for t in task_intents)
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        # Delegate to TaskPlanner for complex planning
        from src.brain_v2.extensions.twin.task_planner import TaskPlanner
        
        planner = TaskPlanner()
        
        # Convert intent to JayaIR for planning
        from src.brain_v2.soul.lingua_logica import LinguaLogica
        from src.brain_v2.engine.jaya_ir import JayaIRTranslator
        
        lingua = LinguaLogica()
        translator = JayaIRTranslator()
        
        s_expr = lingua.normalize(intent)
        jaya_ir = translator.translate(s_expr)
        
        plan = planner.plan(jaya_ir)
        
        return SpecBundle(
            task_spec=plan,
            metadata={"generator": "TaskSpecGenerator", "ir_hash": hash_jaya_ir(jaya_ir)}
        )
```

---

## 4. Action Spec Generator

### Purpose
Generate `ActionSpec` for direct IPC actions (no UI, no feature mount).

### Implementation
```python
class ActionSpecGenerator(SpecGenerator):
    def can_handle(self, intent: IntentMatch) -> bool:
        action_intents = {"shutdown", "restart", "status", "config_get", "config_set"}
        return intent.intent_type in action_intents
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        action_map = {
            "shutdown": ActionSpec(channel="system", action="shutdown", payload={}),
            "restart": ActionSpec(channel="system", action="restart", payload={}),
            "status": ActionSpec(channel="system", action="status", payload={}),
            "config_get": ActionSpec(channel="config", action="get", payload={"key": intent.parameters.get("key")}),
            "config_set": ActionSpec(channel="config", action="set", payload=intent.parameters),
        }
        
        return SpecBundle(
            action_spec=action_map.get(intent.intent_type),
            metadata={"generator": "ActionSpecGenerator"}
        )
```

---

## Spec Generator Router

```python
class SpecGeneratorRouter:
    def __init__(self):
        self.generators: List[SpecGenerator] = [
            UISpecGenerator(UITemplateRegistry()),
            FeatureSpecGenerator(),
            TaskSpecGenerator(),
            ActionSpecGenerator(),
        ]
    
    def generate(self, intent: IntentMatch) -> SpecBundle:
        """Route intent to appropriate generator(s)."""
        bundle = SpecBundle()
        
        for gen in self.generators:
            if gen.can_handle(intent):
                result = gen.generate(intent)
                # Merge results (later generators can override)
                if result.ui_spec:
                    bundle.ui_spec = result.ui_spec
                if result.feature_spec:
                    bundle.feature_spec = result.feature_spec
                if result.task_spec:
                    bundle.task_spec = result.task_spec
                if result.action_spec:
                    bundle.action_spec = result.action_spec
                bundle.metadata.update(result.metadata)
        
        return bundle
```

---

## Integration with IntentToUIPipeline (Phase 3C)

Current Phase 3C uses `IntentToUIPipeline` in `os_kernel/intent_to_ui.py`. Future Phase 3 moves spec generation to brain side:

```python
# Current (Phase 3C - in os_kernel)
pipeline = IntentToUIPipeline(bridge, intent_engine)
result = pipeline.process_intent("show login dialog")

# Future (Phase 3 - brain generates specs)
from src.brain_v2.engine.spec_generators import SpecGeneratorRouter

router = SpecGeneratorRouter()
intent_match = intent_engine.match("show login dialog")[0]
spec_bundle = router.generate(intent_match)

# House compiles & mounts
if spec_bundle.ui_spec:
    feature = bridge.mount_feature(spec_bundle.ui_spec)
if spec_bundle.feature_spec:
    feature = bridge.mount_feature(spec_bundle.feature_spec)
if spec_bundle.action_spec:
    bridge.dispatch_ipc(spec_bundle.action_spec)
```

---

## Testing

```bash
# Spec Generator Tests (when implemented)
python -m pytest tests/ -k "spec_generator" -v

# Integration with IntentToUIPipeline
python -m pytest tests/test_phase3c_intent_to_ui.py -v
```

---

## 🔗 Related Docs

- [Dynamic Spec Generation](../03-features/dynamic-spec-gen.md) — Full architecture
- [API Reference](../02-architecture/api-reference.md) — SceneGraph, FeatureManifest interfaces
- [Roadmap Phase 3](../06-roadmap/phase-3-dynamic-specs.md) — Implementation plan