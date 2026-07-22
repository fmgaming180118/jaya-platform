"""Phase 3B — Window Manager for os_kernel.

This module provides window management capabilities including:
- Window creation, destruction, and lifecycle
- Z-order management
- Focus management
- Layout and tiling
- Multi-monitor support (stub)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict


class WindowState(str, Enum):
    """Window states."""
    NORMAL = "normal"
    MINIMIZED = "minimized"
    MAXIMIZED = "maximized"
    FULLSCREEN = "fullscreen"
    CLOSED = "closed"


class WindowLayer(str, Enum):
    """Window z-order layers."""
    DESKTOP = "desktop"          # Wallpaper, widgets
    NORMAL = "normal"            # Regular windows
    DOCK = "dock"                # Taskbar, dock
    DIALOG = "dialog"            # Modal dialogs
    TOOLTIP = "tooltip"          # Tooltips, popovers
    OVERLAY = "overlay"          # System overlays


@dataclass
class WindowGeometry:
    """Window position and size."""
    x: int = 0
    y: int = 0
    width: int = 800
    height: int = 600
    
    def to_dict(self) -> Dict[str, Any]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WindowGeometry":
        return cls(
            x=data.get("x", 0),
            y=data.get("y", 0),
            width=data.get("width", 800),
            height=data.get("height", 600),
        )


@dataclass
class Window:
    """Window managed by the shell."""
    window_id: str
    title: str
    feature_id: str
    mount_point: str
    geometry: WindowGeometry = field(default_factory=WindowGeometry)
    state: WindowState = WindowState.NORMAL
    layer: WindowLayer = WindowLayer.NORMAL
    visible: bool = True
    focused: bool = False
    resizable: bool = True
    minimizable: bool = True
    maximizable: bool = True
    closable: bool = True
    icon: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: datetime.now().timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now().timestamp())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "window_id": self.window_id,
            "title": self.title,
            "feature_id": self.feature_id,
            "mount_point": self.mount_point,
            "geometry": self.geometry.to_dict(),
            "state": self.state.value,
            "layer": self.layer.value,
            "visible": self.visible,
            "focused": self.focused,
            "resizable": self.resizable,
            "minimizable": self.minimizable,
            "maximizable": self.maximizable,
            "closable": self.closable,
            "icon": self.icon,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class WindowManager:
    """Manages windows, z-order, focus, and layout."""
    
    def __init__(self):
        self._windows: Dict[str, Window] = {}
        self._z_order: List[str] = []  # window_ids from bottom to top
        self._focused_window: Optional[str] = None
        self._callbacks: Dict[str, List[Callable]] = defaultdict(list)
        self._next_z = 1000
    
    def create_window(self, feature_id: str, mount_point: str, title: str = "",
                      geometry: WindowGeometry = None, layer: WindowLayer = WindowLayer.NORMAL,
                      **kwargs) -> Window:
        """Create a new window for a mounted feature."""
        window_id = str(uuid.uuid4())[:8]
        window = Window(
            window_id=window_id,
            title=title or f"Feature {feature_id[:8]}",
            feature_id=feature_id,
            mount_point=mount_point,
            geometry=geometry or WindowGeometry(),
            layer=layer,
            **kwargs
        )
        
        self._windows[window_id] = window
        self._z_order.append(window_id)
        self._bring_to_front(window_id)
        self._set_focus(window_id)
        self._emit("window_created", window)
        
        return window
    
    def close_window(self, window_id: str) -> bool:
        """Close a window."""
        if window_id not in self._windows:
            return False
        
        window = self._windows[window_id]
        window.state = WindowState.CLOSED
        window.visible = False
        
        if window_id in self._z_order:
            self._z_order.remove(window_id)
        
        if self._focused_window == window_id:
            self._focused_window = None
            # Focus next topmost window
            for wid in reversed(self._z_order):
                if self._windows[wid].visible:
                    self._set_focus(wid)
                    break
        
        self._emit("window_closed", window)
        del self._windows[window_id]
        return True
    
    def minimize_window(self, window_id: str) -> bool:
        """Minimize a window."""
        if window_id not in self._windows:
            return False
        window = self._windows[window_id]
        window.state = WindowState.MINIMIZED
        window.visible = False
        window.updated_at = datetime.now().timestamp()
        self._emit("window_minimized", window)
        return True
    
    def maximize_window(self, window_id: str) -> bool:
        """Maximize a window."""
        if window_id not in self._windows:
            return False
        window = self._windows[window_id]
        window.state = WindowState.MAXIMIZED
        window.updated_at = datetime.now().timestamp()
        self._emit("window_maximized", window)
        return True
    
    def restore_window(self, window_id: str) -> bool:
        """Restore a minimized/maximized window."""
        if window_id not in self._windows:
            return False
        window = self._windows[window_id]
        window.state = WindowState.NORMAL
        window.visible = True
        window.updated_at = datetime.now().timestamp()
        self._emit("window_restored", window)
        return True
    
    def set_window_geometry(self, window_id: str, geometry: WindowGeometry) -> bool:
        """Set window position and size."""
        if window_id not in self._windows:
            return False
        window = self._windows[window_id]
        window.geometry = geometry
        window.updated_at = datetime.now().timestamp()
        self._emit("window_geometry_changed", window)
        return True
    
    def set_window_title(self, window_id: str, title: str) -> bool:
        """Set window title."""
        if window_id not in self._windows:
            return False
        window = self._windows[window_id]
        window.title = title
        window.updated_at = datetime.now().timestamp()
        self._emit("window_title_changed", window)
        return True
    
    def bring_to_front(self, window_id: str) -> bool:
        """Bring window to front (top of z-order)."""
        return self._bring_to_front(window_id)
    
    def _bring_to_front(self, window_id: str) -> bool:
        if window_id not in self._windows:
            return False
        if window_id in self._z_order:
            self._z_order.remove(window_id)
        self._z_order.append(window_id)
        self._emit("window_zorder_changed", self._windows[window_id])
        return True
    
    def send_to_back(self, window_id: str) -> bool:
        """Send window to back (bottom of z-order)."""
        if window_id not in self._windows:
            return False
        if window_id in self._z_order:
            self._z_order.remove(window_id)
        self._z_order.insert(0, window_id)
        self._emit("window_zorder_changed", self._windows[window_id])
        return True
    
    def focus_window(self, window_id: str) -> bool:
        """Set focus to a window."""
        return self._set_focus(window_id)
    
    def _set_focus(self, window_id: str) -> bool:
        if window_id not in self._windows:
            return False
        
        # Unfocus previous
        if self._focused_window and self._focused_window in self._windows:
            self._windows[self._focused_window].focused = False
        
        self._focused_window = window_id
        self._windows[window_id].focused = True
        self._bring_to_front(window_id)
        self._emit("window_focused", self._windows[window_id])
        return True
    
    def get_window(self, window_id: str) -> Optional[Window]:
        """Get window by ID."""
        return self._windows.get(window_id)
    
    def get_window_by_feature(self, feature_id: str) -> Optional[Window]:
        """Get window by feature ID."""
        for window in self._windows.values():
            if window.feature_id == feature_id:
                return window
        return None
    
    def get_windows_at_layer(self, layer: WindowLayer) -> List[Window]:
        """Get all windows at a specific layer."""
        return [w for w in self._windows.values() if w.layer == layer]
    
    def get_all_windows(self) -> List[Window]:
        """Get all windows in z-order (bottom to top)."""
        return [self._windows[wid] for wid in self._z_order if wid in self._windows]
    
    def get_visible_windows(self) -> List[Window]:
        """Get all visible windows in z-order."""
        return [w for w in self.get_all_windows() if w.visible]
    
    def get_focused_window(self) -> Optional[Window]:
        """Get currently focused window."""
        if self._focused_window and self._focused_window in self._windows:
            return self._windows[self._focused_window]
        return None
    
    def on(self, event: str, callback: Callable) -> None:
        """Register event callback."""
        self._callbacks[event].append(callback)
    
    def off(self, event: str, callback: Callable) -> None:
        """Unregister event callback."""
        if callback in self._callbacks[event]:
            self._callbacks[event].remove(callback)
    
    def _emit(self, event: str, *args) -> None:
        for callback in self._callbacks[event]:
            try:
                callback(*args)
            except Exception as e:
                print(f"WindowManager callback error: {e}")


# Layout management
class LayoutManager:
    """Manages window layouts and tiling."""
    
    def __init__(self, window_manager: WindowManager):
        self.window_manager = window_manager
        self._layouts: Dict[str, Callable] = {
            "tile": self._tile_windows,
            "cascade": self._cascade_windows,
            "grid": self._grid_windows,
            "side_by_side": self._side_by_side,
        }
    
    def apply_layout(self, layout_name: str, window_ids: List[str] = None,
                     screen_rect: Dict[str, int] = None) -> bool:
        """Apply a layout to windows."""
        if layout_name not in self._layouts:
            return False
        
        windows = []
        if window_ids:
            for wid in window_ids:
                w = self.window_manager.get_window(wid)
                if w and w.visible:
                    windows.append(w)
        else:
            windows = self.window_manager.get_visible_windows()
        
        if not windows:
            return False
        
        screen_rect = screen_rect or {"x": 0, "y": 0, "width": 1920, "height": 1080}
        
        self._layouts[layout_name](windows, screen_rect)
        return True
    
    def _tile_windows(self, windows: List[Window], screen_rect: Dict[str, int]) -> None:
        """Tile windows horizontally."""
        n = len(windows)
        if n == 0:
            return
        
        w = screen_rect["width"] // n
        for i, window in enumerate(windows):
            geom = WindowGeometry(
                x=screen_rect["x"] + i * w,
                y=screen_rect["y"],
                width=w,
                height=screen_rect["height"],
            )
            self.window_manager.set_window_geometry(window.window_id, geom)
            window.state = WindowState.NORMAL
            window.visible = True
    
    def _cascade_windows(self, windows: List[Window], screen_rect: Dict[str, int]) -> None:
        """Cascade windows with offset."""
        offset = 30
        for i, window in enumerate(windows):
            geom = WindowGeometry(
                x=screen_rect["x"] + i * offset,
                y=screen_rect["y"] + i * offset,
                width=min(800, screen_rect["width"] - 100),
                height=min(600, screen_rect["height"] - 100),
            )
            self.window_manager.set_window_geometry(window.window_id, geom)
            window.state = WindowState.NORMAL
            window.visible = True
    
    def _grid_windows(self, windows: List[Window], screen_rect: Dict[str, int]) -> None:
        """Arrange windows in a grid."""
        n = len(windows)
        if n == 0:
            return
        
        cols = int(n ** 0.5)
        if cols == 0:
            cols = 1
        rows = (n + cols - 1) // cols
        
        cell_w = screen_rect["width"] // cols
        cell_h = screen_rect["height"] // rows
        
        for i, window in enumerate(windows):
            row = i // cols
            col = i % cols
            geom = WindowGeometry(
                x=screen_rect["x"] + col * cell_w,
                y=screen_rect["y"] + row * cell_h,
                width=cell_w,
                height=cell_h,
            )
            self.window_manager.set_window_geometry(window.window_id, geom)
            window.state = WindowState.NORMAL
            window.visible = True
    
    def _side_by_side(self, windows: List[Window], screen_rect: Dict[str, int]) -> None:
        """Arrange two windows side by side."""
        if len(windows) != 2:
            self._tile_windows(windows, screen_rect)
            return
        
        half_w = screen_rect["width"] // 2
        for i, window in enumerate(windows):
            geom = WindowGeometry(
                x=screen_rect["x"] + i * half_w,
                y=screen_rect["y"],
                width=half_w,
                height=screen_rect["height"],
            )
            self.window_manager.set_window_geometry(window.window_id, geom)
            window.state = WindowState.NORMAL
            window.visible = True


# Multi-monitor support (stub)
class Monitor:
    """Represents a physical monitor."""
    
    def __init__(self, monitor_id: str, name: str, 
                 x: int, y: int, width: int, height: int,
                 is_primary: bool = False):
        self.monitor_id = monitor_id
        self.name = name
        self.geometry = WindowGeometry(x=x, y=y, width=width, height=height)
        self.is_primary = is_primary
        self.scale_factor = 1.0
        self.refresh_rate = 60


class MultiMonitorManager:
    """Manages multiple monitors (stub for future implementation)."""
    
    def __init__(self):
        self._monitors: Dict[str, Monitor] = {}
        self._primary_monitor: Optional[str] = None
    
    def add_monitor(self, monitor: Monitor) -> None:
        self._monitors[monitor.monitor_id] = monitor
        if monitor.is_primary or not self._primary_monitor:
            self._primary_monitor = monitor.monitor_id
    
    def remove_monitor(self, monitor_id: str) -> bool:
        if monitor_id in self._monitors:
            del self._monitors[monitor_id]
            if self._primary_monitor == monitor_id:
                self._primary_monitor = next(iter(self._monitors), None)
            return True
        return False
    
    def get_monitor(self, monitor_id: str) -> Optional[Monitor]:
        return self._monitors.get(monitor_id)
    
    def get_primary_monitor(self) -> Optional[Monitor]:
        if self._primary_monitor:
            return self._monitors.get(self._primary_monitor)
        return next(iter(self._monitors.values()), None)
    
    def get_all_monitors(self) -> List[Monitor]:
        return list(self._monitors.values())
    
    def get_virtual_screen_rect(self) -> Dict[str, int]:
        """Get bounding rectangle of all monitors."""
        if not self._monitors:
            return {"x": 0, "y": 0, "width": 1920, "height": 1080}
        
        min_x = min(m.geometry.x for m in self._monitors.values())
        min_y = min(m.geometry.y for m in self._monitors.values())
        max_x = max(m.geometry.x + m.geometry.width for m in self._monitors.values())
        max_y = max(m.geometry.y + m.geometry.height for m in self._monitors.values())
        
        return {
            "x": min_x,
            "y": min_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        }


# Demo
if __name__ == "__main__":
    wm = WindowManager()
    
    # Create some windows
    w1 = wm.create_window("feature-1", "mount-1", "Window 1", 
                          WindowGeometry(100, 100, 800, 600))
    w2 = wm.create_window("feature-2", "mount-2", "Window 2",
                          WindowGeometry(200, 200, 600, 400))
    w3 = wm.create_window("feature-3", "mount-3", "Window 3",
                          WindowGeometry(300, 300, 400, 300))
    
    print("All windows (z-order):")
    for w in wm.get_all_windows():
        print(f"  {w.window_id}: {w.title} (focused={w.focused})")
    
    print(f"\nFocused: {wm.get_focused_window().title}")
    
    # Test minimize/restore
    wm.minimize_window(w1.window_id)
    print(f"\nAfter minimize w1: {w1.state.value}, visible={w1.visible}")
    
    wm.restore_window(w1.window_id)
    print(f"After restore w1: {w1.state.value}, visible={w1.visible}")
    
    # Test layout manager
    layout = LayoutManager(wm)
    layout.apply_layout("tile", [w1.window_id, w2.window_id, w3.window_id])
    
    print("\nAfter tile layout:")
    for w in [w1, w2, w3]:
        print(f"  {w.window_id}: x={w.geometry.x}, y={w.geometry.y}, w={w.geometry.width}, h={w.geometry.height}")
    
    # Test multi-monitor
    mm = MultiMonitorManager()
    mm.add_monitor(Monitor("mon1", "Primary", 0, 0, 1920, 1080, True))
    mm.add_monitor(Monitor("mon2", "Secondary", 1920, 0, 1920, 1080))
    
    print(f"\nVirtual screen: {mm.get_virtual_screen_rect()}")
    print(f"Primary: {mm.get_primary_monitor().name}")