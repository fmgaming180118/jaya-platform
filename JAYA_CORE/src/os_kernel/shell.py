"""Phase 3B — Shell Integration for Feature-Aware OS Shell.

This module provides the shell layer that integrates with the feature system,
allowing dynamic feature mounting, window management, and user interaction.
"""

from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from src.os_kernel.feature_bridge import JayaBridge
from src.os_kernel.feature_registry import get_feature_registry
from src.os_kernel.ipc import (
    BrainIPCClient,
    InProcessIPCChannel,
    IPCRouter,
    KernelIPCServer,
)
from src.os_kernel.ui_spec import SceneGraph


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


class Shell:
    """Main shell integrating window management, feature system, and IPC."""

    def __init__(self, features_dir: str = "./features"):
        self.features_dir = features_dir
        self.window_manager = WindowManager()
        self.feature_registry = get_feature_registry(features_dir)

        # IPC system
        self.ipc_router: Optional[IPCRouter] = None
        self.brain_client: Optional[BrainIPCClient] = None
        self.kernel_server: Optional[KernelIPCServer] = None
        self.jaya_bridge: Optional[JayaBridge] = None

        # State
        self._running = False
        self._mount_point_counter = 0

        # Register window manager callbacks
        self.window_manager.on("window_created", self._on_window_created)
        self.window_manager.on("window_closed", self._on_window_closed)
        self.window_manager.on("window_focused", self._on_window_focused)

    async def start(self) -> None:
        """Start the shell and IPC system."""
        # Create IPC system
        channel = InProcessIPCChannel()
        self.ipc_router = IPCRouter(channel)
        self.brain_client = BrainIPCClient(self.ipc_router)
        self.kernel_server = KernelIPCServer(
            self.ipc_router,
            feature_registry=self.feature_registry,
            jaya_bridge=self.jaya_bridge,
        )

        # Create JayaBridge
        self.jaya_bridge = JayaBridge(features_dir=self.features_dir)
        self.kernel_server.jaya_bridge = self.jaya_bridge

        # Start IPC router
        await self.ipc_router.start()

        # Discover features
        self.feature_registry.discover_features()

        self._running = True
        print("Shell started")

    async def stop(self) -> None:
        """Stop the shell."""
        self._running = False

        # Close all windows
        for window in self.window_manager.get_all_windows():
            self.window_manager.close_window(window.window_id)

        # Stop IPC
        if self.ipc_router:
            await self.ipc_router.stop()

        print("Shell stopped")

    # Feature integration
    async def mount_feature(self, feature_id: str, title: str = "",
                            geometry: WindowGeometry = None,
                            layer: WindowLayer = WindowLayer.NORMAL,
                            config: Dict = None) -> Optional[Window]:
        """Mount a feature and create a window for it."""
        # Mount feature via registry
        mount_point = f"mount-{self._mount_point_counter}"
        self._mount_point_counter += 1

        instance = self.feature_registry.mount_feature(
            feature_id=feature_id,
            mount_point=mount_point,
            config=config or {},
            jaya_bridge=self.jaya_bridge,
        )

        if instance.status.value != "mounted":
            print(f"Failed to mount feature: {instance.status.value}")
            return None

        # Create window
        feature_name = instance.manifest.name
        window = self.window_manager.create_window(
            feature_id=feature_id,
            mount_point=mount_point,
            title=title or feature_name,
            geometry=geometry,
            layer=layer,
        )

        # Notify brain_v2 via IPC
        if self.brain_client:
            await self.brain_client.notify(
                f"Feature '{feature_name}' mounted at {mount_point}",
                level="success"
            )

        return window

    async def unmount_feature(self, feature_id: str) -> bool:
        """Unmount a feature and close its window."""
        window = self.window_manager.get_window_by_feature(feature_id)
        if window:
            self.window_manager.close_window(window.window_id)

        success = self.feature_registry.unmount_feature(feature_id)

        if success and self.brain_client:
            await self.brain_client.notify(
                f"Feature {feature_id[:8]} unmounted",
                level="info"
            )

        return success

    async def compile_and_mount(self, scene: SceneGraph, feature_name: str = None,
                                title: str = "", geometry: WindowGeometry = None,
                                layer: WindowLayer = WindowLayer.NORMAL) -> Optional[Window]:
        """Compile a SceneGraph to feature and mount it."""
        # Compile
        from src.os_kernel.feature_compiler import compile_scene_to_feature
        compile_scene_to_feature(scene, self.features_dir, feature_name)

        # Discover new feature
        self.feature_registry.discover_features()

        # Find the new feature
        features = self.feature_registry.list_discovered()
        new_feature = None
        for f in features:
            if f.name == (feature_name or scene.name):
                new_feature = f
                break

        if not new_feature:
            print("Failed to find compiled feature")
            return None

        # Mount
        return await self.mount_feature(new_feature.id, title, geometry, layer)

    # Window operations
    def get_window(self, window_id: str) -> Optional[Window]:
        return self.window_manager.get_window(window_id)

    def get_all_windows(self) -> List[Window]:
        return self.window_manager.get_all_windows()

    def get_visible_windows(self) -> List[Window]:
        return self.window_manager.get_visible_windows()

    def focus_window(self, window_id: str) -> bool:
        return self.window_manager.focus_window(window_id)

    def close_window(self, window_id: str) -> bool:
        window = self.window_manager.get_window(window_id)
        if window:
            # Also unmount feature
            asyncio.create_task(self.unmount_feature(window.feature_id))
        return self.window_manager.close_window(window_id)

    # Event callbacks
    def _on_window_created(self, window: Window) -> None:
        print(f"Window created: {window.window_id} ({window.title})")

    def _on_window_closed(self, window: Window) -> None:
        print(f"Window closed: {window.window_id} ({window.title})")

    def _on_window_focused(self, window: Window) -> None:
        print(f"Window focused: {window.window_id} ({window.title})")

    # Shell status
    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self._running,
            "windows": len(self.window_manager._windows),
            "visible_windows": len(self.window_manager.get_visible_windows()),
            "focused_window": self.window_manager.get_focused_window().window_id if self.window_manager.get_focused_window() else None,
            "features_mounted": len(self.feature_registry._instances),
            "features_discovered": len(self.feature_registry._discovered),
        }


# ============================================================
# Integration with brain_v2
# ============================================================

class ShellIntegration:
    """Integrates shell with brain_v2 runtime."""

    def __init__(self, shell: Shell, brain_engine=None):
        self.shell = shell
        self.brain_engine = brain_engine
        self._intent_handlers = {}

    def register_intent_handler(self, intent: str, handler: Callable) -> None:
        """Register a handler for a specific intent."""
        self._intent_handlers[intent] = handler

    async def handle_intent(self, intent: str, params: Dict = None) -> Dict[str, Any]:
        """Handle an intent from brain_v2."""
        handler = self._intent_handlers.get(intent)
        if handler:
            return await handler(params or {})

        # Default handlers for common intents
        if intent == "create_window":
            return await self._handle_create_window(params or {})
        elif intent == "close_window":
            return await self._handle_close_window(params or {})
        elif intent == "focus_window":
            return await self._handle_focus_window(params or {})
        elif intent == "list_windows":
            return await self._handle_list_windows(params or {})
        elif intent == "compile_feature":
            return await self._handle_compile_feature(params or {})
        elif intent == "mount_feature":
            return await self._handle_mount_feature(params or {})
        elif intent == "unmount_feature":
            return await self._handle_unmount_feature(params or {})

        return {"success": False, "error": f"Unknown intent: {intent}"}

    async def _handle_create_window(self, params: Dict) -> Dict[str, Any]:
        from src.os_kernel.ui_spec import WindowGeometry
        geometry = None
        if "geometry" in params:
            geometry = WindowGeometry.from_dict(params["geometry"])

        window = self.shell.window_manager.create_window(
            feature_id=params.get("feature_id", "unknown"),
            mount_point=params.get("mount_point", "body"),
            title=params.get("title", ""),
            geometry=geometry,
            layer=WindowLayer(params.get("layer", "normal")),
        )
        return {"success": True, "window": window.to_dict()}

    async def _handle_close_window(self, params: Dict) -> Dict[str, Any]:
        window_id = params.get("window_id")
        if window_id:
            success = self.shell.window_manager.close_window(window_id)
            return {"success": success}
        return {"success": False, "error": "window_id required"}

    async def _handle_focus_window(self, params: Dict) -> Dict[str, Any]:
        window_id = params.get("window_id")
        if window_id:
            success = self.shell.window_manager.focus_window(window_id)
            return {"success": success}
        return {"success": False, "error": "window_id required"}

    async def _handle_list_windows(self, params: Dict) -> Dict[str, Any]:
        windows = [w.to_dict() for w in self.shell.window_manager.get_all_windows()]
        return {"success": True, "windows": windows}

    async def _handle_compile_feature(self, params: Dict) -> Dict[str, Any]:
        scene_json = params.get("scene")
        feature_name = params.get("feature_name")
        if not scene_json:
            return {"success": False, "error": "scene required"}

        from src.os_kernel.ui_spec import SceneGraph
        scene = SceneGraph.from_json(scene_json)
        output_path = compile_scene_to_feature(scene, self.shell.features_dir, feature_name)
        return {"success": True, "feature_path": str(output_path)}

    async def _handle_mount_feature(self, params: Dict) -> Dict[str, Any]:
        feature_id = params.get("feature_id")
        if not feature_id:
            return {"success": False, "error": "feature_id required"}

        window = await self.shell.mount_feature(
            feature_id=feature_id,
            title=params.get("title", ""),
            geometry=WindowGeometry.from_dict(params["geometry"]) if "geometry" in params else None,
            layer=WindowLayer(params.get("layer", "normal")),
            config=params.get("config"),
        )
        if window:
            return {"success": True, "window": window.to_dict()}
        return {"success": False, "error": "Failed to mount feature"}

    async def _handle_unmount_feature(self, params: Dict) -> Dict[str, Any]:
        feature_id = params.get("feature_id")
        if not feature_id:
            return {"success": False, "error": "feature_id required"}

        success = await self.shell.unmount_feature(feature_id)
        return {"success": success}


# ============================================================
# Demo
# ============================================================

async def demo():
    """Demo the shell system."""
    shell = Shell(features_dir="./test_features")
    await shell.start()

    try:
        # List discovered features
        features = shell.feature_registry.list_discovered()
        print(f"Discovered features: {len(features)}")
        for f in features:
            print(f"  - {f.name} ({f.id[:8]})")

        # Mount a feature if available
        if features:
            window = await shell.mount_feature(features[0].id, title="Test Window")
            if window:
                print(f"Mounted feature in window: {window.window_id}")

                # Test window operations
                shell.window_manager.minimize_window(window.window_id)
                print(f"Minimized: {window.state.value}")

                shell.window_manager.restore_window(window.window_id)
                print(f"Restored: {window.state.value}")

                shell.window_manager.maximize_window(window.window_id)
                print(f"Maximized: {window.state.value}")

                shell.window_manager.restore_window(window.window_id)
                print(f"Restored: {window.state.value}")

        # Test shell integration
        integration = ShellIntegration(shell)
        result = await integration.handle_intent("list_windows", {})
        print(f"Windows: {result}")

    finally:
        await shell.stop()


if __name__ == "__main__":
    asyncio.run(demo())
