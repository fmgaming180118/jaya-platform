# Window Manager Research — JAYA_OS

## Overview

Research notes on window management implementation for JAYA_OS. The WindowManager is responsible for window lifecycle, z-order, focus, and multi-monitor support.

---

## Design Goals

1. **Cross-platform** — Windows, Linux (X11/Wayland), macOS
2. **Lightweight** — Minimal dependencies, fast startup
3. **Embeddable** — Can run in-process or as separate process
4. **Scriptable** — Full control via Python API

---

## Backend Options

### Option 1: Native Python (ctypes/cffi)
- **Windows**: `user32.dll`, `dwmapi.dll`
- **Linux**: Xlib (`libX11`), Wayland (`libwayland-client`)
- **macOS**: Cocoa (`AppKit`)

**Pros**: No external dependencies, full control
**Cons**: Platform-specific code, maintenance burden

### Option 2: Web-based (Electron/Tauri-like)
- Use webview (WebView2 on Windows, WebKitGTK on Linux, WKWebView on macOS)
- Render UI as HTML/CSS/JS

**Pros**: Cross-platform UI, rich styling
**Cons**: Heavier, JavaScript bridge complexity

### Option 3: GUI Toolkit (PyQt/PySide, Tkinter, wxPython)
- **PyQt6/PySide6**: Qt6, mature, feature-rich
- **Tkinter**: Built-in, lightweight
- **wxPython**: Native look

**Pros**: Battle-tested, handles platform differences
**Cons**: Large dependencies (Qt), licensing (PyQt GPL/commercial)

### Option 4: Custom Minimal (Recommended for JAYA_OS)
- **Windows**: Direct Win32 API via `ctypes`
- **Linux**: X11 via `python-xlib` or Wayland via `pywayland`
- **macOS**: Cocoa via `pyobjc` (if available) or X11

**Pros**: Minimal, tailored to JAYA_OS needs
**Cons**: More development effort

---

## Recommended Approach: Hybrid

### Phase OS-2 (WindowManager MVP)
1. **Windows**: Win32 API via `ctypes` (no external deps)
2. **Linux**: X11 via `python-xlib` (lightweight)
3. **macOS**: Deferred (use XQuartz/X11 initially)

### Phase OS-4 (Hardware Abstraction)
- Add Wayland support for Linux
- Native macOS Cocoa backend
- Multi-monitor, DPI scaling, touch input

---

## Core API Design

```python
class WindowManager:
    def __init__(self, config: WindowManagerConfig):
        self.backend = self._create_backend()
    
    def create_window(self, spec: WidgetSpec) -> WindowHandle:
        """Create window from WINDOW widget spec."""
        ...
    
    def destroy_window(self, handle: WindowHandle) -> bool:
        ...
    
    def bring_to_front(self, handle: WindowHandle) -> None:
        ...
    
    def set_focus(self, handle: WindowHandle) -> None:
        ...
    
    def get_window_state(self, handle: WindowHandle) -> WindowState:
        ...
    
    def set_window_state(self, handle: WindowHandle, state: WindowState) -> None:
        ...
    
    def list_windows(self) -> List[WindowHandle]:
        ...

class WindowHandle:
    window_id: str
    title: str
    bounds: Rect
    state: WindowState  # NORMAL, MINIMIZED, MAXIMIZED, FULLSCREEN
    z_order: int
    has_focus: bool
    widget_tree: WidgetSpec
```

---

## Win32 Implementation Notes

### Key APIs
```python
# Window creation
CreateWindowExW(
    dwExStyle, lpClassName, lpWindowName, dwStyle,
    x, y, nWidth, nHeight, hWndParent, hMenu, hInstance, lpParam
)

# Window styles
WS_OVERLAPPEDWINDOW = WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX
WS_VISIBLE = 0x10000000

# DWM (Desktop Window Manager) for modern styling
DwmExtendFrameIntoClientArea(hwnd, margins)
DwmSetWindowAttribute(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, ...)

# Message loop
GetMessageW, TranslateMessage, DispatchMessageW
```

### Window Class Registration
```python
WNDCLASSEXW = {
    "cbSize": sizeof(WNDCLASSEXW),
    "style": CS_HREDRAW | CS_VREDRAW | CS_DBLCLKS,
    "lpfnWndProc": window_proc,
    "hInstance": GetModuleHandleW(None),
    "hIcon": LoadIconW(None, IDI_APPLICATION),
    "hCursor": LoadCursorW(None, IDC_ARROW),
    "hbrBackground": COLOR_WINDOW + 1,
    "lpszClassName": "JAYA_OS_Window",
}
```

### DPI Awareness
```python
# Per-monitor DPI awareness (Windows 10+)
SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)
```

---

## X11 Implementation Notes

### Key Libraries
- `python-xlib` — Pure Python X11 client library
- Or `xcb` via `python-xcffib` (faster, lower-level)

### Basic Window Creation
```python
from Xlib import display, X

d = display.Display()
screen = d.screen()
root = screen.root

window = root.create_window(
    x, y, width, height, border_width,
    screen.root_depth,
    X.InputOutput,
    X.CopyFromParent,
    background_pixel=screen.white_pixel,
    event_mask=X.ExposureMask | X.KeyPressMask | X.ButtonPressMask | X.StructureNotifyMask
)

window.set_wm_name("JAYA_OS Window")
window.set_wm_class("jaya_os", "JAYA_OS")
window.map()
```

### Event Handling
```python
while True:
    event = d.next_event()
    if event.type == X.Expose:
        # Redraw
    elif event.type == X.KeyPress:
        # Handle key
    elif event.type == X.ConfigureNotify:
        # Resize/move
```

---

## Integration with Widget Runtime

### Window ↔ Widget Tree
```python
class WindowManager:
    def create_window(self, spec: WidgetSpec) -> WindowHandle:
        # 1. Create native window
        handle = self.backend.create_window(
            title=spec.props.get("title", "JAYA_OS"),
            width=parse_dimension(spec.props.get("width", "800px")),
            height=parse_dimension(spec.props.get("height", "600px")),
        )
        
        # 2. Create widget runtime for this window
        widget_runtime = WidgetRuntime(handle, spec)
        
        # 3. Register with event loop
        self.event_loop.register_window(handle, widget_runtime)
        
        return WindowHandle(
            window_id=handle.id,
            title=spec.props.get("title", "JAYA_OS"),
            bounds=Rect(0, 0, width, height),
            state=WindowState.NORMAL,
            z_order=self._next_z_order(),
            has_focus=True,
            widget_tree=spec
        )
```

---

## Multi-Monitor Support

### Windows
```python
# EnumDisplayMonitors to get monitor info
# MonitorFromWindow to get monitor for window
# SetWindowPos with HWND_TOPMOST for fullscreen
```

### X11
```python
# XRandR extension for monitor configuration
# Xinerama for multi-monitor info
```

---

## Testing Strategy

```bash
# Unit tests for WindowManager API
python -m pytest tests/ -k "window_manager" -v

# Integration tests with WidgetRuntime
python -m pytest tests/ -k "window_widget_integration" -v

# Platform-specific tests (run on each OS)
python -m pytest tests/ -k "win32" -v
python -m pytest tests/ -k "x11" -v
```

---

## Future Enhancements

| Feature | Priority | Notes |
|---|---|---|
| Wayland support | High | Linux modern display protocol |
| macOS native | Medium | Cocoa via pyobjc |
| Touch input | Medium | Windows Pointer API, X11 XI2 |
| DPI scaling | High | Per-monitor DPI |
| Window snapping | Low | Win32 Snap, X11 _NET_WM_STATE |
| Virtual desktops | Low | Windows VirtualDesktop API, X11 _NET_CURRENT_DESKTOP |

---

## 🔗 Related Docs

- [UI Runtime](../03-features/ui-runtime.md) — Widget Runtime, Event Loop
- [IPC Bridge](../03-features/ipc-bridge.md) — Inter-process communication
- [Architecture Overview](../02-architecture/overview.md)
- [Roadmap OS-2](../06-roadmap/os-2-window-manager.md)