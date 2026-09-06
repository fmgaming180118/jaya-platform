"""
spec_generators.py — Phase 3 Brain-Side Specification Generation Engine for JAYA_CORE

Implements brain-side spec generators:
- IntentMatch: Pure brain-side intent match dataclass.
- SceneGraph & WidgetSpec: Pure brain-side UI specification contracts.
- FeatureManifest: Pure brain-side feature capability manifest specification.
- ExecutionPlan: Task Spec DAG specification.
- ActionSpec: Action Spec IPC command specification.
- SpecBundle: Container for generated UI, Feature, Task, and Action specifications.
- SpecGenerator: Abstract base class for spec generators.
- UITemplateRegistry: Registry of built-in UI templates.
- UISpecGenerator: Generates SceneGraph / WidgetSpec UI specifications.
- FeatureSpecGenerator: Generates FeatureManifest capability specifications.
- TaskSpecGenerator: Generates ExecutionPlan / JayaIR DAG task specifications.
- ActionSpecGenerator: Generates ActionSpec direct IPC specifications.
- SpecGeneratorRouter: Central router dispatching intents to appropriate spec generators.
"""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, Optional

from jaya_core.brain_v2.engine.action_protocol import (
    DEFAULT_ACTION_CATALOG,
    ActionPlan,
    ActionPolicy,
    ActionStep,
    AuthorizationDecision,
    ExecutionReceipt,
    ReceiptOutcome,
    RiskLevel,
    SideEffectClass,
    build_action_plan,
)


@dataclass
class IntentMatch:
    """Pure brain-side intent match result."""
    intent_type: str
    confidence: float
    parameters: Dict[str, Any] = field(default_factory=dict)
    suggested_ui: Optional[str] = None


@dataclass
class WidgetSpec:
    """Pure brain-side Widget specification."""
    id: str
    type: str
    label: str = ""
    placeholder: str = ""
    value: Any = None
    options: List[Dict[str, Any]] = field(default_factory=list)
    children: List["WidgetSpec"] = field(default_factory=list)
    style: Dict[str, Any] = field(default_factory=dict)
    layout: Optional[str] = None
    events: List[Dict[str, Any]] = field(default_factory=list)
    bindings: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class SceneGraph:
    """Pure brain-side SceneGraph UI specification."""
    name: str
    description: str
    root: WidgetSpec
    version: str = "1.0"
    metadata: Dict[str, Any] = field(default_factory=dict)


def create_window(title: str, width: str = "600px", height: str = "400px", children: List[WidgetSpec] = None) -> WidgetSpec:
    """Helper to create a window widget spec."""
    return WidgetSpec(
        id=f"win_{int(time.time()*1000)}",
        type="window",
        label=title,
        style={"width": width, "height": height, "title": title},
        children=children or []
    )


def create_panel(layout: str = "flex_col", children: List[WidgetSpec] = None) -> WidgetSpec:
    """Helper to create a panel widget spec."""
    return WidgetSpec(
        id=f"panel_{int(time.time()*1000)}",
        type="panel",
        layout=layout,
        children=children or []
    )


def create_label(text: str, id: Optional[str] = None) -> WidgetSpec:
    """Helper to create a label widget spec."""
    return WidgetSpec(
        id=id or f"lbl_{int(time.time()*1000)}",
        type="label",
        label=text,
        value=text
    )


def create_button(label: str, on_click: str = "", id: Optional[str] = None) -> WidgetSpec:
    """Helper to create a button widget spec."""
    events = [{"event": "click", "action": on_click}] if on_click else []
    return WidgetSpec(
        id=id or f"btn_{int(time.time()*1000)}",
        type="button",
        label=label,
        events=events
    )


def create_text_input(placeholder: str = "", id: Optional[str] = None) -> WidgetSpec:
    """Helper to create a text input widget spec."""
    return WidgetSpec(
        id=id or f"txt_{int(time.time()*1000)}",
        type="text_input",
        placeholder=placeholder
    )


@dataclass
class FeatureManifest:
    """Feature Spec — Feature capability manifest specification."""
    name: str
    version: str = "1.0.0"
    entry_point: str = "src.main:run"
    permissions: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)
    ui_spec: Optional[SceneGraph] = None
    config_schema: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExecutionStep:
    """Represents a single step in a TaskSpec ExecutionPlan."""
    step_id: str
    action: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    timeout_sec: float = 30.0


@dataclass
class ExecutionPlan:
    """Task Spec — Execution plan DAG produced by TaskSpecGenerator."""
    plan_id: str
    steps: List[ExecutionStep] = field(default_factory=list)
    dependencies: Dict[str, List[str]] = field(default_factory=dict)
    parallel_groups: List[List[str]] = field(default_factory=list)
    estimated_latency_ms: float = 1.0
    required_resources: Dict[str, float] = field(default_factory=dict)
    priority: int = 0

    @property
    def status(self) -> str:
        """A brain-generated task specification never proves execution."""

        return "PLAN_ONLY"


@dataclass
class ActionSpec:
    """Action Spec — IPC action command specification."""
    channel: str
    action: str
    payload: Dict[str, Any] = field(default_factory=dict)
    require_auth: bool = True
    timestamp: float = field(default_factory=time.time)

    @property
    def status(self) -> str:
        """An IPC action specification is a plan, not an execution claim."""

        return "PLAN_ONLY"


@dataclass
class SpecBundle:
    """Container holding one or more generated specifications."""
    bundle_id: str
    ui_spec: Optional[SceneGraph] = None
    feature_spec: Optional[FeatureManifest] = None
    task_spec: Optional[ExecutionPlan] = None
    action_spec: Optional[ActionSpec] = None
    action_plan: Optional[ActionPlan] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    _execution_receipt: Optional[ExecutionReceipt] = field(
        default=None,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        metadata = dict(self.metadata)
        metadata.pop("execution_status", None)
        metadata.pop("execution_receipt_digest", None)
        self.metadata = MappingProxyType(metadata)

    @property
    def execution_receipt(self) -> Optional[ExecutionReceipt]:
        """Return authenticated evidence attached through the policy boundary."""

        return self._execution_receipt

    @property
    def execution_status(self) -> str:
        """Derive status only from an authenticated attached receipt."""

        if self._execution_receipt is None:
            return "PLAN_ONLY"
        if self._execution_receipt.outcome is ReceiptOutcome.SUCCEEDED:
            return "EXECUTED"
        return "EXECUTION_FAILED"

    def status_snapshot(self) -> dict[str, Any]:
        """Return UI-safe metadata with evidence-bound execution status."""

        snapshot = {**self.metadata, "execution_status": self.execution_status}
        if self._execution_receipt is not None:
            snapshot["execution_receipt_digest"] = (
                self._execution_receipt.receipt_digest
            )
        return snapshot

    def is_empty(self) -> bool:
        """Returns True if no specifications are contained in the bundle."""
        return (
            self.ui_spec is None and
            self.feature_spec is None and
            self.task_spec is None and
            self.action_spec is None and
            self.action_plan is None
        )

    def apply_execution_receipt(
        self,
        *,
        policy: ActionPolicy,
        authorization: AuthorizationDecision,
        receipt: ExecutionReceipt,
    ) -> str:
        """Advance compatibility status only after receipt authentication."""

        if self.action_plan is None:
            raise ValueError("bundle has no ActionPlan")
        policy.verify_receipt(
            receipt,
            plan=self.action_plan,
            authorization=authorization,
        )
        self._execution_receipt = receipt
        return self.execution_status


class SpecGenerator(ABC):
    """Abstract base class for brain-side specification generators."""

    @abstractmethod
    def can_handle(self, intent: IntentMatch) -> bool:
        """Returns True if this generator can handle the given intent."""
        pass

    @abstractmethod
    def generate(self, intent: IntentMatch) -> SpecBundle:
        """Generates a SpecBundle for the given intent."""
        pass


class UITemplateRegistry:
    """Registry managing 10 built-in UI templates for UISpecGenerator."""

    def __init__(self):
        self._templates: Dict[str, Dict[str, Any]] = {}
        self._register_default_templates()

    def register(self, name: str, description: str, patterns: List[str], builder_fn: Any):
        """Registers a UI template."""
        self._templates[name] = {
            "name": name,
            "description": description,
            "patterns": patterns,
            "builder": builder_fn,
        }

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Retrieves a registered template by name."""
        return self._templates.get(name)

    def list_templates(self) -> List[Dict[str, Any]]:
        """Returns list of registered templates."""
        return list(self._templates.values())

    def _register_default_templates(self):
        """Registers the 10 core built-in UI templates."""
        # 1. Login Dialog
        self.register(
            "login_dialog",
            "User login dialog with username and password",
            ["login", "sign in", "auth"],
            lambda title="Sign In", show_remember=True, **kwargs: SceneGraph(
                name="Login Dialog",
                description="User authentication dialog",
                root=create_window(
                    title=title, width="380px", height="280px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label("Username"),
                                create_text_input(placeholder="Enter username", id="username_input"),
                                create_label("Password"),
                                create_text_input(placeholder="Enter password", id="password_input"),
                                create_button(label="Submit", on_click="jaya:auth_submit", id="login_btn"),
                            ]
                        )
                    ]
                )
            )
        )

        # 2. Dashboard
        self.register(
            "dashboard",
            "System metrics dashboard panel",
            ["dashboard", "metrics", "overview"],
            lambda title="JAYA System Dashboard", **kwargs: SceneGraph(
                name="Dashboard",
                description="System metrics overview",
                root=create_window(
                    title=title, width="800px", height="600px",
                    children=[
                        create_panel(
                            layout="grid",
                            children=[
                                create_label("CPU Load: 12%"),
                                create_label("RAM Usage: 1.4 GB"),
                                create_label("Cache Hit Rate: 97.6%"),
                                create_button(label="Refresh", on_click="jaya:refresh_metrics"),
                            ]
                        )
                    ]
                )
            )
        )

        # 3. Settings Dialog
        self.register(
            "settings_dialog",
            "System preferences and settings",
            ["settings", "preferences", "config"],
            lambda title="Settings", **kwargs: SceneGraph(
                name="Settings Dialog",
                description="System preferences",
                root=create_window(
                    title=title, width="500px", height="400px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label("Theme: Dark Sovereign"),
                                create_label("Log Level: INFO"),
                                create_button(label="Save Settings", on_click="jaya:save_settings"),
                            ]
                        )
                    ]
                )
            )
        )

        # 4. File Explorer
        self.register(
            "file_explorer",
            "File browser and workspace navigation",
            ["files", "browse", "explorer"],
            lambda title="File Explorer", **kwargs: SceneGraph(
                name="File Explorer",
                description="Browse workspace files",
                root=create_window(
                    title=title, width="700px", height="500px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label("Workspace Root: ./"),
                                create_button(label="Open File", on_click="jaya:open_file"),
                            ]
                        )
                    ]
                )
            )
        )

        # 5. Chat Interface
        self.register(
            "chat_interface",
            "Conversational RAG & Assistant interface",
            ["chat", "assistant", "ask"],
            lambda title="JAYA Assistant", **kwargs: SceneGraph(
                name="Chat Interface",
                description="Chat with JAYA",
                root=create_window(
                    title=title, width="600px", height="700px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label("JAYA Sovereign RAG Agent"),
                                create_text_input(placeholder="Type your prompt...", id="chat_input"),
                                create_button(label="Send", on_click="jaya:send_chat", id="send_btn"),
                            ]
                        )
                    ]
                )
            )
        )

        # 6. Confirm Dialog
        self.register(
            "confirm_dialog",
            "Confirmation prompt modal",
            ["confirm", "are you sure", "prompt"],
            lambda title="Confirm Action", message="Are you sure?", **kwargs: SceneGraph(
                name="Confirm Dialog",
                description="Action confirmation",
                root=create_window(
                    title=title, width="350px", height="200px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label(message),
                                create_button(label="Confirm", on_click="jaya:confirm_yes"),
                                create_button(label="Cancel", on_click="jaya:confirm_no"),
                            ]
                        )
                    ]
                )
            )
        )

        # 7. Progress Dialog
        self.register(
            "progress_dialog",
            "Task authorization and execution status",
            ["progress", "loading", "status"],
            lambda title="Task Progress", **kwargs: SceneGraph(
                name="Progress Dialog",
                description="Task authorization status",
                root=create_window(
                    title=title, width="400px", height="180px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label("Task planned; awaiting authorization"),
                                create_label("Status: PLAN_ONLY"),
                            ]
                        )
                    ]
                )
            )
        )

        # 8. List View
        self.register(
            "list_view",
            "Tabular / list item layout",
            ["list", "table", "items"],
            lambda title="Item List", **kwargs: SceneGraph(
                name="List View",
                description="Data item listing",
                root=create_window(
                    title=title, width="650px", height="450px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label("Registered Items"),
                                create_button(label="Add Item", on_click="jaya:add_item"),
                            ]
                        )
                    ]
                )
            )
        )

        # 9. Form
        self.register(
            "form",
            "Dynamic input form container",
            ["form", "input", "entry"],
            lambda title="Input Form", **kwargs: SceneGraph(
                name="Form",
                description="Dynamic input form",
                root=create_window(
                    title=title, width="480px", height="380px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label("Input Data"),
                                create_text_input(placeholder="Enter data...", id="form_input"),
                                create_button(label="Submit", on_click="jaya:submit_form"),
                            ]
                        )
                    ]
                )
            )
        )

        # 10. Generic Dialog
        self.register(
            "generic_dialog",
            "Generic modal window container",
            ["dialog", "popup", "modal"],
            lambda title="Dialog", **kwargs: SceneGraph(
                name="Generic Dialog",
                description="Generic modal container",
                root=create_window(
                    title=title, width="400px", height="300px",
                    children=[
                        create_panel(
                            layout="flex_col",
                            children=[
                                create_label(title),
                                create_button(label="OK", on_click="jaya:close_dialog"),
                            ]
                        )
                    ]
                )
            )
        )


class UISpecGenerator(SpecGenerator):
    """Brain-side UI Spec Generator producing SceneGraph specifications."""

    def __init__(self, template_registry: Optional[UITemplateRegistry] = None):
        self.registry = template_registry or UITemplateRegistry()

    def can_handle(self, intent: IntentMatch) -> bool:
        return intent.suggested_ui is not None or any(
            t in intent.intent_type for t in ["show_", "open_", "create_ui", "view_"]
        )

    def generate(self, intent: IntentMatch) -> SpecBundle:
        template_name = intent.suggested_ui or "generic_dialog"
        template = self.registry.get(template_name)
        if not template:
            template = self.registry.get("generic_dialog")

        builder = template["builder"]
        scene: SceneGraph = builder(**intent.parameters)
        return SpecBundle(
            bundle_id=f"bundle-ui-{intent.intent_type}-{int(time.time())}",
            ui_spec=scene,
            metadata={"template": template_name, "intent_type": intent.intent_type}
        )


class FeatureSpecGenerator(SpecGenerator):
    """Brain-side Feature Spec Generator producing FeatureManifest capability specs."""

    FEATURE_MAP = {
        "run_analysis": ("analysis_module", "src.research.analysis:run"),
        "process_data": ("data_processor", "src.research.processor:process"),
        "sync_knowledge": ("knowledge_syncer", "src.research.sync:sync"),
        "train_model": ("student_trainer", "src.training.distill:train"),
    }

    def can_handle(self, intent: IntentMatch) -> bool:
        return intent.intent_type in self.FEATURE_MAP or any(
            k in intent.intent_type for k in ["analysis", "process", "sync", "train"]
        )

    def generate(self, intent: IntentMatch) -> SpecBundle:
        feat_info = self.FEATURE_MAP.get(intent.intent_type, ("generic_feature", "src.generic:run"))
        feat_name, entry_point = feat_info

        manifest = FeatureManifest(
            name=feat_name,
            version="1.0.0",
            entry_point=entry_point,
            permissions=["fs_read", "net_http"],
            dependencies=[],
            config_schema=intent.parameters
        )

        return SpecBundle(
            bundle_id=f"bundle-feature-{intent.intent_type}-{int(time.time())}",
            feature_spec=manifest,
            metadata={"feature_name": feat_name, "intent_type": intent.intent_type}
        )


class TaskSpecGenerator(SpecGenerator):
    """Brain-side Task Spec Generator producing ExecutionPlan DAG specs."""

    def __init__(self, action_policy: Optional[ActionPolicy] = None) -> None:
        self._action_policy = action_policy

    def can_handle(self, intent: IntentMatch) -> bool:
        return any(t in intent.intent_type for t in ["compute", "calculate", "simulate", "optimize", "task"])

    def generate(self, intent: IntentMatch) -> SpecBundle:
        steps = [
            ExecutionStep(
                step_id="step_1_init",
                action="init_context",
                parameters={"intent": intent.intent_type}
            ),
            ExecutionStep(
                step_id="step_2_execute",
                action="run_computation",
                parameters=intent.parameters
            ),
            ExecutionStep(
                step_id="step_3_finalize",
                action="format_result",
                parameters={}
            )
        ]

        plan = ExecutionPlan(
            plan_id=f"plan-{intent.intent_type}-{int(time.time())}",
            steps=steps,
            dependencies={"step_2_execute": ["step_1_init"], "step_3_finalize": ["step_2_execute"]},
            parallel_groups=[["step_1_init"], ["step_2_execute"], ["step_3_finalize"]],
            estimated_latency_ms=1.5,
            required_resources={"cpu_topk": 0.10, "ram_mb": 50.0},
            priority=10
        )
        action_steps = (
            ActionStep(
                step_id="step_1_init",
                action="init_context",
                parameters={"intent": intent.intent_type},
            ),
            ActionStep(
                step_id="step_2_execute",
                action="run_computation",
                parameters=intent.parameters,
                required_capabilities=("compute.execute",),
            ),
            ActionStep(
                step_id="step_3_finalize",
                action="format_result",
            ),
        )
        plan_kwargs = {
            "intent": {
                "intent_type": intent.intent_type,
                "parameters": intent.parameters,
            },
            "ordered_steps": action_steps,
            "risk": RiskLevel.LOW,
            "required_capabilities": ("compute.execute",),
            "side_effect_class": SideEffectClass.NONE,
        }
        action_plan = (
            self._action_policy.create_plan(**plan_kwargs)
            if self._action_policy is not None
            else build_action_plan(**plan_kwargs)
        )

        return SpecBundle(
            bundle_id=f"bundle-task-{intent.intent_type}-{int(time.time())}",
            task_spec=plan,
            action_plan=action_plan,
            metadata={
                "plan_id": plan.plan_id,
                "action_plan_id": action_plan.plan_id,
                "intent_type": intent.intent_type,
            },
        )


class ActionSpecGenerator(SpecGenerator):
    """Brain-side Action Spec Generator producing ActionSpec IPC specs."""

    ACTION_MAP = {
        "shutdown": ("os_control", "shutdown_system"),
        "restart": ("os_control", "restart_system"),
        "status": ("observability", "get_status"),
        "config_get": ("config_manager", "get_config"),
        "config_set": ("config_manager", "set_config"),
    }

    def __init__(self, action_policy: Optional[ActionPolicy] = None) -> None:
        self._action_policy = action_policy

    def can_handle(self, intent: IntentMatch) -> bool:
        return intent.intent_type in self.ACTION_MAP or any(
            a in intent.intent_type for a in ["shutdown", "restart", "status", "config"]
        )

    def generate(self, intent: IntentMatch) -> SpecBundle:
        channel, action = self.ACTION_MAP.get(intent.intent_type, ("ipc_default", intent.intent_type))

        action_spec = ActionSpec(
            channel=channel,
            action=action,
            payload=intent.parameters,
            require_auth=True
        )
        requirement = DEFAULT_ACTION_CATALOG.get(action)
        required_capabilities = (
            requirement.required_capabilities if requirement is not None else ()
        )
        side_effect_class = (
            requirement.side_effect_class
            if requirement is not None
            else SideEffectClass.NONE
        )
        risk = (
            requirement.minimum_risk if requirement is not None else RiskLevel.LOW
        )
        plan_kwargs = {
            "intent": {
                "intent_type": intent.intent_type,
                "parameters": intent.parameters,
            },
            "ordered_steps": (
                ActionStep(
                    step_id="step_1_action",
                    action=action,
                    parameters={
                        "channel": channel,
                        "payload": intent.parameters,
                    },
                    required_capabilities=required_capabilities,
                    side_effect_class=side_effect_class,
                ),
            ),
            "risk": risk,
            "required_capabilities": required_capabilities,
            "side_effect_class": side_effect_class,
        }
        action_plan = (
            self._action_policy.create_plan(**plan_kwargs)
            if self._action_policy is not None
            else build_action_plan(**plan_kwargs)
        )

        return SpecBundle(
            bundle_id=f"bundle-action-{intent.intent_type}-{int(time.time())}",
            action_spec=action_spec,
            action_plan=action_plan,
            metadata={
                "channel": channel,
                "action": action,
                "action_plan_id": action_plan.plan_id,
            },
        )


class SpecGeneratorRouter:
    """
    Central router dispatching intents to brain-side spec generators
    to assemble a composite SpecBundle.
    """

    def __init__(
        self,
        template_registry: Optional[UITemplateRegistry] = None,
        action_policy: Optional[ActionPolicy] = None,
    ):
        self.template_registry = template_registry or UITemplateRegistry()
        self.ui_generator = UISpecGenerator(self.template_registry)
        self.feature_generator = FeatureSpecGenerator()
        self.task_generator = TaskSpecGenerator(action_policy=action_policy)
        self.action_generator = ActionSpecGenerator(action_policy=action_policy)

        self.generators: List[SpecGenerator] = [
            self.ui_generator,
            self.feature_generator,
            self.task_generator,
            self.action_generator,
        ]

    def route(self, intent: IntentMatch) -> SpecBundle:
        """Routes an intent across all matching generators and merges into a SpecBundle."""
        bundle_id = f"bundle-composite-{intent.intent_type}-{int(time.time())}"
        composite = SpecBundle(bundle_id=bundle_id, metadata={"intent_type": intent.intent_type})

        for generator in self.generators:
            if generator.can_handle(intent):
                sub_bundle = generator.generate(intent)
                if sub_bundle.ui_spec and not composite.ui_spec:
                    composite.ui_spec = sub_bundle.ui_spec
                if sub_bundle.feature_spec and not composite.feature_spec:
                    composite.feature_spec = sub_bundle.feature_spec
                if sub_bundle.task_spec and not composite.task_spec:
                    composite.task_spec = sub_bundle.task_spec
                if sub_bundle.action_spec and not composite.action_spec:
                    composite.action_spec = sub_bundle.action_spec
                if sub_bundle.action_plan and not composite.action_plan:
                    composite.action_plan = sub_bundle.action_plan

        # Fallback if no specific generator handled it
        if composite.is_empty():
            composite.ui_spec = self.ui_generator.generate(intent).ui_spec

        return composite
