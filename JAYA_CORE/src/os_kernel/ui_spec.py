"""Phase 3A — UI Specification Schema for Dynamic Feature Injection.

This module defines the typed UI specification that JAYA can generate
and the os_kernel can mount as runnable features.

Design goals:
- Serializable to JSON for transport between brain_v2 and os_kernel
- Versioned for forward/backward compatibility
- Validatable before execution
- Supports common UI patterns (windows, panels, forms, lists, charts)
"""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Union


class WidgetType(str, Enum):
    """Supported widget types for dynamic UI generation."""
    WINDOW = "window"
    PANEL = "panel"
    BUTTON = "button"
    LABEL = "label"
    TEXT_INPUT = "text_input"
    TEXTAREA = "textarea"
    SELECT = "select"
    CHECKBOX = "checkbox"
    RADIO_GROUP = "radio_group"
    SLIDER = "slider"
    PROGRESS_BAR = "progress_bar"
    TABLE = "table"
    LIST = "list"
    TREE = "tree"
    TAB_VIEW = "tab_view"
    SPLIT_VIEW = "split_view"
    CHART = "chart"
    CANVAS = "canvas"
    IMAGE = "image"
    ICON = "icon"
    TOOLBAR = "toolbar"
    MENU_BAR = "menu_bar"
    STATUS_BAR = "status_bar"
    DIALOG = "dialog"
    SIDEBAR = "sidebar"
    HEADER = "header"
    FOOTER = "footer"
    FORM = "form"
    GRID = "grid"
    FLEX = "flex"
    SCROLL_VIEW = "scroll_view"
    CUSTOM = "custom"


class LayoutType(str, Enum):
    """Layout strategies for container widgets."""
    ABSOLUTE = "absolute"
    FLEX_ROW = "flex_row"
    FLEX_COL = "flex_col"
    GRID = "grid"
    STACK = "stack"
    FLOW = "flow"
    DOCK = "dock"


class SizeUnit(str, Enum):
    """Size units for dimensions."""
    PX = "px"
    PERCENT = "%"
    FR = "fr"  # Fractional unit (CSS grid)
    AUTO = "auto"
    FIT_CONTENT = "fit_content"


@dataclass
class Dimension:
    """Dimension with unit."""
    value: float
    unit: SizeUnit = SizeUnit.PX

    def to_css(self) -> str:
        if self.unit == SizeUnit.AUTO:
            return "auto"
        if self.unit == SizeUnit.FIT_CONTENT:
            return "fit-content"
        return f"{self.value}{self.unit.value}"

    @classmethod
    def from_css(cls, css: str) -> "Dimension":
        css = css.strip()
        if css == "auto":
            return cls(0, SizeUnit.AUTO)
        if css == "fit-content":
            return cls(0, SizeUnit.FIT_CONTENT)
        if css.endswith("%"):
            return cls(float(css[:-1]), SizeUnit.PERCENT)
        if css.endswith("fr"):
            return cls(float(css[:-2]), SizeUnit.FR)
        if css.endswith("px"):
            return cls(float(css[:-2]), SizeUnit.PX)
        # Default to pixels
        return cls(float(css), SizeUnit.PX)


@dataclass
class Rect:
    """Rectangle with positioned dimensions."""
    x: Dimension = field(default_factory=lambda: Dimension(0, SizeUnit.PX))
    y: Dimension = field(default_factory=lambda: Dimension(0, SizeUnit.PX))
    width: Dimension = field(default_factory=lambda: Dimension(100, SizeUnit.PERCENT))
    height: Dimension = field(default_factory=lambda: Dimension(100, SizeUnit.PERCENT))


@dataclass
class StyleTokens:
    """Design system tokens for consistent styling."""
    # Colors
    color_primary: str = "#0066CC"
    color_secondary: str = "#6C757D"
    color_success: str = "#28A745"
    color_warning: str = "#FFC107"
    color_danger: str = "#DC3545"
    color_background: str = "#FFFFFF"
    color_surface: str = "#F8F9FA"
    color_text: str = "#212529"
    color_text_muted: str = "#6C757D"
    color_border: str = "#DEE2E6"

    # Spacing
    spacing_xs: str = "4px"
    spacing_sm: str = "8px"
    spacing_md: str = "16px"
    spacing_lg: str = "24px"
    spacing_xl: str = "32px"

    # Typography
    font_family: str = "system-ui, -apple-system, sans-serif"
    font_size_sm: str = "12px"
    font_size_md: str = "14px"
    font_size_lg: str = "18px"
    font_size_xl: str = "24px"
    font_weight_normal: int = 400
    font_weight_medium: int = 500
    font_weight_bold: int = 700

    # Borders
    border_radius_sm: str = "4px"
    border_radius_md: str = "8px"
    border_radius_lg: str = "12px"
    border_width: str = "1px"

    # Shadows
    shadow_sm: str = "0 1px 2px rgba(0,0,0,0.05)"
    shadow_md: str = "0 4px 6px rgba(0,0,0,0.1)"
    shadow_lg: str = "0 10px 15px rgba(0,0,0,0.1)"

    # Transitions
    transition_fast: str = "150ms ease"
    transition_normal: str = "250ms ease"
    transition_slow: str = "350ms ease"

    def to_css_vars(self) -> Dict[str, str]:
        """Convert to CSS custom properties."""
        return {f"--jaya-{k.replace('_', '-')}": v for k, v in asdict(self).items()}


@dataclass
class WidgetStyle:
    """Inline style overrides for a widget."""
    # Layout
    display: Optional[str] = None
    position: Optional[str] = None
    flex: Optional[str] = None
    grid_template_columns: Optional[str] = None
    grid_template_rows: Optional[str] = None
    gap: Optional[str] = None
    padding: Optional[str] = None
    margin: Optional[str] = None
    width: Optional[str] = None
    height: Optional[str] = None
    min_width: Optional[str] = None
    min_height: Optional[str] = None
    max_width: Optional[str] = None
    max_height: Optional[str] = None
    align_items: Optional[str] = None
    justify_content: Optional[str] = None

    # Visual
    background_color: Optional[str] = None
    color: Optional[str] = None
    border: Optional[str] = None
    border_radius: Optional[str] = None
    box_shadow: Optional[str] = None
    opacity: Optional[float] = None
    overflow: Optional[str] = None

    # Typography
    font_size: Optional[str] = None
    font_weight: Optional[int] = None
    font_family: Optional[str] = None
    text_align: Optional[str] = None
    line_height: Optional[str] = None

    # Interaction
    cursor: Optional[str] = None
    pointer_events: Optional[str] = None
    user_select: Optional[str] = None

    # Transform/Animation
    transform: Optional[str] = None
    transition: Optional[str] = None
    animation: Optional[str] = None

    # Z-index
    z_index: Optional[int] = None

    def to_css(self) -> Dict[str, str]:
        """Convert to CSS property dict, omitting None values."""
        result = {}
        for k, v in asdict(self).items():
            if v is not None:
                css_key = k.replace('_', '-')
                result[css_key] = str(v)
        return result


@dataclass
class EventHandler:
    """Event handler binding for widget interactions."""
    event: str  # e.g., "click", "change", "submit", "mount", "unmount"
    action: str  # Action identifier (e.g., "jaya:run_task", "jaya:open_dialog")
    payload: Dict[str, Any] = field(default_factory=dict)
    debounce_ms: int = 0
    once: bool = False


@dataclass
class Binding:
    """Data binding for reactive UI."""
    source: str  # e.g., "state.user.name", "props.items", "context.theme"
    target: str  # Widget property to bind (e.g., "text", "value", "visible", "disabled")
    transform: Optional[str] = None  # Optional transform: "uppercase", "lowercase", "json", "date"
    fallback: Any = None


@dataclass
class WidgetSpec:
    """Complete specification for a single widget."""
    id: str
    type: WidgetType
    label: str = ""
    placeholder: str = ""
    value: Any = None
    options: List[Dict[str, Any]] = field(default_factory=list)  # For select, radio_group
    children: List["WidgetSpec"] = field(default_factory=list)
    style: WidgetStyle = field(default_factory=WidgetStyle)
    layout: Optional[LayoutType] = None
    rect: Optional[Rect] = None
    events: List[EventHandler] = field(default_factory=list)
    bindings: List[Binding] = field(default_factory=list)
    visible: bool = True
    enabled: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "placeholder": self.placeholder,
            "value": self.value,
            "options": self.options,
            "children": [c.to_dict() for c in self.children],
            "style": self.style.to_css(),
            "layout": self.layout.value if self.layout else None,
            "rect": asdict(self.rect) if self.rect else None,
            "events": [asdict(e) for e in self.events],
            "bindings": [asdict(b) for b in self.bindings],
            "visible": self.visible,
            "enabled": self.enabled,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WidgetSpec":
        """Deserialize from dictionary."""
        children = [cls.from_dict(c) for c in data.get("children", [])]
        style_data = data.get("style", {})
        style = WidgetStyle(**style_data) if style_data else WidgetStyle()
        rect_data = data.get("rect")
        rect = Rect(**rect_data) if rect_data else None
        events = [EventHandler(**e) for e in data.get("events", [])]
        bindings = [Binding(**b) for b in data.get("bindings", [])]
        layout = LayoutType(data["layout"]) if data.get("layout") else None

        return cls(
            id=data["id"],
            type=WidgetType(data["type"]),
            label=data.get("label", ""),
            placeholder=data.get("placeholder", ""),
            value=data.get("value"),
            options=data.get("options", []),
            children=children,
            style=style,
            layout=layout,
            rect=rect,
            events=events,
            bindings=bindings,
            visible=data.get("visible", True),
            enabled=data.get("enabled", True),
            metadata=data.get("metadata", {}),
        )


@dataclass
class SceneGraph:
    """Root container for a complete UI scene."""
    version: str = "0.1"
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Scene"
    description: str = ""
    root: WidgetSpec = field(default_factory=lambda: WidgetSpec(
        id="root",
        type=WidgetType.WINDOW,
        label="JAYA Feature",
        layout=LayoutType.FLEX_COL,
    ))
    styles: StyleTokens = field(default_factory=StyleTokens)
    global_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "root": self.root.to_dict(),
            "styles": asdict(self.styles),
            "global_state": self.global_state,
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SceneGraph":
        root = WidgetSpec.from_dict(data["root"])
        styles = StyleTokens(**data.get("styles", {}))
        return cls(
            version=data.get("version", "0.1"),
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "Untitled Scene"),
            description=data.get("description", ""),
            root=root,
            styles=styles,
            global_state=data.get("global_state", {}),
            metadata=data.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "SceneGraph":
        return cls.from_dict(json.loads(json_str))


# Convenience factory functions
def create_window(
    title: str,
    width: Union[str, Dimension] = "800px",
    height: Union[str, Dimension] = "600px",
    children: List[WidgetSpec] = None,
) -> WidgetSpec:
    """Create a window widget."""
    if isinstance(width, str):
        width = Dimension.from_css(width)
    if isinstance(height, str):
        height = Dimension.from_css(height)

    return WidgetSpec(
        id=str(uuid.uuid4()),
        type=WidgetType.WINDOW,
        label=title,
        rect=Rect(width=width, height=height),
        layout=LayoutType.FLEX_COL,
        children=children or [],
    )


def create_button(
    label: str,
    on_click: str = None,
    variant: str = "primary",
    **kwargs
) -> WidgetSpec:
    """Create a button widget."""
    btn = WidgetSpec(
        id=str(uuid.uuid4()),
        type=WidgetType.BUTTON,
        label=label,
        metadata={"variant": variant},
    )
    if on_click:
        btn.events.append(EventHandler(
            event="click",
            action=on_click,
        ))
    return btn


def create_panel(
    children: List[WidgetSpec] = None,
    layout: LayoutType = LayoutType.FLEX_COL,
    **kwargs
) -> WidgetSpec:
    """Create a panel/container widget."""
    return WidgetSpec(
        id=str(uuid.uuid4()),
        type=WidgetType.PANEL,
        layout=layout,
        children=children or [],
    )


def create_text_input(
    placeholder: str = "",
    value: str = "",
    on_change: str = None,
    **kwargs
) -> WidgetSpec:
    """Create a text input widget."""
    inp = WidgetSpec(
        id=str(uuid.uuid4()),
        type=WidgetType.TEXT_INPUT,
        placeholder=placeholder,
        value=value,
    )
    if on_change:
        inp.events.append(EventHandler(
            event="change",
            action=on_change,
        ))
    return inp


def create_label(text: str, **kwargs) -> WidgetSpec:
    """Create a label widget."""
    return WidgetSpec(
        id=str(uuid.uuid4()),
        type=WidgetType.LABEL,
        label=text,
    )


def create_table(
    columns: List[Dict[str, str]],
    data: List[Dict[str, Any]] = None,
    on_row_click: str = None,
    **kwargs
) -> WidgetSpec:
    """Create a table widget."""
    tbl = WidgetSpec(
        id=str(uuid.uuid4()),
        type=WidgetType.TABLE,
        metadata={"columns": columns, "data": data or []},
    )
    if on_row_click:
        tbl.events.append(EventHandler(
            event="row_click",
            action=on_row_click,
        ))
    return tbl


# Standard JAYA action prefixes
class JayaActions:
    """Standard action identifiers for JAYA feature communication."""
    RUN_TASK = "jaya:run_task"
    OPEN_DIALOG = "jaya:open_dialog"
    CLOSE_DIALOG = "jaya:close_dialog"
    NAVIGATE = "jaya:navigate"
    NOTIFY = "jaya:notify"
    UPDATE_STATE = "jaya:update_state"
    CALL_API = "jaya:call_api"
    EXECUTE_CODE = "jaya:execute_code"
    SAVE_FILE = "jaya:save_file"
    LOAD_FILE = "jaya:load_file"
    OPEN_URL = "jaya:open_url"
    COPY_TO_CLIPBOARD = "jaya:copy_to_clipboard"
    FOCUS_WIDGET = "jaya:focus_widget"
    SCROLL_TO = "jaya:scroll_to"
