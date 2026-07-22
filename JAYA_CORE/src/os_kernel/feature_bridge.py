"""Phase 3A — Feature Bridge: brain_v2 ↔ os_kernel Communication.

This module provides the communication layer between the resident AI (brain_v2)
and the OS kernel (os_kernel) for dynamic feature injection.

The bridge allows brain_v2 to:
- Request feature compilation from intent
- Mount/unmount features
- Dispatch actions to features
- Receive events from features
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from enum import Enum

from src.os_kernel.ui_spec import SceneGraph, WidgetSpec, WidgetType, LayoutType
from src.os_kernel.feature_compiler import FeatureCompiler, compile_scene_to_feature
from src.os_kernel.feature_registry import (
    FeatureRegistry,
    FeatureManifest,
    FeatureInstance,
    FeatureStatus,
    FeaturePermission,
    get_feature_registry,
)


class BridgeAction(str, Enum):
    """Standard JAYA bridge actions."""
    # Feature lifecycle
    COMPILE_FEATURE = "jaya:compile_feature"
    MOUNT_FEATURE = "jaya:mount_feature"
    UNMOUNT_FEATURE = "jaya:unmount_feature"
    LIST_FEATURES = "jaya:list_features"
    GET_FEATURE_STATUS = "jaya:get_feature_status"

    # Feature interaction
    DISPATCH_ACTION = "jaya:dispatch_action"
    UPDATE_FEATURE_STATE = "jaya:update_feature_state"
    GET_FEATURE_STATE = "jaya:get_feature_state"

    # UI operations
    OPEN_DIALOG = "jaya:open_dialog"
    CLOSE_DIALOG = "jaya:close_dialog"
    NOTIFY = "jaya:notify"
    NAVIGATE = "jaya:navigate"

    # System operations
    RUN_TASK = "jaya:run_task"
    CALL_API = "jaya:call_api"
    EXECUTE_CODE = "jaya:execute_code"
    SAVE_FILE = "jaya:save_file"
    LOAD_FILE = "jaya:load_file"
    OPEN_URL = "jaya:open_url"
    COPY_TO_CLIPBOARD = "jaya:copy_to_clipboard"

    # Feature-specific
    FOCUS_WIDGET = "jaya:focus_widget"
    SCROLL_TO = "jaya:scroll_to"
    UPDATE_WIDGET = "jaya:update_widget"


@dataclass
class BridgeRequest:
    """Request from brain_v2 to os_kernel."""
    action: BridgeAction
    payload: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    correlation_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BridgeRequest":
        return cls(
            action=BridgeAction(data["action"]),
            payload=data.get("payload", {}),
            request_id=data.get("request_id", str(uuid.uuid4())),
            timestamp=data.get("timestamp", datetime.now().timestamp()),
            correlation_id=data.get("correlation_id"),
        )


@dataclass
class BridgeResponse:
    """Response from os_kernel to brain_v2."""
    request_id: str
    success: bool
    data: Any = None
    error: str = ""
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def success_response(cls, request_id: str, data: Any = None) -> "BridgeResponse":
        return cls(request_id=request_id, success=True, data=data)

    @classmethod
    def error_response(cls, request_id: str, error: str) -> "BridgeResponse":
        return cls(request_id=request_id, success=False, error=error)


@dataclass
class FeatureEvent:
    """Event emitted by a feature."""
    feature_id: str
    event_type: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class JayaBridge:
    """Main bridge for brain_v2 ↔ os_kernel communication."""

    def __init__(self, features_dir: str = None, sandbox_mode: bool = True):
        self.registry = get_feature_registry(features_dir)
        self.registry._sandbox_mode = sandbox_mode
        self._action_handlers: Dict[BridgeAction, Callable] = {}
        self._event_listeners: Dict[str, List[Callable]] = {}
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._running = False

        # Register default handlers
        self._register_default_handlers()

    def _register_default_handlers(self):
        """Register built-in action handlers."""
        self._action_handlers[BridgeAction.COMPILE_FEATURE] = self._handle_compile_feature
        self._action_handlers[BridgeAction.MOUNT_FEATURE] = self._handle_mount_feature
        self._action_handlers[BridgeAction.UNMOUNT_FEATURE] = self._handle_unmount_feature
        self._action_handlers[BridgeAction.LIST_FEATURES] = self._handle_list_features
        self._action_handlers[BridgeAction.GET_FEATURE_STATUS] = self._handle_get_feature_status
        self._action_handlers[BridgeAction.DISPATCH_ACTION] = self._handle_dispatch_action
        self._action_handlers[BridgeAction.UPDATE_FEATURE_STATE] = self._handle_update_feature_state
        self._action_handlers[BridgeAction.GET_FEATURE_STATE] = self._handle_get_feature_state
        self._action_handlers[BridgeAction.OPEN_DIALOG] = self._handle_open_dialog
        self._action_handlers[BridgeAction.CLOSE_DIALOG] = self._handle_close_dialog
        self._action_handlers[BridgeAction.NOTIFY] = self._handle_notify
        self._action_handlers[BridgeAction.RUN_TASK] = self._handle_run_task

    async def dispatch(self, action: BridgeAction, payload: Dict[str, Any] = None) -> BridgeResponse:
        """Dispatch an action and wait for response."""
        request = BridgeRequest(action=action, payload=payload or {})
        return await self._process_request(request)

    async def _process_request(self, request: BridgeRequest) -> BridgeResponse:
        """Process a bridge request."""
        handler = self._action_handlers.get(request.action)
        if not handler:
            return BridgeResponse.error_response(request.request_id, f"No handler for action: {request.action}")

        try:
            if asyncio.iscoroutinefunction(handler):
                result = await handler(request.payload)
            else:
                result = handler(request.payload)
            return BridgeResponse.success_response(request.request_id, result)
        except Exception as e:
            return BridgeResponse.error_response(request.request_id, str(e))

    # ============================================================
    # Feature Lifecycle Handlers
    # ============================================================

    def _handle_compile_feature(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Compile a SceneGraph to a feature package."""
        scene_data = payload.get("scene")
        feature_name = payload.get("feature_name")
        output_dir = payload.get("output_dir")

        if not scene_data:
            raise ValueError("Missing 'scene' in payload")

        # Parse scene
        if isinstance(scene_data, str):
            scene = SceneGraph.from_json(scene_data)
        elif isinstance(scene_data, dict):
            scene = SceneGraph.from_dict(scene_data)
        else:
            scene = scene_data

        # Compile
        output_path = compile_scene_to_feature(scene, output_dir or "./features", feature_name)

        return {
            "success": True,
            "feature_path": str(output_path),
            "feature_name": output_path.name,
            "manifest": str(output_path / "manifest.json"),
        }

    def _handle_mount_feature(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Mount a feature at a mount point."""
        feature_id = payload.get("feature_id")
        mount_point = payload.get("mount_point", "body")
        config = payload.get("config", {})
        jaya_bridge = payload.get("jaya_bridge")  # Passed from brain_v2

        if not feature_id:
            raise ValueError("Missing 'feature_id' in payload")

        # Discover features if not already done
        if not self.registry._discovered:
            self.registry.discover_features()

        instance = self.registry.mount_feature(
            feature_id=feature_id,
            mount_point=mount_point,
            config=config,
            jaya_bridge=jaya_bridge,
        )

        # Start feature if it has a run method
        if instance.entry_point:
            instance.status = FeatureStatus.RUNNING
            # Run in background
            asyncio.create_task(self._run_feature(instance))

        return {
            "success": True,
            "feature_id": feature_id,
            "mount_point": mount_point,
            "status": instance.status.value,
        }

    def _handle_unmount_feature(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Unmount a feature."""
        feature_id = payload.get("feature_id")
        if not feature_id:
            raise ValueError("Missing 'feature_id' in payload")

        success = self.registry.unmount_feature(feature_id)
        return {"success": success, "feature_id": feature_id}

    def _handle_list_features(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """List all discovered features."""
        features = self.registry.list_discovered()
        return {
            "features": [f.to_dict() for f in features],
            "count": len(features),
        }

    def _handle_get_feature_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get status of a specific feature."""
        feature_id = payload.get("feature_id")
        if not feature_id:
            raise ValueError("Missing 'feature_id' in payload")

        instance = self.registry.get_instance(feature_id)
        if not instance:
            return {"success": False, "error": "Feature not mounted"}

        return {
            "success": True,
            "status": instance.to_dict(),
        }

    async def _run_feature(self, instance: FeatureInstance):
        """Run a feature's entry point."""
        try:
            if asyncio.iscoroutinefunction(instance.entry_point):
                await instance.entry_point(self, instance.config)
            else:
                instance.entry_point(self, instance.config)
        except Exception as e:
            instance.status = FeatureStatus.ERROR
            instance.error = str(e)
            self._emit_event(FeatureEvent(
                feature_id=instance.manifest.id,
                event_type="error",
                payload={"error": str(e)},
            ))

    # ============================================================
    # Feature Interaction Handlers
    # ============================================================

    def _handle_dispatch_action(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch an action to a specific feature."""
        feature_id = payload.get("feature_id")
        action = payload.get("action")
        action_payload = payload.get("payload", {})

        if not feature_id or not action:
            raise ValueError("Missing 'feature_id' or 'action' in payload")

        instance = self.registry.get_instance(feature_id)
        if not instance:
            raise ValueError(f"Feature not mounted: {feature_id}")

        # Check if feature module has a dispatch handler
        if hasattr(instance.module, "dispatch"):
            result = instance.module.dispatch(action, action_payload)
            return {"success": True, "result": result}

        return {"success": False, "error": "Feature does not support action dispatch"}

    def _handle_update_feature_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Update feature state."""
        feature_id = payload.get("feature_id")
        state_updates = payload.get("state", {})

        if not feature_id:
            raise ValueError("Missing 'feature_id' in payload")

        instance = self.registry.get_instance(feature_id)
        if not instance:
            raise ValueError(f"Feature not mounted: {feature_id}")

        instance.state.update(state_updates)

        # Notify feature if it has a state handler
        if hasattr(instance.module, "on_state_change"):
            instance.module.on_state_change(instance.state)

        return {"success": True, "state": instance.state}

    def _handle_get_feature_state(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Get feature state."""
        feature_id = payload.get("feature_id")
        if not feature_id:
            raise ValueError("Missing 'feature_id' in payload")

        instance = self.registry.get_instance(feature_id)
        if not instance:
            raise ValueError(f"Feature not mounted: {feature_id}")

        return {"success": True, "state": instance.state}

    # ============================================================
    # UI Operation Handlers
    # ============================================================

    def _handle_open_dialog(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Open a dialog (delegates to UI layer)."""
        # This would integrate with the actual UI framework
        dialog_id = str(uuid.uuid4())
        return {
            "success": True,
            "dialog_id": dialog_id,
            "message": "Dialog open requested",
        }

    def _handle_close_dialog(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Close a dialog."""
        dialog_id = payload.get("dialog_id")
        return {"success": True, "dialog_id": dialog_id}

    def _handle_notify(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Show a notification."""
        message = payload.get("message", "")
        level = payload.get("level", "info")  # info, warning, error, success
        duration = payload.get("duration", 5000)

        self._emit_event(FeatureEvent(
            feature_id="system",
            event_type="notification",
            payload={"message": message, "level": level, "duration": duration},
        ))

        return {"success": True}

    def _handle_run_task(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Run a background task."""
        task_code = payload.get("code", "")
        task_label = payload.get("label", "TASK")

        # This would integrate with the twin/task system
        task_id = str(uuid.uuid4())

        return {
            "success": True,
            "task_id": task_id,
            "message": f"Task '{task_label}' queued",
        }

    # ============================================================
    # Event System
    # ============================================================

    def on(self, event_type: str, handler: Callable):
        """Register an event listener."""
        if event_type not in self._event_listeners:
            self._event_listeners[event_type] = []
        self._event_listeners[event_type].append(handler)

    def off(self, event_type: str, handler: Callable):
        """Unregister an event listener."""
        if event_type in self._event_listeners:
            self._event_listeners[event_type].remove(handler)

    def _emit_event(self, event: FeatureEvent):
        """Emit an event to all listeners."""
        listeners = self._event_listeners.get(event.event_type, [])
        for listener in listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    asyncio.create_task(listener(event))
                else:
                    listener(event)
            except Exception as e:
                print(f"Event listener error: {e}")

    # ============================================================
    # Intent-to-Feature Compilation (Brain_v2 Integration)
    # ============================================================

    async def compile_intent_to_feature(
        self,
        intent: str,
        feature_name: str = None,
        context: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Compile a natural language intent into a feature.

        This is the main entry point for brain_v2 to create features from intent.
        """
        context = context or {}

        # Use LinguaLogica to parse intent into UI spec
        # This would integrate with brain_v2's intent_engine and lingua_logica
        scene = await self._intent_to_scene(intent, context)

        # Compile to feature
        feature_name = feature_name or self._slugify(intent)
        output_path = compile_scene_to_feature(scene, "./features", feature_name)

        return {
            "success": True,
            "feature_path": str(output_path),
            "feature_name": output_path.name,
            "scene": scene.to_dict(),
        }

    async def _intent_to_scene(self, intent: str, context: Dict) -> SceneGraph:
        """Convert natural language intent to SceneGraph.

        This is a simplified version - in production, this would use
        brain_v2's IntentEngine + LinguaLogica + LLM.
        """
        intent_lower = intent.lower()

        # Simple pattern matching for demo
        if "login" in intent_lower or "sign in" in intent_lower:
            return self._create_login_scene()
        elif "dashboard" in intent_lower:
            return self._create_dashboard_scene()
        elif "settings" in intent_lower or "preferences" in intent_lower:
            return self._create_settings_scene()
        elif "chat" in intent_lower or "conversation" in intent_lower:
            return self._create_chat_scene()
        elif "file" in intent_lower and ("explorer" in intent_lower or "manager" in intent_lower):
            return self._create_file_explorer_scene()
        else:
            # Generic fallback
            return self._create_generic_scene(intent)

    def _create_login_scene(self) -> SceneGraph:
        from src.os_kernel.ui_spec import (
            create_window, create_panel, create_label, create_text_input, create_button,
            LayoutType, WidgetType
        )
        return SceneGraph(
            name="Login Dialog",
            description="User authentication dialog",
            root=create_window(
                title="JAYA Login",
                width="400px",
                height="350px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        children=[
                            create_label("Welcome to JAYA", style={"font_size": "24px", "font_weight": "600", "margin_bottom": "24px"}),
                            create_text_input(placeholder="Username or Email", on_change="jaya:update_state"),
                            create_text_input(placeholder="Password", value="", on_change="jaya:update_state"),
                            create_button(label="Sign In", on_click="jaya:run_task", variant="primary"),
                            create_label("Forgot password?", style={"color": "#0066CC", "cursor": "pointer", "margin_top": "16px"}),
                        ],
                    ),
                ],
            ),
        )

    def _create_dashboard_scene(self) -> SceneGraph:
        from src.os_kernel.ui_spec import (
            create_window, create_panel, create_label, create_button,
            LayoutType, WidgetType, WidgetStyle, Dimension, SizeUnit
        )
        return SceneGraph(
            name="Dashboard",
            description="Main dashboard with metrics and quick actions",
            root=create_window(
                title="JAYA Dashboard",
                width="1200px",
                height="800px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        children=[
                            # Header
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style=WidgetStyle(padding="16px", border_bottom="1px solid var(--jaya-color-border)"),
                                children=[
                                    create_label("JAYA Dashboard", style=WidgetStyle(font_size="24px", font_weight="600")),
                                    create_panel(layout=LayoutType.FLEX_ROW, style=WidgetStyle(margin_left="auto", gap="8px"), children=[
                                        create_button(label="New Task", on_click="jaya:run_task"),
                                        create_button(label="Settings", variant="secondary", on_click="jaya:open_dialog"),
                                    ]),
                                ],
                            ),
                            # Main content
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style=WidgetStyle(flex="1", padding="24px", gap="24px"),
                                children=[
                                    # Sidebar
                                    create_panel(
                                        layout=LayoutType.FLEX_COL,
                                        style=WidgetStyle(width="280px", background_color="var(--jaya-color-surface)", border_radius="8px", padding="16px"),
                                        children=[
                                            create_label("Navigation", style=WidgetStyle(font_weight="600", margin_bottom="16px")),
                                            create_button(label="Overview", variant="secondary"),
                                            create_button(label="Tasks", variant="secondary"),
                                            create_button(label="Analytics", variant="secondary"),
                                            create_button(label="Integrations", variant="secondary"),
                                        ],
                                    ),
                                    # Main area
                                    create_panel(
                                        layout=LayoutType.FLEX_COL,
                                        style=WidgetStyle(flex="1", gap="16px"),
                                        children=[
                                            # Stats row
                                            create_panel(
                                                layout=LayoutType.FLEX_ROW,
                                                style=WidgetStyle(gap="16px"),
                                                children=[
                                                    create_panel(style=WidgetStyle(flex="1", background_color="var(--jaya-color-surface)", border_radius="8px", padding="24px"), children=[
                                                        create_label("Total Tasks", style=WidgetStyle(font_size="14px", color="var(--jaya-color-text-muted)")),
                                                        create_label("1,234", style=WidgetStyle(font_size="32px", font_weight="600")),
                                                    ]),
                                                    create_panel(style=WidgetStyle(flex="1", background_color="var(--jaya-color-surface)", border_radius="8px", padding="24px"), children=[
                                                        create_label("Completed", style=WidgetStyle(font_size="14px", color="var(--jaya-color-text-muted)")),
                                                        create_label("987", style=WidgetStyle(font_size="32px", font_weight="600", color="var(--jaya-color-success)")),
                                                    ]),
                                                    create_panel(style=WidgetStyle(flex="1", background_color="var(--jaya-color-surface)", border_radius="8px", padding="24px"), children=[
                                                        create_label("In Progress", style=WidgetStyle(font_size="14px", color="var(--jaya-color-text-muted)")),
                                                        create_label("156", style=WidgetStyle(font_size="32px", font_weight="600", color="var(--jaya-color-warning)")),
                                                    ]),
                                                    create_panel(style=WidgetStyle(flex="1", background_color="var(--jaya-color-surface)", border_radius="8px", padding="24px"), children=[
                                                        create_label("Overdue", style=WidgetStyle(font_size="14px", color="var(--jaya-color-text-muted)")),
                                                        create_label("12", style=WidgetStyle(font_size="32px", font_weight="600", color="var(--jaya-color-danger)")),
                                                    ]),
                                                ],
                                            ),
                                            # Chart placeholder
                                            create_panel(
                                                style=WidgetStyle(flex="1", background_color="var(--jaya-color-surface)", border_radius="8px", padding="24px"),
                                                children=[
                                                    create_label("Activity Chart", style=WidgetStyle(font_weight="600", margin_bottom="16px")),
                                                    create_label("[Chart would render here]", style=WidgetStyle(color="var(--jaya-color-text-muted)", text_align="center")),
                                                ],
                                            ),
                                        ],
                                    ),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _create_settings_scene(self) -> SceneGraph:
        from src.os_kernel.ui_spec import (
            create_window, create_panel, create_label, create_text_input, create_button, create_select,
            LayoutType, WidgetType, WidgetStyle
        )
        return SceneGraph(
            name="Settings",
            description="Application settings and preferences",
            root=create_window(
                title="Settings",
                width="600px",
                height="700px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style=WidgetStyle(padding="24px", gap="24px"),
                        children=[
                            create_label("Settings", style=WidgetStyle(font_size="24px", font_weight="600")),
                            # General
                            create_panel(
                                style=WidgetStyle(background_color="var(--jaya-color-surface)", border_radius="8px", padding="24px"),
                                children=[
                                    create_label("General", style=WidgetStyle(font_weight="600", margin_bottom="16px")),
                                    create_text_input(placeholder="Display Name", value="JAYA User"),
                                    create_select(options=[
                                        {"value": "en", "label": "English"},
                                        {"value": "id", "label": "Indonesian"},
                                    ], placeholder="Language"),
                                    create_select(options=[
                                        {"value": "light", "label": "Light"},
                                        {"value": "dark", "label": "Dark"},
                                        {"value": "system", "label": "System"},
                                    ], placeholder="Theme"),
                                ],
                            ),
                            # Privacy
                            create_panel(
                                style=WidgetStyle(background_color="var(--jaya-color-surface)", border_radius="8px", padding="24px"),
                                children=[
                                    create_label("Privacy & Security", style=WidgetStyle(font_weight="600", margin_bottom="16px")),
                                    create_label("Data Collection", style=WidgetStyle(font_weight="500", margin_top="16px")),
                                    create_label("Allow anonymous usage analytics"),
                                    create_label("Crash Reporting", style=WidgetStyle(font_weight="500", margin_top="16px")),
                                    create_label("Automatically send crash reports"),
                                ],
                            ),
                            # Actions
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style=WidgetStyle(justify_content="flex-end", gap="12px"),
                                children=[
                                    create_button(label="Cancel", variant="secondary", on_click="jaya:close_dialog"),
                                    create_button(label="Save Changes", variant="primary", on_click="jaya:run_task"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _create_chat_scene(self) -> SceneGraph:
        from src.os_kernel.ui_spec import (
            create_window, create_panel, create_label, create_text_input, create_button,
            LayoutType, WidgetType, WidgetStyle
        )
        return SceneGraph(
            name="Chat",
            description="Chat interface for JAYA conversation",
            root=create_window(
                title="JAYA Chat",
                width="500px",
                height="700px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        children=[
                            # Messages area
                            create_panel(
                                style=WidgetStyle(flex="1", overflow_y="auto", padding="16px", gap="12px"),
                                children=[
                                    create_panel(
                                        style=WidgetStyle(background_color="var(--jaya-color-surface)", border_radius="12px", padding="12px 16px", max_width="80%", align_self="flex-start"),
                                        children=[
                                            create_label("Hello! How can I help you today?", style=WidgetStyle(color="var(--jaya-color-text)")),
                                        ],
                                    ),
                                ],
                            ),
                            # Input area
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style=WidgetStyle(padding="16px", border_top="1px solid var(--jaya-color-border)", gap="8px"),
                                children=[
                                    create_text_input(
                                        placeholder="Type a message...",
                                        style=WidgetStyle(flex="1"),
                                        on_change="jaya:update_state",
                                    ),
                                    create_button(label="Send", variant="primary", on_click="jaya:run_task"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _create_file_explorer_scene(self) -> SceneGraph:
        from src.os_kernel.ui_spec import (
            create_window, create_panel, create_label, create_button, create_tree,
            LayoutType, WidgetType, WidgetStyle
        )
        return SceneGraph(
            name="File Explorer",
            description="File system browser",
            root=create_window(
                title="File Explorer",
                width="400px",
                height="600px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        children=[
                            # Toolbar
                            create_panel(
                                layout=LayoutType.FLEX_ROW,
                                style=WidgetStyle(padding="8px", border_bottom="1px solid var(--jaya-color-border)", gap="8px"),
                                children=[
                                    create_button(label="↑", variant="secondary", on_click="jaya:run_task"),
                                    create_button(label="🔄", variant="secondary", on_click="jaya:run_task"),
                                    create_button(label="🏠", variant="secondary", on_click="jaya:run_task"),
                                    create_panel(style=WidgetStyle(flex="1")),
                                    create_button(label="New Folder", variant="secondary", on_click="jaya:run_task"),
                                ],
                            ),
                            # Path bar
                            create_panel(
                                style=WidgetStyle(padding="8px 12px", background_color="var(--jaya-color-surface)", border_bottom="1px solid var(--jaya-color-border)"),
                                children=[
                                    create_label("📁 Home > Documents > Projects", style=WidgetStyle(font_family="monospace", font_size="13px")),
                                ],
                            ),
                            # File tree
                            create_panel(
                                style=WidgetStyle(flex="1", overflow_y="auto", padding="8px"),
                                children=[
                                    create_label("📁 Documents", style=WidgetStyle(font_weight="500")),
                                    create_label("📁 Downloads"),
                                    create_label("📁 Pictures"),
                                    create_label("📄 README.md"),
                                    create_label("📄 config.yaml"),
                                    create_label("📁 Projects"),
                                ],
                            ),
                        ],
                    ),
                ],
            ),
        )

    def _create_generic_scene(self, intent: str) -> SceneGraph:
        from src.os_kernel.ui_spec import (
            create_window, create_panel, create_label, create_button,
            LayoutType, WidgetType, WidgetStyle
        )
        return SceneGraph(
            name=f"Feature: {intent[:50]}",
            description=f"Auto-generated feature for: {intent}",
            root=create_window(
                title=f"JAYA Feature: {intent[:40]}",
                width="600px",
                height="400px",
                children=[
                    create_panel(
                        layout=LayoutType.FLEX_COL,
                        style=WidgetStyle(padding="24px", gap="16px", align_items="center"),
                        children=[
                            create_label(f"Feature for: {intent}", style=WidgetStyle(font_size="18px", font_weight="600", text_align="center")),
                            create_label("This feature was auto-generated from your intent.", style=WidgetStyle(color="var(--jaya-color-text-muted)", text_align="center")),
                            create_button(label="Close", variant="secondary", on_click="jaya:close_dialog"),
                        ],
                    ),
                ],
            ),
        )

    def _slugify(self, text: str) -> str:
        import re
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        text = re.sub(r'[\s-]+', '_', text)
        return text[:50].strip('_')


# Convenience function for brain_v2 integration
async def create_feature_from_intent(
    bridge: JayaBridge,
    intent: str,
    feature_name: str = None,
    context: Dict = None,
) -> Dict[str, Any]:
    """High-level function for brain_v2 to create features from intent."""
    return await bridge.compile_intent_to_feature(intent, feature_name, context)


# Example usage
if __name__ == "__main__":
    async def demo():
        bridge = JayaBridge(features_dir="./test_features")

        # Discover existing features
        features = bridge.registry.discover_features()
        print(f"Discovered {len(features)} features")

        # Compile intent to feature
        result = await bridge.compile_intent_to_feature("Create a login dialog with username and password fields")
        print(f"Compiled feature: {result}")

        # Mount feature
        if result.get("success"):
            mount_result = await bridge.dispatch(BridgeAction.MOUNT_FEATURE, {
                "feature_id": result["feature_name"],
                "mount_point": "dialog-root",
            })
            print(f"Mount result: {mount_result}")

    asyncio.run(demo())