# Phase OS-2: Window Manager + Widget Runtime

## Objective
Implement native UI rendering: WindowManager, Widget Runtime, Layout Engine, Style System, Event Loop.

---

## Scope
- **In scope**: WindowManager (Win32, X11), Widget Runtime (16 types), Layout Engine, Style System, Event Loop
- **Out of scope**: IPC Bridge (OS-3), Hardware Abstraction (OS-4)

---

## Prerequisites
- ✅ OS-1 complete (standalone JAYA_OS package)
- ✅ UI Spec (SceneGraph, WidgetSpec, StyleTokens) stable
- ✅ Phase 3C tests passing

---

## Deliverables

| # | Deliverable | File/Location | Status |
|---|---|---|---|
| 1 | WindowManager (Win32 backend) | `src/jaya_os/window_manager.py` | 🔄 Planned |
| 2 | WindowManager (X11 backend) | `src/jaya_os/window_manager_x11.py` | 🔄 Planned |
| 3 | Widget Runtime (16 widget types) | `src/jaya_os/widget_runtime.py` | 🔄 Planned |
| 4 | Layout Engine (Flexbox + Grid) | `src/jaya_os/layout_engine.py` | 🔄 Planned |
| 5 | Style System (StyleTokens) | `src/jaya_os/style_tokens.py` | 🔄 Planned |
| 4 | Event Loop | `src/jaya_os/event_loop.py` | 🔄 Planned |
| 5 | Data Binding | `src/jaya_os/data_binding.py` | 🔄 Planned |
| 6 | Integration with JayaBridge | `src/jaya_os/bridge_integration.py` | 🔄 Planned |
| 7 | Unit tests | `tests/test_window_manager.py`, etc. | 🔄 Planned |
| 8 | Integration tests | `tests/test_ui_integration.py` | 🔄 Planned |

---

## Technical Implementation

### 2.1 WindowManager

#### Backend Strategy
```python
# src/jaya_os/window_manager.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional
from jaya_os.ui_spec import WidgetSpec, Rect

@dataclass
class WindowHandle:
    window_id: str
    title: str
    bounds: Rect
    state: "WindowState"  # NORMAL, MINIMIZED, MAXIMIZED, FULLSCREEN
    z_order: int
    has_focus: bool
    widget_tree: WidgetSpec

class WindowState:
    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"
    FULLSCREEN = "fullscreen"

class WindowManagerBackend(ABC):
    @abstractmethod
    def create_window(self, spec: WidgetSpec) -> WindowHandle: ...
    @abstractmethod
    def destroy_window(self, handle: WindowHandle) -> bool: ...
    @abstractmethod
    def bring_to_front(self, handle: WindowHandle) -> None: ...
    @abstractmethod
    def set_focus(self, handle: WindowHandle) -> None: ...
    @abstractmethod
    def get_window_state(self, handle: WindowHandle) -> WindowState: ...
    @abstractmethod
    def set_window_state(self, handle: WindowHandle, state: WindowState) -> None: ...
    @abstractmethod
    def list_windows(self) -> List[WindowHandle]: ...

class WindowManager:
    def __init__(self, config: "WindowManagerConfig"):
        self.backend = self._create_backend()
        self.windows: dict[str, WindowHandle] = {}
        self._z_order = 0
    
    def _create_backend(self) -> WindowManagerBackend:
        import sys
        if sys.platform == "win32":
            from jaya_os.window_manager_win32 import Win32Backend
            return Win32Backend()
        elif sys.platform.startswith("linux"):
            from jaya_os.window_manager_x11 import X11Backend
            return X11Backend()
        else:
            raise NotImplementedError(f"Platform {sys.platform} not supported")
    
    def create_window(self, spec: WidgetSpec) -> WindowHandle:
        handle = self.backend.create_window(spec)
        handle.z_order = self._z_order
        self._z_order += 1
        self.windows[handle.window_id] = handle
        return handle
    
    def destroy_window(self, handle: WindowHandle) -> bool:
        result = self.backend.destroy_window(handle)
        if result:
            self.windows.pop(handle.window_id, None)
        return result
    
    # ... other methods delegate to backend
```

#### Win32 Backend (`window_manager_win32.py`)
```python
# src/jaya_os/window_manager_win32.py
import ctypes
from ctypes import wintypes
from jaya_os.window_manager import WindowManagerBackend, WindowHandle, WindowState
from jaya_os.ui_spec import WidgetSpec, Rect

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi

# Win32 constants
WS_OVERLAPPEDWINDOW = 0x00CF0000
WS_VISIBLE = 0x10000000
CW_USEDEFAULT = 0x80000000

class Win32Backend(WindowManagerBackend):
    def __init__(self):
        self._register_window_class()
        self._hwnd_map = {}  # window_id -> hwnd
    
    def _register_window_class(self):
        wc = ctypes.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(ctypes.WNDCLASSEXW)
        wc.style = 0x0001 | 0x0002 | 0x0008  # CS_HREDRAW | CS_VREDRAW | CS_DBLCLKS
        wc.lpfnWndProc = self._wnd_proc
        wc.hInstance = ctypes.windll.kernel32.GetModuleHandleW(None)
        wc.hIcon = user32.LoadIconW(None, 0x7F00)  # IDI_APPLICATION
        wc.hCursor = user32.LoadCursorW(None, 0x7F00)  # IDC_ARROW
        wc.hbrBackground = ctypes.c_int(5 + 1)  # COLOR_WINDOW + 1
        wc.lpszClassName = "JAYA_OS_Window"
        
        atom = user32.RegisterClassExW(ctypes.byref(wc))
        if not atom:
            raise ctypes.WinError()
    
    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        # Handle messages: WM_CLOSE, WM_SIZE, WM_SETFOCUS, etc.
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
    
    def create_window(self, spec: WidgetSpec) -> WindowHandle:
        # Parse dimensions
        width = self._parse_dimension(spec.props.get("width", "800px"))
        height = self._parse_dimension(spec.props.get("height", "600px"))
        
        hwnd = user32.CreateWindowExW(
            0, "JAYA_OS_Window", spec.props.get("title", "JAYA_OS"),
            WS_OVERLAPPEDWINDOW | WS_VISIBLE,
            CW_USEDEFAULT, CW_USEDEFAULT, width, height,
            None, None, ctypes.windll.kernel32.GetModuleHandleW(None), None
        )
        
        if not hwnd:
            raise ctypes.WinError()
        
        # Enable dark mode if supported
        self._try_enable_dark_mode(hwnd)
        
        handle = WindowHandle(
            window_id=str(id(hwnd)),
            title=spec.props.get("title", "JAYA_OS"),
            bounds=Rect(0, 0, f"{width}px", f"{height}px"),
            state=WindowState.NORMAL,
            z_order=0,
            has_focus=True,
            widget_tree=spec
        )
        
        self._hwnd_map[handle.window_id] = hwnd
        return handle
    
    def _try_enable_dark_mode(self, hwnd):
        try:
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            value = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(
                hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
                ctypes.byref(value), ctypes.sizeof(value)
            )
        except:
            pass  # Not supported on this Windows version
    
    def _parse_dimension(self, dim: str) -> int:
        if dim.endswith("px"):
            return int(dim[:-2])
        return 800  # default
    
    def destroy_window(self, handle: WindowHandle) -> bool:
        hwnd = self._hwnd_map.pop(handle.window_id, None)
        if hwnd:
            return user32.DestroyWindow(hwnd)
        return False
    
    def bring_to_front(self, handle: WindowHandle) -> None:
        hwnd = self._hwnd_map.get(handle.window_id)
        if hwnd:
            user32.BringWindowToTop(hwnd)
    
    def set_focus(self, handle: WindowHandle) -> None:
        hwnd = self._hwnd_map.get(handle.window_id)
        if hwnd:
            user32.SetFocus(hwnd)
    
    def get_window_state(self, handle: WindowHandle) -> WindowState:
        hwnd = self._hwnd_map.get(handle.window_id)
        if not hwnd:
            return WindowState.NORMAL
        
        placement = ctypes.WINDOWPLACEMENT()
        placement.length = ctypes.sizeof(ctypes.WINDOWPLACEMENT)
        user32.GetWindowPlacement(hwnd, ctypes.byref(placement))
        
        if placement.showCmd == 2:  # SW_MINIMIZE
            return WindowState.MINIMIZED
        elif placement.showCmd == 3:  # SW_MAXIMIZE
            return WindowState.MAXIMIZED
        return WindowState.NORMAL
    
    def set_window_state(self, handle: WindowHandle, state: WindowState) -> None:
        hwnd = self._hwnd_map.get(handle.window_id)
        if not hwnd:
            return
        
        cmd_map = {
            WindowState.NORMAL: 1,      # SW_NORMAL
            WindowState.MINIMIZED: 2,   # SW_MINIMIZE
            WindowState.MAXIMIZED: 3,   # SW_MAXIMIZE
        }
        user32.ShowWindow(hwnd, cmd_map.get(state, 1))
    
    def list_windows(self) -> list:
        return list(self._hwnd_map.keys())
```

#### X11 Backend (`window_manager_x11.py`)
```python
# src/jaya_os/window_manager_x11.py
from Xlib import display, X
from jaya_os.window_manager import WindowManagerBackend, WindowHandle, WindowState
from jaya_os.ui_spec import WidgetSpec, Rect

class X11Backend(WindowManagerBackend):
    def __init__(self):
        self.d = display.Display()
        self.screen = self.d.screen()
        self.root = self.screen.root
        self._window_map = {}  # window_id -> X window
    
    def create_window(self, spec: WidgetSpec) -> WindowHandle:
        width = self._parse_dimension(spec.props.get("width", "800px"))
        height = self._parse_dimension(spec.props.get("height", "600px"))
        
        window = self.root.create_window(
            0, 0, width, height, 1,
            self.screen.root_depth,
            X.InputOutput,
            X.CopyFromParent,
            background_pixel=self.screen.white_pixel,
            event_mask=(
                X.ExposureMask | X.KeyPressMask | X.ButtonPressMask |
                X.StructureNotifyMask | X.FocusChangeMask
            )
        )
        
        window.set_wm_name(spec.props.get("title", "JAYA_OS"))
        window.set_wm_class("jaya_os", "JAYA_OS")
        window.map()
        self.d.flush()
        
        handle = WindowHandle(
            window_id=str(window.id),
            title=spec.props.get("title", "JAYA_OS"),
            bounds=Rect(0, 0, f"{width}px", f"{height}px"),
            state=WindowState.NORMAL,
            z_order=0,
            has_focus=True,
            widget_tree=spec
        )
        
        self._window_map[handle.window_id] = window
        return handle
    
    def _parse_dimension(self, dim: str) -> int:
        if dim.endswith("px"):
            return int(dim[:-2])
        return 800
    
    def destroy_window(self, handle: WindowHandle) -> bool:
        window = self._window_map.pop(handle.window_id, None)
        if window:
            window.destroy()
            self.d.flush()
            return True
        return False
    
    def bring_to_front(self, handle: WindowHandle) -> None:
        window = self._window_map.get(handle.window_id)
        if window:
            window.configure(stack_mode=X.Above)
            self.d.flush()
    
    def set_focus(self, handle: WindowHandle) -> None:
        window = self._window_map.get(handle.window_id)
        if window:
            window.set_input_focus(X.RevertToParent, X.CurrentTime)
            self.d.flush()
    
    def get_window_state(self, handle: WindowHandle) -> WindowState:
        # X11 doesn't have direct minimized/maximized state
        # Would need to check _NET_WM_STATE atoms
        return WindowState.NORMAL
    
    def set_window_state(self, handle: WindowHandle, state: WindowState) -> None:
        # Would need to use _NET_WM_STATE atoms
        pass
    
    def list_windows(self) -> list:
        return list(self._window_map.keys())
```

### 2.2 Widget Runtime

```python
# src/jaya_os/widget_runtime.py
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable
from jaya_os.ui_spec import WidgetSpec, WidgetType, LayoutType, StyleTokens, Rect, Binding, EventHandler

@dataclass
class RenderedWidget:
    widget_id: str
    spec: WidgetSpec
    bounds: Rect
    children: List["RenderedWidget"] = field(default_factory=list)

class WidgetRuntime:
    def __init__(self, window_handle, style_tokens: StyleTokens = None):
        self.window_handle = window_handle
        self.style = style_tokens or StyleTokens()
        self.widget_registry: Dict[str, Callable] = {}
        self._register_builtin_widgets()
    
    def _register_builtin_widgets(self):
        self.widget_registry = {
            WidgetType.WINDOW: self._render_window,
            WidgetType.PANEL: self._render_panel,
            WidgetType.BUTTON: self._render_button,
            WidgetType.LABEL: self._render_label,
            WidgetType.TEXT_INPUT: self._render_text_input,
            WidgetType.TEXTAREA: self._render_textarea,
            WidgetType.SELECT: self._render_select,
            WidgetType.CHECKBOX: self._render_checkbox,
            WidgetType.RADIO: self._render_radio,
            WidgetType.SLIDER: self._render_slider,
            WidgetType.PROGRESS: self._render_progress,
            WidgetType.LIST: self._render_list,
            WidgetType.TABLE: self._render_table,
            WidgetType.CHART: self._render_chart,
            WidgetType.IMAGE: self._render_image,
            WidgetType.TAB: self._render_tab,
            WidgetType.SPLITTER: self._render_splitter,
        }
    
    def render(self, spec: WidgetSpec, container_bounds: Rect) -> RenderedWidget:
        """Render widget tree to native UI."""
        renderer = self.widget_registry.get(spec.type)
        if not renderer:
            raise ValueError(f"No renderer for widget type: {spec.type}")
        return renderer(spec, container_bounds)
    
    def _render_window(self, spec: WidgetSpec, bounds: Rect) -> RenderedWidget:
        # Window is handled by WindowManager
        children = []
        for child in spec.children:
            child_bounds = self._compute_child_bounds(spec, child, bounds)
            children.append(self.render(child, child_bounds))
        return RenderedWidget(
            widget_id=spec.id,
            spec=spec,
            bounds=bounds,
            children=children
        )
    
    def _render_panel(self, spec: WidgetSpec, bounds: Rect) -> RenderedWidget:
        layout = spec.layout or LayoutType.FLEX_COL
        children = []
        child_bounds_list = self.layout_engine.layout(spec.children, bounds, layout)
        for child, child_bounds in zip(spec.children, child_bounds_list):
            children.append(self.render(child, child_bounds))
        return RenderedWidget(
            widget_id=spec.id,
            spec=spec,
            bounds=bounds,
            children=children
        )
    
    def _render_button(self, spec: WidgetSpec, bounds: Rect) -> RenderedWidget:
        # Native button rendering would go here
        # For now, return placeholder
        return RenderedWidget(
            widget_id=spec.id,
            spec=spec,
            bounds=bounds,
            children=[]
        )
    
    # ... other widget renderers
    
    def _compute_child_bounds(self, parent: WidgetSpec, child: WidgetSpec, parent_bounds: Rect) -> Rect:
        # Simplified - layout engine handles this
        return Rect(0, 0, "100%", "100%")
```

### 2.3 Layout Engine

```python
# src/jaya_os/layout_engine.py
from dataclasses import dataclass
from typing import List, Tuple
from jaya_os.ui_spec import WidgetSpec, Rect, LayoutType

@dataclass
class LayoutEngine:
    def layout(self, children: List[WidgetSpec], container: Rect, 
               layout_type: LayoutType) -> List[Rect]:
        if layout_type == LayoutType.FLEX_ROW:
            return self._flex_row(children, container)
        elif layout_type == LayoutType.FLEX_COL:
            return self._flex_col(children, container)
        elif layout_type == LayoutType.GRID:
            return self._grid(children, container)
        elif layout_type == LayoutType.ABSOLUTE:
            return self._absolute(children, container)
        else:
            return self._stack(children, container)
    
    def _flex_row(self, children: List[WidgetSpec], container: Rect) -> List[Rect]:
        # Simplified flex row layout
        total_flex = sum(self._get_flex(child) for child in children)
        if total_flex == 0:
            total_flex = len(children)
        
        x = container.x
        results = []
        for child in children:
            flex = self._get_flex(child)
            width = int(container.width * flex / total_flex)
            results.append(Rect(x, container.y, width, container.height))
            x += width
        return results
    
    def _flex_col(self, children: List[WidgetSpec], container: Rect) -> List[Rect]:
        total_flex = sum(self._get_flex(child) for child in children)
        if total_flex == 0:
            total_flex = len(children)
        
        y = container.y
        results = []
        for child in children:
            flex = self._get_flex(child)
            height = int(container.height * flex / total_flex)
            results.append(Rect(container.x, y, container.width, height))
            y += height
        return results
    
    def _grid(self, children: List[WidgetSpec], container: Rect) -> List[Rect]:
        # Simplified grid - assume square grid
        import math
        cols = int(math.ceil(math.sqrt(len(children))))
        rows = int(math.ceil(len(children) / cols))
        cell_w = container.width // cols
        cell_h = container.height // rows
        
        results = []
        for i, child in enumerate(children):
            row = i // cols
            col = i % cols
            results.append(Rect(
                container.x + col * cell_w,
                container.y + row * cell_h,
                cell_w, cell_h
            ))
        return results
    
    def _absolute(self, children: List[WidgetSpec], container: Rect) -> List[Rect]:
        results = []
        for child in children:
            # Parse absolute position from props
            x = child.props.get("x", 0)
            y = child.props.get("y", 0)
            w = child.props.get("width", 100)
            h = child.props.get("height", 100)
            results.append(Rect(x, y, w, h))
        return results
    
    def _stack(self, children: List[WidgetSpec], container: Rect) -> List[Rect]:
        # Stack all children on top of each other
        return [Rect(container.x, container.y, container.width, container.height) 
                for _ in children]
    
    def _get_flex(self, child: WidgetSpec) -> int:
        flex = child.props.get("flex", 1)
        if isinstance(flex, str) and flex.endswith("%"):
            return int(flex[:-1])
        return int(flex)
```

### 2.4 Style System

```python
# src/jaya_os/style_tokens.py
from dataclasses import dataclass, field
from typing import Dict

@dataclass
class StyleTokens:
    # Colors
    color_primary: str = "#0066CC"
    color_primary_hover: str = "#0052A3"
    color_primary_active: str = "#003D7A"
    color_secondary: str = "#6C757D"
    color_success: str = "#28A745"
    color_warning: str = "#FFC107"
    color_danger: str = "#DC3545"
    color_info: str = "#17A2B8"
    color_light: str = "#F8F9FA"
    color_dark: str = "#343A40"
    color_background: str = "#FFFFFF"
    color_surface: str = "#F5F5F5"
    color_text: str = "#1A1A1A"
    color_text_secondary: str = "#666666"
    color_text_muted: str = "#999999"
    color_border: str = "#E0E0E0"
    color_border_focus: str = "#0066CC"
    
    # Spacing
    spacing_unit: str = "8px"
    spacing_xs: str = "4px"
    spacing_sm: str = "8px"
    spacing_md: str = "16px"
    spacing_lg: str = "24px"
    spacing_xl: str = "32px"
    
    # Typography
    font_family: str = "Inter, system-ui, -apple-system, sans-serif"
    font_size_xs: str = "12px"
    font_size_sm: str = "14px"
    font_size_base: str = "16px"
    font_size_lg: str = "18px"
    font_size_xl: str = "24px"
    font_size_2xl: str = "32px"
    font_weight_normal: int = 400
    font_weight_medium: int = 500
    font_weight_semibold: int = 600
    font_weight_bold: int = 700
    line_height_base: float = 1.5
    line_height_tight: float = 1.25
    
    # Borders & Radius
    border_width: str = "1px"
    border_radius: str = "8px"
    border_radius_sm: str = "4px"
    border_radius_lg: str = "12px"
    border_radius_full: str = "9999px"
    
    # Shadows
    shadow_elevation_1: str = "0 1px 3px rgba(0,0,0,0.1)"
    shadow_elevation_2: str = "0 4px 6px rgba(0,0,0,0.1)"
    shadow_elevation_3: str = "0 10px 20px rgba(0,0,0,0.1)"
    shadow_elevation_4: str = "0 20px 40px rgba(0,0,0,0.1)"
    
    # Transitions
    transition_fast: str = "150ms ease"
    transition_normal: str = "250ms ease"
    transition_slow: str = "350ms ease"
    
    # Z-index
    z_index_dropdown: int = 1000
    z_index_modal: int = 1100
    z_index_tooltip: int = 1200
    z_index_toast: int = 1300
    
    # Breakpoints
    breakpoint_sm: str = "640px"
    breakpoint_md: str = "768px"
    breakpoint_lg: str = "1024px"
    breakpoint_xl: str = "1280px"
    
    def get_color(self, name: str) -> str:
        return getattr(self, f"color_{name}", self.color_primary)
    
    def get_spacing(self, name: str) -> str:
        return getattr(self, f"spacing_{name}", self.spacing_unit)
    
    def get_font_size(self, name: str) -> str:
        return getattr(self, f"font_size_{name}", self.font_size_base)
    
    def get_shadow(self, name: str) -> str:
        return getattr(self, f"shadow_{name}", self.shadow_elevation_1)
    
    def get_transition(self, name: str) -> str:
        return getattr(self, f"transition_{name}", self.transition_normal)

# Dark theme variant
DARK_THEME = StyleTokens(
    color_background="#1A1A1A",
    color_surface="#2D2D2D",
    color_text="#E0E0E0",
    color_text_secondary="#A0A0A0",
    color_text_muted="#707070",
    color_border="#404040",
    color_surface_hover="#3D3D3D",
)
```

### 2.5 Event Loop

```python
# src/jaya_os/event_loop.py
import asyncio
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional
from jaya_os.window_manager import WindowHandle
from jaya_os.widget_runtime import WidgetRuntime
from jaya_os.feature_bridge import JayaBridge

@dataclass
class NativeEvent:
    event_type: str  # "mouse_down", "mouse_up", "mouse_move", "key_down", "key_up", "resize", "close", "focus"
    window_id: str
    x: int = 0
    y: int = 0
    key: str = ""
    modifiers: List[str] = field(default_factory=list)
    button: int = 0
    width: int = 0
    height: int = 0

class EventLoop:
    def __init__(self, window_manager, widget_runtime: WidgetRuntime, jaya_bridge: JayaBridge):
        self.window_manager = window_manager
        self.widget_runtime = widget_runtime
        self.jaya_bridge = jaya_bridge
        self._running = False
        self._hotkeys: Dict[str, Callable] = {}
        self._widget_focus: Dict[str, str] = {}  # window_id -> widget_id
    
    def run(self):
        """Start the event loop (blocking)."""
        self._running = True
        # Platform-specific event loop
        import sys
        if sys.platform == "win32":
            self._run_win32()
        elif sys.platform.startswith("linux"):
            self._run_x11()
    
    def _run_win32(self):
        import ctypes
        user32 = ctypes.windll.user32
        msg = ctypes.wintypes.MSG()
        while self._running and user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    
    def _run_x11(self):
        from Xlib import display
        d = display.Display()
        while self._running:
            event = d.next_event()
            self._handle_x11_event(event)
    
    def _handle_x11_event(self, event):
        # Convert X11 event to NativeEvent and process
        pass
    
    def stop(self):
        self._running = False
    
    def post_event(self, event: NativeEvent):
        """Post event from another thread."""
        # Thread-safe event posting
        pass
    
    def register_hotkey(self, key: str, callback: Callable):
        self._hotkeys[key] = callback
    
    def _dispatch_widget_event(self, window_id: str, event: NativeEvent):
        """Dispatch event to widget runtime for hit testing and handling."""
        # 1. Hit test: find widget at (x, y)
        # 2. Call widget event handler
        # 3. If action, dispatch via JayaBridge
        pass
```

### 2.6 Data Binding

```python
# src/jaya_os/data_binding.py
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import json

@dataclass
class Binding:
    source: str              # Path in state: "user.name"
    target: str              # Widget property: "text"
    transform: Optional[str] = None  # "uppercase", "currency", "date", "json"
    two_way: bool = False    # If True, widget updates propagate back to state

class DataBinder:
    def __init__(self):
        self.bindings: List[Binding] = []
        self.state: Dict[str, Any] = {}
        self.widget_values: Dict[str, Any] = {}  # widget_id -> value
    
    def bind(self, binding: Binding):
        self.bindings.append(binding)
    
    def set_state(self, path: str, value: Any):
        """Set state value and propagate to bound widgets."""
        self._set_nested(self.state, path, value)
        self._propagate_to_widgets(path, value)
    
    def get_state(self, path: str) -> Any:
        return self._get_nested(self.state, path)
    
    def widget_update(self, widget_id: str, property: str, value: Any):
        """Called when widget value changes (for two-way binding)."""
        self.widget_values[f"{widget_id}.{property}"] = value
        
        # Find two-way bindings for this widget/property
        for binding in self.bindings:
            if binding.two_way and binding.target == property:
                # Find widget by ID (simplified)
                self._set_nested(self.state, binding.source, value)
    
    def _propagate_to_widgets(self, path: str, value: Any):
        for binding in self.bindings:
            if binding.source == path:
                transformed = self._transform(value, binding.transform)
                # Update widget (would need widget registry)
                pass
    
    def _transform(self, value: Any, transform: Optional[str]) -> Any:
        if not transform:
            return value
        if transform == "uppercase":
            return str(value).upper()
        elif transform == "lowercase":
            return str(value).lower()
        elif transform == "currency":
            return f"${float(value):,.2f}"
        elif transform == "date":
            from datetime import datetime
            return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d")
        elif transform == "json":
            return json.dumps(value)
        return value
    
    def _get_nested(self, obj: dict, path: str) -> Any:
        keys = path.split(".")
        for key in keys:
            if isinstance(obj, dict):
                obj = obj.get(key)
            else:
                return None
        return obj
    
    def _set_nested(self, obj: dict, path: str, value: Any):
        keys = path.split(".")
        for key in keys[:-1]:
            if key not in obj:
                obj[key] = {}
            obj = obj[key]
        obj[keys[-1]] = value
```

---

## Integration with JayaBridge

```python
# src/jaya_os/bridge_integration.py
from jaya_os.feature_bridge import JayaBridge
from jaya_os.window_manager import WindowManager
from jaya_os.widget_runtime import WidgetRuntime
from jaya_os.event_loop import EventLoop
from jaya_os.data_binding import DataBinder

class JAYA_OS_Runtime:
    def __init__(self, features_dir: str = "./features"):
        self.bridge = JayaBridge(features_dir)
        self.window_manager = WindowManager()
        self.widget_runtime = WidgetRuntime(None)  # window_handle set per window
        self.data_binder = DataBinder()
        self.event_loop = EventLoop(
            self.window_manager, self.widget_runtime, self.bridge
        )
    
    def mount_feature_with_ui(self, feature_name: str, config: dict = None) -> str:
        """Mount feature and create its UI window."""
        feature_id = self.bridge.mount_feature(feature_name, config)
        
        # If feature has UI spec, create window
        feature_instance = self.bridge.mounted.get(feature_id)
        if feature_instance and feature_instance.manifest.ui_spec:
            window_handle = self.window_manager.create_window(
                feature_instance.manifest.ui_spec.root
            )
            
            # Create widget runtime for this window
            widget_runtime = WidgetRuntime(window_handle)
            
            # Render UI
            widget_runtime.render(
                feature_instance.manifest.ui_spec.root,
                window_handle.bounds
            )
            
            # Register with event loop
            self.event_loop.widget_runtime = widget_runtime
        
        return feature_id
    
    def run(self):
        """Start the JAYA_OS runtime."""
        self.event_loop.run()
    
    def shutdown(self):
        self.event_loop.stop()
        # Unmount all features
        for feature_id in list(self.bridge.mounted.keys()):
            self.bridge.unmount_feature(feature_id)
```

---

## Verification Checklist

### Functional
- [ ] WindowManager creates, shows, hides, closes windows on Windows + Linux
- [ ] All 16 widget types render correctly
- [ ] Flexbox + Grid layouts work correctly
- [ ] Style tokens applied correctly
- [ ] Mouse/keyboard events dispatch to JayaBridge
- [ ] Data binding updates UI reactively
- [ ] 60fps rendering for simple UIs

### Quality
- [ ] Unit tests for each component
- [ ] Integration test: Intent → UI → Feature → Action
- [ ] Cross-platform tests (Windows + Linux CI)
- [ ] Memory leak tests (long-running)

### Performance
- [ ] Window creation < 100ms
- [ ] Widget tree layout < 50ms
- [ ] Initial paint < 200ms
- [ ] 60fps sustained for simple UIs

---

## Success Criteria
- [ ] WindowManager works on Windows + Linux
- [ ] All 16 widget types render
- [ ] Flexbox + Grid layouts functional
- [ ] Style tokens system works
- [ ] Event loop dispatches to JayaBridge
- [ ] Data binding reactive
- [ ] Integration test passes

---

## Handoff to OS-3

**Contract**: OS-2 provides:
- WindowManager with Win32 + X11 backends
- WidgetRuntime with 16 widget types
- LayoutEngine (Flexbox + Grid)
- StyleTokens theming system
- EventLoop with hotkey support
- DataBinder for reactive UI

**Files for OS-3**:
- `src/jaya_os/ipc.py` (channel infrastructure)
- `src/jaya_os/ipc_protocol.py` (message schemas)

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [UI Runtime](../03-features/ui-runtime.md)
- [Runtime Features](../03-features/runtime-features.md)
- [Roadmap Overview](../06-roadmap/README.md)