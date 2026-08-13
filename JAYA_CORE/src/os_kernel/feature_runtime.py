"""Phase 3A — Feature Runtime: Base Classes for Feature Execution.

This module provides the runtime environment for executing compiled features
in the os_kernel sandbox. It includes base widget classes, event bus,
and feature lifecycle management.
"""

from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class WidgetEventType(str, Enum):
    """Standard widget event types."""
    MOUNT = "mount"
    UNMOUNT = "unmount"
    CLICK = "click"
    CHANGE = "change"
    INPUT = "input"
    FOCUS = "focus"
    BLUR = "blur"
    SUBMIT = "submit"
    HOVER = "hover"
    KEYDOWN = "keydown"
    KEYUP = "keyup"
    RESIZE = "resize"
    SCROLL = "scroll"
    STATE_CHANGE = "state_change"
    DATA_CHANGE = "data_change"
    ERROR = "error"
    CUSTOM = "custom"


@dataclass
class WidgetEvent:
    """Event emitted by a widget."""
    type: WidgetEventType
    widget_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    bubbles: bool = True  # Whether event bubbles up to parent

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "widget_id": self.widget_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "bubbles": self.bubbles,
        }


class EventBus:
    """Central event bus for widget communication."""

    def __init__(self):
        self._listeners: Dict[WidgetEventType, List[Callable]] = {}
        self._widget_listeners: Dict[str, Dict[WidgetEventType, List[Callable]]] = {}
        self._global_listeners: List[Callable] = []

    def on(self, event_type: WidgetEventType, handler: Callable, widget_id: str = None):
        """Register an event listener."""
        if widget_id:
            if widget_id not in self._widget_listeners:
                self._widget_listeners[widget_id] = {}
            if event_type not in self._widget_listeners[widget_id]:
                self._widget_listeners[widget_id][event_type] = []
            self._widget_listeners[widget_id][event_type].append(handler)
        else:
            if event_type not in self._listeners:
                self._listeners[event_type] = []
            self._listeners[event_type].append(handler)

    def off(self, event_type: WidgetEventType, handler: Callable, widget_id: str = None):
        """Unregister an event listener."""
        if widget_id and widget_id in self._widget_listeners:
            if event_type in self._widget_listeners[widget_id]:
                self._widget_listeners[widget_id][event_type].remove(handler)
        else:
            if event_type in self._listeners:
                self._listeners[event_type].remove(handler)

    def emit(self, event: WidgetEvent):
        """Emit an event to all listeners."""
        # Widget-specific listeners
        if event.widget_id in self._widget_listeners:
            listeners = self._widget_listeners[event.widget_id].get(event.type, [])
            for listener in listeners:
                try:
                    listener(event)
                except Exception as e:
                    print(f"Event listener error: {e}")

        # Global listeners for this event type
        for listener in self._listeners.get(event.type, []):
            try:
                listener(event)
            except Exception as e:
                print(f"Global event listener error: {e}")

        # All-event global listeners
        for listener in self._global_listeners:
            try:
                listener(event)
            except Exception as e:
                print(f"All-event listener error: {e}")

    def on_any(self, handler: Callable):
        """Register a listener for all events."""
        self._global_listeners.append(handler)


class WidgetBase(ABC):
    """Abstract base class for all widgets."""

    def __init__(
        self,
        widget_id: str,
        widget_type: str,
        label: str = "",
        style: Dict[str, str] = None,
        layout: str = None,
        rect: Dict = None,
        visible: bool = True,
        enabled: bool = True,
        metadata: Dict = None,
        event_bus: EventBus = None,
    ):
        self.widget_id = widget_id
        self.widget_type = widget_type
        self.label = label
        self.style = style or {}
        self.layout = layout
        self.rect = rect
        self.visible = visible
        self.enabled = enabled
        self.metadata = metadata or {}
        self._event_bus = event_bus or EventBus()
        self._children: List[WidgetBase] = []
        self._parent: Optional[WidgetBase] = None
        self._state: Dict[str, Any] = {}
        self._refs: Dict[str, Any] = {}  # For DOM refs in real implementation
        self._mounted = False

    @property
    def event_bus(self) -> EventBus:
        return self._event_bus

    @property
    def children(self) -> List[WidgetBase]:
        return self._children

    @property
    def parent(self) -> Optional[WidgetBase]:
        return self._parent

    @property
    def state(self) -> Dict[str, Any]:
        return self._state

    def add_child(self, child: "WidgetBase") -> "WidgetBase":
        """Add a child widget."""
        child._parent = self
        child._event_bus = self._event_bus  # Share event bus
        self._children.append(child)
        if self._mounted:
            child.mount()
        return child

    def remove_child(self, child: "WidgetBase") -> bool:
        """Remove a child widget."""
        if child in self._children:
            child.unmount()
            child._parent = None
            self._children.remove(child)
            return True
        return False

    def mount(self):
        """Mount the widget (called when added to tree)."""
        if self._mounted:
            return
        self._mounted = True
        self._event_bus.emit(WidgetEvent(
            type=WidgetEventType.MOUNT,
            widget_id=self.widget_id,
        ))
        for child in self._children:
            child.mount()

    def unmount(self):
        """Unmount the widget (called when removed from tree)."""
        if not self._mounted:
            return
        self._event_bus.emit(WidgetEvent(
            type=WidgetEventType.UNMOUNT,
            widget_id=self.widget_id,
        ))
        for child in self._children:
            child.unmount()
        self._mounted = False

    def set_state(self, key: str, value: Any) -> None:
        """Set local state and emit change event."""
        old_value = self._state.get(key)
        self._state[key] = value
        self._event_bus.emit(WidgetEvent(
            type=WidgetEventType.STATE_CHANGE,
            widget_id=self.widget_id,
            payload={"key": key, "value": value, "old_value": old_value},
        ))

    def get_state(self, key: str, default: Any = None) -> Any:
        """Get local state value."""
        return self._state.get(key, default)

    def emit(self, event_type: WidgetEventType, payload: Dict[str, Any] = None, bubbles: bool = True):
        """Emit a custom event."""
        self._event_bus.emit(WidgetEvent(
            type=event_type,
            widget_id=self.widget_id,
            payload=payload or {},
            bubbles=bubbles,
        ))

    def on(self, event_type: WidgetEventType, handler: Callable):
        """Register event handler on this widget."""
        self._event_bus.on(event_type, handler, self.widget_id)

    def off(self, event_type: WidgetEventType, handler: Callable):
        """Unregister event handler."""
        self._event_bus.off(event_type, handler, self.widget_id)

    def apply_style(self, style: Dict[str, str]):
        """Apply inline styles."""
        self.style.update(style)
        self.emit(WidgetEventType.CUSTOM, {"action": "style_update", "style": self.style})

    def set_visible(self, visible: bool):
        """Set widget visibility."""
        if self.visible != visible:
            self.visible = visible
            self.emit(WidgetEventType.CUSTOM, {"action": "visibility_change", "visible": visible})

    def set_enabled(self, enabled: bool):
        """Set widget enabled state."""
        if self.enabled != enabled:
            self.enabled = enabled
            self.emit(WidgetEventType.CUSTOM, {"action": "enabled_change", "enabled": enabled})

    def focus(self):
        """Request focus for this widget."""
        self.emit(WidgetEventType.FOCUS, {})

    def blur(self):
        """Remove focus from this widget."""
        self.emit(WidgetEventType.BLUR, {})

    @abstractmethod
    def render(self) -> Dict[str, Any]:
        """Render widget to serializable dict for transport."""
        pass

    @abstractmethod
    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        """Handle a JAYA action dispatched to this widget."""
        pass


class ContainerWidget(WidgetBase):
    """Base class for container widgets that hold children."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._layout_engine = None

    def render(self) -> Dict[str, Any]:
        return {
            "id": self.widget_id,
            "type": self.widget_type,
            "label": self.label,
            "style": self.style,
            "layout": self.layout,
            "rect": self.rect,
            "visible": self.visible,
            "enabled": self.enabled,
            "metadata": self.metadata,
            "children": [c.render() for c in self._children],
            "state": self._state,
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "add_child":
            # Child addition handled at runtime via mount
            return {"added": True}
        elif action == "remove_child":
            child_id = payload.get("child_id")
            for child in self._children:
                if child.widget_id == child_id:
                    self.remove_child(child)
                    return {"removed": True}
            return {"removed": False, "error": "Child not found"}
        elif action == "get_children":
            return {"children": [c.widget_id for c in self._children]}
        return None


class LeafWidget(WidgetBase):
    """Base class for leaf widgets (no children)."""

    def render(self) -> Dict[str, Any]:
        return {
            "id": self.widget_id,
            "type": self.widget_type,
            "label": self.label,
            "style": self.style,
            "layout": self.layout,
            "rect": self.rect,
            "visible": self.visible,
            "enabled": self.enabled,
            "metadata": self.metadata,
            "children": [],
            "state": self._state,
        }


# ============================================================
# Concrete Widget Implementations
# ============================================================

class WindowWidget(ContainerWidget):
    """Top-level window widget."""

    def __init__(self, title: str = "", **kwargs):
        super().__init__(widget_type="window", label=title, **kwargs)
        self.title = title
        self.minimized = False
        self.maximized = False
        self.resizable = kwargs.get("metadata", {}).get("resizable", True)

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "minimize":
            self.minimized = True
            self.emit(WidgetEventType.CUSTOM, {"action": "minimize"})
            return {"minimized": True}
        elif action == "maximize":
            self.maximized = not self.maximized
            self.emit(WidgetEventType.CUSTOM, {"action": "maximize", "maximized": self.maximized})
            return {"maximized": self.maximized}
        elif action == "close":
            self.emit(WidgetEventType.CUSTOM, {"action": "close"})
            return {"closed": True}
        elif action == "set_title":
            self.title = payload.get("title", "")
            self.label = self.title
            return {"title": self.title}
        elif action == "set_size":
            width = payload.get("width")
            height = payload.get("height")
            if width and self.rect:
                self.rect["width"] = width
            if height and self.rect:
                self.rect["height"] = height
            return {"width": width, "height": height}
        return super().handle_action(action, payload)


class PanelWidget(ContainerWidget):
    """Generic panel/container widget."""

    def __init__(self, **kwargs):
        super().__init__(widget_type="panel", **kwargs)


class ButtonWidget(LeafWidget):
    """Button widget."""

    def __init__(self, variant: str = "primary", **kwargs):
        super().__init__(widget_type="button", **kwargs)
        self.variant = variant
        self._pressed = False

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "click":
            self._pressed = not self._pressed
            self.emit(WidgetEventType.CLICK, {"pressed": self._pressed})
            return {"clicked": True, "pressed": self._pressed}
        elif action == "set_variant":
            self.variant = payload.get("variant", "primary")
            return {"variant": self.variant}
        elif action == "set_loading":
            loading = payload.get("loading", False)
            self.set_state("loading", loading)
            return {"loading": loading}
        return None


class LabelWidget(LeafWidget):
    """Label/text widget."""

    def __init__(self, **kwargs):
        super().__init__(widget_type="label", **kwargs)

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "set_text":
            self.label = payload.get("text", "")
            self.emit(WidgetEventType.CUSTOM, {"action": "text_change", "text": self.label})
            return {"text": self.label}
        elif action == "append_text":
            self.label += payload.get("text", "")
            return {"text": self.label}
        return None


class TextInputWidget(LeafWidget):
    """Text input widget."""

    def __init__(self, placeholder: str = "", **kwargs):
        super().__init__(widget_type="text_input", **kwargs)
        self.placeholder = placeholder
        self._value = kwargs.get("value", "")

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, v: str):
        old = self._value
        self._value = v
        self.emit(WidgetEventType.CHANGE, {"value": v, "old_value": old})

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "set_value":
            self.value = payload.get("value", "")
            return {"value": self._value}
        elif action == "get_value":
            return {"value": self._value}
        elif action == "focus":
            self.focus()
            return {"focused": True}
        elif action == "blur":
            self.blur()
            return {"focused": False}
        elif action == "set_placeholder":
            self.placeholder = payload.get("placeholder", "")
            return {"placeholder": self.placeholder}
        return None


class SelectWidget(LeafWidget):
    """Select/dropdown widget."""

    def __init__(self, options: List[Dict] = None, **kwargs):
        super().__init__(widget_type="select", **kwargs)
        self.options = options or []
        self._value = kwargs.get("value")

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "set_options":
            self.options = payload.get("options", [])
            return {"options": self.options}
        elif action == "set_value":
            self._value = payload.get("value")
            self.emit(WidgetEventType.CHANGE, {"value": self._value})
            return {"value": self._value}
        elif action == "get_value":
            return {"value": self._value}
        elif action == "add_option":
            option = payload.get("option")
            if option:
                self.options.append(option)
                return {"added": True}
        return None


class TableWidget(ContainerWidget):
    """Table/data grid widget."""

    def __init__(self, columns: List[Dict] = None, data: List[Dict] = None, **kwargs):
        super().__init__(widget_type="table", **kwargs)
        self.columns = columns or []
        self.data = data or []

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "set_data":
            self.data = payload.get("data", [])
            self.emit(WidgetEventType.DATA_CHANGE, {"count": len(self.data)})
            return {"rows": len(self.data)}
        elif action == "get_data":
            return {"data": self.data}
        elif action == "add_row":
            row = payload.get("row", {})
            self.data.append(row)
            return {"added": True, "index": len(self.data) - 1}
        elif action == "remove_row":
            index = payload.get("index")
            if 0 <= index < len(self.data):
                self.data.pop(index)
                return {"removed": True}
            return {"removed": False}
        elif action == "set_columns":
            self.columns = payload.get("columns", [])
            return {"columns": self.columns}
        return None

    def render(self) -> Dict[str, Any]:
        base = super().render()
        base["metadata"] = {
            **base.get("metadata", {}),
            "columns": self.columns,
            "data": self.data,
        }
        return base


class ProgressBarWidget(LeafWidget):
    """Progress bar widget."""

    def __init__(self, max_value: float = 100, **kwargs):
        super().__init__(widget_type="progress_bar", **kwargs)
        self.max_value = max_value
        self._value = kwargs.get("value", 0)

    @property
    def value(self) -> float:
        return self._value

    @value.setter
    def value(self, v: float):
        self._value = max(0, min(self.max_value, v))
        percent = (self._value / self.max_value) * 100
        self.emit(WidgetEventType.CUSTOM, {"action": "progress", "value": self._value, "percent": percent})

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "set_progress":
            self.value = payload.get("value", 0)
            return {"value": self._value, "percent": (self._value / self.max_value) * 100}
        elif action == "get_progress":
            return {"value": self._value, "percent": (self._value / self.max_value) * 100}
        elif action == "set_max":
            self.max_value = payload.get("max", 100)
            return {"max": self.max_value}
        return None


class DialogWidget(ContainerWidget):
    """Dialog/modal widget."""

    def __init__(self, modal: bool = True, **kwargs):
        super().__init__(widget_type="dialog", **kwargs)
        self.modal = modal
        self._open = False

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Any:
        if action == "open":
            self._open = True
            self.set_visible(True)
            self.emit(WidgetEventType.CUSTOM, {"action": "open"})
            return {"opened": True}
        elif action == "close":
            self._open = False
            self.set_visible(False)
            self.emit(WidgetEventType.CUSTOM, {"action": "close"})
            return {"closed": True}
        elif action == "is_open":
            return {"open": self._open}
        return None


# ============================================================
# Feature Runtime
# ============================================================

@dataclass
class FeatureRuntime:
    """Runtime environment for a mounted feature."""

    feature_id: str
    feature_name: str
    mount_point: str
    root_widget: WidgetBase
    event_bus: EventBus
    config: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=lambda: datetime.now().timestamp())
    status: str = "running"

    async def mount(self, root_widget: WidgetBase, mount_point: str):
        """Mount the feature's widget tree."""
        self.root_widget = root_widget
        self.mount_point = mount_point
        self.root_widget.mount()
        self.status = "running"

    async def unmount(self):
        """Unmount the feature."""
        self.root_widget.unmount()
        self.status = "stopped"

    async def run(self):
        """Run the feature's main loop."""
        # Keep the feature running
        while self.status == "running":
            await asyncio.sleep(1)

    def dispatch(self, action: str, payload: Dict[str, Any] = None) -> Any:
        """Dispatch an action to the feature's root widget."""
        return self.root_widget.handle_action(action, payload or {})

    def update_state(self, updates: Dict[str, Any]):
        """Update feature state."""
        self.state.update(updates)
        # Propagate to widgets via bindings
        self._apply_bindings(self.root_widget)

    def get_state(self) -> Dict[str, Any]:
        """Get current feature state."""
        return self.state.copy()

    def _apply_bindings(self, widget: WidgetBase) -> None:
        """Apply runtime state to every widget that exposes binding support."""
        apply_bindings = getattr(widget, "apply_bindings", None)
        if callable(apply_bindings):
            apply_bindings(self.state)
        for child in widget.children:
            self._apply_bindings(child)

    def emit(self, event_type: WidgetEventType, payload: Dict[str, Any] = None):
        """Emit event from feature root."""
        self.root_widget.emit(event_type, payload)

    def on(self, event_type: WidgetEventType, handler: Callable):
        """Listen for events from feature."""
        self.root_widget.on(event_type, handler)

    def stop(self):
        """Stop the feature."""
        self.status = "stopped"
        self.root_widget.unmount()


# ============================================================
# JAYA Action Dispatcher
# ============================================================

class JayaActionDispatcher:
    """Dispatches JAYA actions to appropriate handlers."""

    def __init__(self, runtime: FeatureRuntime):
        self.runtime = runtime
        self._handlers: Dict[str, Callable] = {}

    def register(self, action: str, handler: Callable):
        """Register an action handler."""
        self._handlers[action] = handler

    def dispatch(self, action: str, payload: Dict[str, Any] = None) -> Any:
        """Dispatch an action."""
        handler = self._handlers.get(action)
        if handler:
            return handler(payload or {})
        # Fall back to widget handling
        return self.runtime.dispatch(action, payload or {})

    def dispatch_to_widget(self, widget_id: str, action: str, payload: Dict[str, Any] = None) -> Any:
        """Dispatch action to specific widget by ID."""
        widget = self._find_widget(self.runtime.root_widget, widget_id)
        if widget:
            return widget.handle_action(action, payload or {})
        return {"error": f"Widget not found: {widget_id}"}

    def _find_widget(self, root: WidgetBase, widget_id: str) -> Optional[WidgetBase]:
        """Find widget by ID in tree."""
        if root.widget_id == widget_id:
            return root
        for child in root.children:
            found = self._find_widget(child, widget_id)
            if found:
                return found
        return None


# ============================================================
# Standard JAYA Actions (built-in)
# ============================================================

def create_standard_dispatcher(runtime: FeatureRuntime) -> JayaActionDispatcher:
    """Create a dispatcher with standard JAYA actions."""
    dispatcher = JayaActionDispatcher(runtime)

    # UI actions
    dispatcher.register("jaya:open_dialog", lambda p: runtime.dispatch("open", p))
    dispatcher.register("jaya:close_dialog", lambda p: runtime.dispatch("close", p))
    dispatcher.register("jaya:notify", lambda p: runtime.emit(WidgetEventType.CUSTOM, {"action": "notify", **p}))
    dispatcher.register("jaya:focus_widget", lambda p: runtime.dispatch_to_widget(p.get("widget_id"), "focus"))
    dispatcher.register("jaya:scroll_to", lambda p: runtime.dispatch_to_widget(p.get("widget_id"), "scroll", p))

    # State actions
    dispatcher.register("jaya:update_state", lambda p: runtime.update_state(p))
    dispatcher.register("jaya:get_state", lambda p: runtime.get_state())

    def unavailable_external_action(action: str) -> Dict[str, Any]:
        return {
            "success": False,
            "error_code": "ACTION_ADAPTER_UNAVAILABLE",
            "action": action,
            "message": "A capability-authorized OS adapter is required",
        }

    # External side effects are never simulated by the in-process UI runtime.
    for action in (
        "jaya:save_file",
        "jaya:load_file",
        "jaya:copy_to_clipboard",
        "jaya:navigate",
        "jaya:open_url",
    ):
        dispatcher.register(
            action,
            lambda _payload, action=action: unavailable_external_action(action),
        )

    return dispatcher


# ============================================================
# Testing / Demo
# ============================================================

if __name__ == "__main__":
    # Demo: Create a simple widget tree
    event_bus = EventBus()

    # Create window
    window = WindowWidget(
        widget_id="main-window",
        title="JAYA Demo",
        style={"width": "800px", "height": "600px"},
        event_bus=event_bus,
    )

    # Create panel
    panel = PanelWidget(
        widget_id="main-panel",
        layout="flex_col",
        style={"padding": "20px", "gap": "16px"},
        event_bus=event_bus,
    )

    # Add label
    label = LabelWidget(
        widget_id="welcome-label",
        label="Welcome to JAYA!",
        style={"font_size": "24px", "font_weight": "600"},
        event_bus=event_bus,
    )

    # Add button
    button = ButtonWidget(
        widget_id="action-btn",
        label="Click Me",
        variant="primary",
        event_bus=event_bus,
    )

    # Add input
    input_widget = TextInputWidget(
        widget_id="name-input",
        placeholder="Enter your name",
        event_bus=event_bus,
    )

    # Build tree
    panel.add_child(label)
    panel.add_child(input_widget)
    panel.add_child(button)
    window.add_child(panel)

    # Mount
    window.mount()

    # Test event handling
    def on_click(event):
        print(f"Button clicked! Event: {event.to_dict()}")

    button.on(WidgetEventType.CLICK, on_click)

    # Simulate click
    button.handle_action("click", {})

    # Test state
    input_widget.handle_action("set_value", {"value": "JAYA User"})
    print(f"Input value: {input_widget.value}")

    # Render
    print("\nRendered tree:")
    print(json.dumps(window.render(), indent=2))

    # Unmount
    window.unmount()
    print("\nDemo complete!")
