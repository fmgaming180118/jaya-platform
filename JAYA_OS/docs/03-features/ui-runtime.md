# UI Runtime — JAYA_OS

## Overview

The UI Runtime is responsible for rendering and managing the user interface specified by `SceneGraph` (WidgetSpec trees). It consists of:

1. **WindowManager** — Window lifecycle, z-order, focus management
2. **Widget Runtime** — Renders WidgetSpec (button, input, list, chart, etc.)
3. **Event Loop** — Handles user interactions, dispatches to JayaBridge

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            UI RUNTIME                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐         │
│  │  WindowManager  │    │  Widget Runtime │    │   Event Loop    │         │
│  │                 │    │                 │    │                 │         │
│  │ • Create window │    │ • Render widgets│    │ • Mouse/keyboard│         │
│  │ • Z-order       │    │ • Layout engine │    │ • Focus mgmt    │         │
│  │ • Focus         │    │ • Style tokens  │    │ • Drag/resize   │         │
│  │ • Min/max/close │    │ • Data binding  │    │ • IPC dispatch  │         │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘         │
│           │                      │                      │                  │
│           └──────────────────────┼──────────────────────┘                  │
│                                  ▼                                         │
│                    ┌─────────────────────────┐                             │
│                    │      JayaBridge         │                             │
│                    │  (Action Dispatch)      │                             │
│                    └───────────┬─────────────┘                             │
│                                │                                           │
│                                ▼                                           │
│                    ┌─────────────────────────┐                             │
│                    │      JAYA_CORE          │                             │
│                    │  (Brain receives        │                             │
│                    │   action results)       │                             │
│                    └─────────────────────────┘                             │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. WindowManager

### Responsibilities
- Window creation, destruction, lifecycle
- Z-order management (bring to front, send to back)
- Focus tracking (which window has keyboard focus)
- Window state (minimized, maximized, fullscreen, normal)
- Multi-monitor support

### API
```python
class WindowManager:
    def __init__(self, default_width="800px", default_height="600px",
                 theme="light", animations=True, max_windows=20):
        ...

    def create_window(self, spec: WidgetSpec) -> WindowHandle:
        """Create window from WINDOW widget spec."""
        ...

    def destroy_window(self, handle: WindowHandle) -> bool:
        """Destroy window and cleanup resources."""
        ...

    def bring_to_front(self, handle: WindowHandle) -> None:
        """Bring window to top of z-order."""
        ...

    def set_focus(self, handle: WindowHandle) -> None:
        """Set keyboard focus to window."""
        ...

    def get_window_state(self, handle: WindowHandle) -> WindowState:
        """Get current state: normal, minimized, maximized, fullscreen."""
        ...

    def set_window_state(self, handle: WindowHandle, state: WindowState) -> None:
        """Change window state."""
        ...

    def list_windows(self) -> List[WindowHandle]:
        """List all managed windows."""
        ...
```

### WindowHandle
```python
@dataclass
class WindowHandle:
    window_id: str
    title: str
    bounds: Rect              # x, y, width, height
    state: WindowState        # NORMAL, MINIMIZED, MAXIMIZED, FULLSCREEN
    z_order: int
    has_focus: bool
    widget_tree: WidgetSpec   # Root widget spec
```

---

## 2. Widget Runtime

### Responsibilities
- Render widget tree to native UI
- Layout engine (Flexbox, Grid, Absolute)
- Style system (StyleTokens, CSS-like)
- Data binding (reactive updates)
- Event handling (click, change, submit, etc.)

### Widget Types Supported

| Type | Description | Key Props | Events |
|---|---|---|---|
| `WINDOW` | Top-level window | title, width, height, resizable | on_close, on_resize |
| `PANEL` | Container with layout | layout (FLEX_ROW/FLEX_COL/GRID) | - |
| `BUTTON` | Clickable button | label, variant (primary/secondary/danger) | on_click |
| `LABEL` | Text display | text, wrap | - |
| `TEXT_INPUT` | Single-line input | placeholder, type (text/password/number) | on_change, on_submit |
| `TEXTAREA` | Multi-line input | placeholder, rows | on_change |
| `SELECT` | Dropdown select | options[], multiple | on_change |
| `CHECKBOX` | Checkbox | label, checked | on_change |
| `RADIO` | Radio button | label, value, group | on_change |
| `SLIDER` | Range slider | min, max, step, value | on_change |
| `PROGRESS` | Progress bar | value, max, indeterminate | - |
| `LIST` | Selectable list | items[], multi_select | on_select |
| `TABLE` | Data table | columns[], rows[] | on_sort, on_select |
| `CHART` | Data visualization | type (line/bar/pie), data[] | - |
| `IMAGE` | Image display | src, alt, fit | - |
| `TAB` | Tab container | tabs[] | on_change |
| `SPLITTER` | Resizable splitter | orientation, sizes[] | on_resize |

### Layout Engine
```python
class LayoutEngine:
    def layout(self, root: WidgetSpec, container_bounds: Rect) -> Dict[str, Rect]:
        """Compute positions for all widgets."""
        ...

    def flex_layout(self, children: List[WidgetSpec], container: Rect, 
                    direction: LayoutType) -> Dict[str, Rect]:
        """Flexbox-like layout (row/col)."""
        ...

    def grid_layout(self, children: List[WidgetSpec], container: Rect,
                    rows: int, cols: int) -> Dict[str, Rect]:
        """Grid layout."""
        ...
```

### Style System (StyleTokens)
```python
@dataclass
class StyleTokens:
    # Colors
    color_primary: str = "#0066CC"
    color_background: str = "#FFFFFF"
    color_surface: str = "#F5F5F5"
    color_text: str = "#1A1A1A"
    color_text_secondary: str = "#666666"
    color_border: str = "#E0E0E0"
    color_error: str = "#D32F2F"
    color_success: str = "#388E3C"
    
    # Spacing
    spacing_unit: str = "8px"
    spacing_xs: str = "4px"
    spacing_sm: str = "8px"
    spacing_md: str = "16px"
    spacing_lg: str = "24px"
    spacing_xl: str = "32px"
    
    # Typography
    font_family: str = "Inter, system-ui, sans-serif"
    font_size_xs: str = "12px"
    font_size_sm: str = "14px"
    font_size_base: str = "16px"
    font_size_lg: str = "18px"
    font_size_xl: str = "24px"
    font_weight_normal: int = 400
    font_weight_medium: int = 500
    font_weight_bold: int = 700
    
    # Borders & Shadows
    border_radius: str = "8px"
    border_radius_sm: str = "4px"
    border_radius_lg: str = "12px"
    shadow_elevation_1: str = "0 1px 3px rgba(0,0,0,0.1)"
    shadow_elevation_2: str = "0 4px 6px rgba(0,0,0,0.1)"
    shadow_elevation_3: str = "0 10px 20px rgba(0,0,0,0.1)"
    
    # Transitions
    transition_fast: str = "150ms ease"
    transition_normal: str = "250ms ease"
    transition_slow: str = "350ms ease"
```

### Data Binding
```python
@dataclass
class Binding:
    source: str              # Path in state: "user.name"
    target: str              # Widget property: "text"
    transform: Optional[str] = None  # Optional transform: "uppercase", "currency", "date"
    two_way: bool = False    # If True, widget updates propagate back to state
```

---

## 3. Event Loop

### Responsibilities
- Native event capture (mouse, keyboard, touch, window events)
- Hit testing (which widget was clicked)
- Focus management (tab navigation, focus ring)
- Drag & drop
- IPC dispatch to JayaBridge for actions

### Event Flow
```
Native Event (OS)
        │
        ▼
Event Loop (hit test, focus)
        │
        ├─► Widget Event Handler (on_click, on_change, etc.)
        │        │
        │        ▼
        │   JayaBridge.dispatch_action(feature_id, action, payload)
        │        │
        │        ▼
        │   Feature executes, returns result
        │        │
        │        ▼
        │   Update widget state via data binding
        │        │
        │        ▼
        │   Re-render affected widgets
        │
        └─► Window Event (resize, close, focus)
                 │
                 ▼
            WindowManager updates state
```

### API
```python
class EventLoop:
    def __init__(self, window_manager: WindowManager, 
                 widget_runtime: WidgetRuntime,
                 jaya_bridge: JayaBridge):
        ...

    def run(self) -> None:
        """Start the event loop (blocking)."""
        ...

    def stop(self) -> None:
        """Stop the event loop."""
        ...

    def post_event(self, event: Event) -> None:
        """Post event from another thread."""
        ...

    def register_hotkey(self, key: str, callback: Callable) -> None:
        """Register global hotkey."""
        ...
```

---

## Integration with Feature System

### Feature Mounting Creates UI
```python
# When JayaBridge mounts a feature with UI spec:
feature_id = bridge.mount_feature("login_dialog")

# Internally:
# 1. FeatureCompiler compiles SceneGraph → Python module
# 2. JayaBridge loads module, creates FeatureInstance
# 3. WindowManager.create_window(scene.root) → WindowHandle
# 4. WidgetRuntime renders widget tree in window
# 5. EventLoop handles interactions
```

### Action Dispatch from UI
```python
# In compiled feature code (generated by FeatureCompiler):
def handle_submit_login(payload: Dict, state: Dict) -> Dict:
    # Validate
    if not payload.get("username") or not payload.get("password"):
        return {"error": "Username and password required"}
    
    # Update state
    state["last_login_attempt"] = datetime.now().isoformat()
    
    # Return result (sent back to UI via IPC)
    return {"success": True, "redirect": "dashboard"}

# Widget event handler (generated):
def on_submit_click(event):
    payload = collect_form_data(form_widget)
    result = jaya_bridge.dispatch_action(feature_id, "submit_login", payload)
    if result.get("success"):
        navigate_to(result["redirect"])
    else:
        show_error(result["error"])
```

---

## Configuration

```python
@dataclass
class UIRuntimeConfig:
    # Window Manager
    window_default_width: str = "800px"
    window_default_height: str = "600px"
    window_theme: str = "light"          # "light" | "dark" | "auto"
    window_animations: bool = True
    window_max_windows: int = 20
    
    # Widget Runtime
    widget_animation_duration: int = 250  # ms
    widget_focus_ring: bool = True
    widget_tooltip_delay: int = 500       # ms
    
    # Event Loop
    event_loop_poll_interval: int = 16    # ms (~60fps)
    event_loop_max_events_per_frame: int = 100
    
    # Theme
    theme_light: StyleTokens = LIGHT_THEME
    theme_dark: StyleTokens = DARK_THEME
```

---

## Testing

```bash
# Window Manager tests
python -m pytest tests/ -k "window_manager" -v

# Widget Runtime tests
python -m pytest tests/ -k "widget_runtime" -v

# Event Loop tests
python -m pytest tests/ -k "event_loop" -v

# Integration tests
python -m pytest tests/ -k "ui_integration" -v
```

---

## 🔗 Related Docs

- [Runtime Features](../03-features/runtime-features.md) — FeatureCompiler, Registry, Bridge
- [IPC Bridge](../03-features/ipc-bridge.md) — Inter-process communication
- [Sandbox Security](../03-features/sandbox-security.md) — Capability-based permissions
- [Architecture Overview](../02-architecture/overview.md)
- [API Reference](../02-architecture/api-reference.md)