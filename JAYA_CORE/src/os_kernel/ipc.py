"""Phase 3B — IPC (Inter-Process Communication) for brain_v2 ↔ os_kernel.

This module provides the communication layer between the resident AI (brain_v2)
and the OS kernel (os_kernel) for dynamic feature management.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict


class MessageType(str, Enum):
    """IPC message types."""
    # Feature lifecycle
    FEATURE_COMPILE = "feature:compile"
    FEATURE_MOUNT = "feature:mount"
    FEATURE_UNMOUNT = "feature:unmount"
    FEATURE_LIST = "feature:list"
    FEATURE_STATUS = "feature:status"
    
    # Feature interaction
    FEATURE_DISPATCH = "feature:dispatch"
    FEATURE_STATE_GET = "feature:state:get"
    FEATURE_STATE_SET = "feature:state:set"
    
    # UI operations
    UI_NOTIFY = "ui:notify"
    UI_DIALOG_OPEN = "ui:dialog:open"
    UI_DIALOG_CLOSE = "ui:dialog:close"
    UI_FOCUS = "ui:focus"
    UI_SCROLL = "ui:scroll"
    
    # System operations
    SYS_RUN_TASK = "sys:run_task"
    SYS_CALL_API = "sys:call_api"
    SYS_EXEC_CODE = "sys:exec_code"
    SYS_SAVE_FILE = "sys:save_file"
    SYS_LOAD_FILE = "sys:load_file"
    SYS_OPEN_URL = "sys:open_url"
    SYS_CLIPBOARD = "sys:clipboard"
    
    # Events (kernel -> brain)
    EVENT_FEATURE_MOUNTED = "event:feature:mounted"
    EVENT_FEATURE_UNMOUNTED = "event:feature:unmounted"
    EVENT_FEATURE_ERROR = "event:feature:error"
    EVENT_WIDGET_ACTION = "event:widget:action"
    EVENT_STATE_CHANGED = "event:state:changed"
    EVENT_NOTIFICATION = "event:notification"
    
    # Control
    PING = "ping"
    PONG = "pong"
    ACK = "ack"
    NAK = "nak"


@dataclass
class IPCMessage:
    """IPC message envelope."""
    type: MessageType
    payload: Dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: Optional[str] = None
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    source: str = "unknown"
    target: str = "broadcast"
    
    def to_json(self) -> str:
        return json.dumps({
            "type": self.type.value,
            "payload": self.payload,
            "message_id": self.message_id,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "source": self.source,
            "target": self.target,
        })
    
    @classmethod
    def from_json(cls, json_str: str) -> "IPCMessage":
        data = json.loads(json_str)
        return cls(
            type=MessageType(data["type"]),
            payload=data.get("payload", {}),
            message_id=data.get("message_id", str(uuid.uuid4())),
            correlation_id=data.get("correlation_id"),
            timestamp=data.get("timestamp", datetime.now().timestamp()),
            source=data.get("source", "unknown"),
            target=data.get("target", "broadcast"),
        )
    
    @classmethod
    def create(cls, msg_type: MessageType, payload: Dict[str, Any] = None, 
               source: str = "brain_v2", target: str = "os_kernel",
               correlation_id: str = None) -> "IPCMessage":
        return cls(
            type=msg_type,
            payload=payload or {},
            source=source,
            target=target,
            correlation_id=correlation_id,
        )
    
    @classmethod
    def response(cls, request: "IPCMessage", success: bool, 
                 data: Any = None, error: str = "") -> "IPCMessage":
        return cls(
            type=MessageType.ACK if success else MessageType.NAK,
            payload={"success": success, "data": data, "error": error},
            correlation_id=request.message_id,
            source=request.target,
            target=request.source,
        )


class IPCChannel:
    """Abstract IPC channel for message transport."""
    
    async def send(self, message: IPCMessage) -> None:
        raise NotImplementedError
    
    async def receive(self) -> Optional[IPCMessage]:
        raise NotImplementedError
    
    async def close(self) -> None:
        pass


class InProcessIPCChannel(IPCChannel):
    """In-process IPC channel using asyncio queues (for same-process communication)."""
    
    def __init__(self):
        self._queues: Dict[str, asyncio.Queue] = defaultdict(asyncio.Queue)
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)
        self._broadcast_queue: asyncio.Queue = asyncio.Queue()
    
    async def send(self, message: IPCMessage) -> None:
        # Deliver to target's queue
        await self._queues[message.target].put(message)
        
        # Also deliver to broadcast queue for router
        await self._broadcast_queue.put(message)
        
        # Also deliver to subscribers of this message type
        for subscriber in self._subscriptions.get(message.type.value, set()):
            if subscriber != message.target:
                await self._queues[subscriber].put(message)
    
    async def receive(self, target: str = "os_kernel") -> Optional[IPCMessage]:
        if target == "router":
            # Router receives all messages via broadcast queue
            try:
                return await asyncio.wait_for(self._broadcast_queue.get(), timeout=0.1)
            except asyncio.TimeoutError:
                return None
        try:
            return await asyncio.wait_for(self._queues[target].get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None
    
    def subscribe(self, subscriber: str, message_types: List[MessageType]) -> None:
        for msg_type in message_types:
            self._subscriptions[msg_type.value].add(subscriber)
    
    def unsubscribe(self, subscriber: str, message_types: List[MessageType]) -> None:
        for msg_type in message_types:
            self._subscriptions[msg_type.value].discard(subscriber)


class IPCRouter:
    """Routes IPC messages between brain_v2 and os_kernel components."""
    
    def __init__(self, channel: IPCChannel):
        self.channel = channel
        self._handlers: Dict[MessageType, Callable] = {}
        self._running = False
        self._receive_task: Optional[asyncio.Task] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
    
    def register_handler(self, msg_type: MessageType, handler: Callable) -> None:
        """Register a handler for a message type."""
        self._handlers[msg_type] = handler
    
    def unregister_handler(self, msg_type: MessageType) -> None:
        self._handlers.pop(msg_type, None)
    
    async def start(self) -> None:
        """Start the message routing loop."""
        self._running = True
        self._receive_task = asyncio.create_task(self._receive_loop())
    
    async def stop(self) -> None:
        """Stop the message routing loop."""
        self._running = False
        if self._receive_task:
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass
        await self.channel.close()
    
    async def _receive_loop(self) -> None:
        while self._running:
            try:
                message = await self.channel.receive(target="router")
                if message:
                    await self._route_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"IPC receive error: {e}")
    
    async def _route_message(self, message: IPCMessage) -> None:
        # Check if this is a response to a pending request
        if message.correlation_id and message.correlation_id in self._pending_requests:
            future = self._pending_requests.pop(message.correlation_id)
            if not future.done():
                future.set_result(message)
            return
        
        # Route to handler
        handler = self._handlers.get(message.type)
        if handler:
            try:
                if asyncio.iscoroutinefunction(handler):
                    response = await handler(message)
                else:
                    response = handler(message)
                
                # Send response if this was a request (has message_id for correlation)
                # The request's message_id becomes the response's correlation_id
                if message.message_id and response:
                    # Ensure response has correct correlation_id (request's message_id)
                    if not response.correlation_id:
                        response.correlation_id = message.message_id
                    # Send response back to the original sender
                    await self.channel.send(response)
            except Exception as e:
                error_response = IPCMessage.response(message, False, error=str(e))
                await self.channel.send(error_response)
        else:
            # No handler - send NAK
            if message.message_id:
                nak = IPCMessage.response(message, False, error=f"No handler for {message.type.value}")
                await self.channel.send(nak)
    
    async def send_request(self, message: IPCMessage, timeout: float = 30.0) -> IPCMessage:
        """Send a request and wait for response."""
        future = asyncio.Future()
        self._pending_requests[message.message_id] = future
        
        await self.channel.send(message)
        
        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except asyncio.TimeoutError:
            self._pending_requests.pop(message.message_id, None)
            raise TimeoutError(f"Request {message.message_id} timed out")
    
    async def send_notification(self, msg_type: MessageType, payload: Dict[str, Any],
                                source: str = "os_kernel", target: str = "brain_v2") -> None:
        """Send a fire-and-forget notification."""
        message = IPCMessage.create(msg_type, payload, source=source, target=target)
        await self.channel.send(message)


# ============================================================
# High-level API for brain_v2
# ============================================================

class BrainIPCClient:
    """Client for brain_v2 to communicate with os_kernel."""
    
    def __init__(self, router: IPCRouter):
        self.router = router
    
    async def compile_feature(self, scene_json: str, feature_name: str = None,
                              output_dir: str = "./features") -> Dict[str, Any]:
        """Compile a SceneGraph to a feature package."""
        msg = IPCMessage.create(
            MessageType.FEATURE_COMPILE,
            {"scene": scene_json, "feature_name": feature_name, "output_dir": output_dir},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def mount_feature(self, feature_id: str, mount_point: str = "body",
                            config: Dict = None) -> Dict[str, Any]:
        """Mount a feature at a mount point."""
        msg = IPCMessage.create(
            MessageType.FEATURE_MOUNT,
            {"feature_id": feature_id, "mount_point": mount_point, "config": config or {}},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def unmount_feature(self, feature_id: str) -> Dict[str, Any]:
        """Unmount a feature."""
        msg = IPCMessage.create(
            MessageType.FEATURE_UNMOUNT,
            {"feature_id": feature_id},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def list_features(self) -> Dict[str, Any]:
        """List all discovered features."""
        msg = IPCMessage.create(
            MessageType.FEATURE_LIST,
            {},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def get_feature_status(self, feature_id: str) -> Dict[str, Any]:
        """Get status of a specific feature."""
        msg = IPCMessage.create(
            MessageType.FEATURE_STATUS,
            {"feature_id": feature_id},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def dispatch_feature_action(self, feature_id: str, action: str,
                                      payload: Dict = None) -> Dict[str, Any]:
        """Dispatch an action to a mounted feature."""
        msg = IPCMessage.create(
            MessageType.FEATURE_DISPATCH,
            {"feature_id": feature_id, "action": action, "payload": payload or {}},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def get_feature_state(self, feature_id: str) -> Dict[str, Any]:
        """Get feature state."""
        msg = IPCMessage.create(
            MessageType.FEATURE_STATE_GET,
            {"feature_id": feature_id},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def set_feature_state(self, feature_id: str, state: Dict) -> Dict[str, Any]:
        """Set feature state."""
        msg = IPCMessage.create(
            MessageType.FEATURE_STATE_SET,
            {"feature_id": feature_id, "state": state},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def notify(self, message: str, level: str = "info", duration: int = 5000) -> None:
        """Show a notification."""
        await self.router.send_notification(
            MessageType.UI_NOTIFY,
            {"message": message, "level": level, "duration": duration}
        )
    
    async def open_dialog(self, dialog_id: str, config: Dict = None) -> Dict[str, Any]:
        """Open a dialog."""
        msg = IPCMessage.create(
            MessageType.UI_DIALOG_OPEN,
            {"dialog_id": dialog_id, "config": config or {}},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def close_dialog(self, dialog_id: str) -> Dict[str, Any]:
        """Close a dialog."""
        msg = IPCMessage.create(
            MessageType.UI_DIALOG_CLOSE,
            {"dialog_id": dialog_id},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def run_task(self, code: str, label: str = "TASK") -> Dict[str, Any]:
        """Run a background task."""
        msg = IPCMessage.create(
            MessageType.SYS_RUN_TASK,
            {"code": code, "label": label},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def call_api(self, endpoint: str, method: str = "GET",
                       params: Dict = None, body: Any = None) -> Dict[str, Any]:
        """Call an external API."""
        msg = IPCMessage.create(
            MessageType.SYS_CALL_API,
            {"endpoint": endpoint, "method": method, "params": params, "body": body},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def execute_code(self, code: str, context: Dict = None) -> Dict[str, Any]:
        """Execute arbitrary code in kernel context."""
        msg = IPCMessage.create(
            MessageType.SYS_EXEC_CODE,
            {"code": code, "context": context or {}},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def save_file(self, path: str, content: str) -> Dict[str, Any]:
        """Save a file."""
        msg = IPCMessage.create(
            MessageType.SYS_SAVE_FILE,
            {"path": path, "content": content},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def load_file(self, path: str) -> Dict[str, Any]:
        """Load a file."""
        msg = IPCMessage.create(
            MessageType.SYS_LOAD_FILE,
            {"path": path},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def open_url(self, url: str) -> Dict[str, Any]:
        """Open a URL in browser."""
        msg = IPCMessage.create(
            MessageType.SYS_OPEN_URL,
            {"url": url},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload
    
    async def copy_to_clipboard(self, text: str) -> Dict[str, Any]:
        """Copy text to clipboard."""
        msg = IPCMessage.create(
            MessageType.SYS_CLIPBOARD,
            {"text": text, "action": "copy"},
            source="brain_v2", target="os_kernel"
        )
        response = await self.router.send_request(msg)
        return response.payload


# ============================================================
# High-level API for os_kernel
# ============================================================

class KernelIPCServer:
    """Server for os_kernel to handle requests from brain_v2."""
    
    def __init__(self, router: IPCRouter, feature_registry=None, jaya_bridge=None):
        self.router = router
        self.feature_registry = feature_registry
        self.jaya_bridge = jaya_bridge
        self._register_handlers()
    
    def _register_handlers(self) -> None:
        # Feature lifecycle
        self.router.register_handler(MessageType.FEATURE_COMPILE, self._handle_compile_feature)
        self.router.register_handler(MessageType.FEATURE_MOUNT, self._handle_mount_feature)
        self.router.register_handler(MessageType.FEATURE_UNMOUNT, self._handle_unmount_feature)
        self.router.register_handler(MessageType.FEATURE_LIST, self._handle_list_features)
        self.router.register_handler(MessageType.FEATURE_STATUS, self._handle_feature_status)
        
        # Feature interaction
        self.router.register_handler(MessageType.FEATURE_DISPATCH, self._handle_dispatch_feature)
        self.router.register_handler(MessageType.FEATURE_STATE_GET, self._handle_get_feature_state)
        self.router.register_handler(MessageType.FEATURE_STATE_SET, self._handle_set_feature_state)
        
        # UI operations
        self.router.register_handler(MessageType.UI_DIALOG_OPEN, self._handle_open_dialog)
        self.router.register_handler(MessageType.UI_DIALOG_CLOSE, self._handle_close_dialog)
        
        # System operations
        self.router.register_handler(MessageType.SYS_RUN_TASK, self._handle_run_task)
        self.router.register_handler(MessageType.SYS_CALL_API, self._handle_call_api)
        self.router.register_handler(MessageType.SYS_EXEC_CODE, self._handle_exec_code)
        self.router.register_handler(MessageType.SYS_SAVE_FILE, self._handle_save_file)
        self.router.register_handler(MessageType.SYS_LOAD_FILE, self._handle_load_file)
        self.router.register_handler(MessageType.SYS_OPEN_URL, self._handle_open_url)
        self.router.register_handler(MessageType.SYS_CLIPBOARD, self._handle_clipboard)
        
        # Ping
        self.router.register_handler(MessageType.PING, lambda m: IPCMessage.response(m, True, {"pong": True}))
    
    # Feature lifecycle handlers
    async def _handle_compile_feature(self, message: IPCMessage) -> IPCMessage:
        if not self.jaya_bridge:
            return IPCMessage.response(message, False, error="JayaBridge not available")
        
        try:
            # The client sends a scene JSON, not an intent string
            scene_json = message.payload.get("scene", "")
            feature_name = message.payload.get("feature_name")
            output_dir = message.payload.get("output_dir", "./features")
            
            # Parse scene JSON to SceneGraph
            from src.os_kernel.ui_spec import SceneGraph
            if isinstance(scene_json, str):
                scene = SceneGraph.from_json(scene_json)
            elif isinstance(scene_json, dict):
                scene = SceneGraph.from_dict(scene_json)
            else:
                scene = scene_json
            
            # Compile scene to feature
            from src.os_kernel.feature_compiler import compile_scene_to_feature
            output_path = compile_scene_to_feature(scene, output_dir, feature_name)
            
            result = {
                "success": True,
                "feature_path": str(output_path),
                "feature_id": scene.id,  # Use scene's UUID as feature_id for mounting
                "feature_name": output_path.name,
                "scene": scene.to_dict(),
            }
            return IPCMessage.response(message, True, result)
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))
    
    async def _handle_mount_feature(self, message: IPCMessage) -> IPCMessage:
        if not self.feature_registry:
            return IPCMessage.response(message, False, error="FeatureRegistry not available")
        
        try:
            instance = self.feature_registry.mount_feature(
                feature_id=message.payload["feature_id"],
                mount_point=message.payload.get("mount_point", "body"),
                config=message.payload.get("config", {}),
                jaya_bridge=self.jaya_bridge,
            )
            return IPCMessage.response(message, True, {
                "feature_id": instance.manifest.id,
                "mount_point": instance.mount_point,
                "status": instance.status.value,
            })
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))
    
    async def _handle_unmount_feature(self, message: IPCMessage) -> IPCMessage:
        if not self.feature_registry:
            return IPCMessage.response(message, False, error="FeatureRegistry not available")
        
        success = self.feature_registry.unmount_feature(message.payload["feature_id"])
        return IPCMessage.response(message, success)
    
    async def _handle_list_features(self, message: IPCMessage) -> IPCMessage:
        if not self.feature_registry:
            return IPCMessage.response(message, False, error="FeatureRegistry not available")
        
        features = self.feature_registry.list_discovered()
        return IPCMessage.response(message, True, {
            "features": [f.to_dict() for f in features],
            "count": len(features),
        })
    
    async def _handle_feature_status(self, message: IPCMessage) -> IPCMessage:
        if not self.feature_registry:
            return IPCMessage.response(message, False, error="FeatureRegistry not available")
        
        instance = self.feature_registry.get_instance(message.payload["feature_id"])
        if not instance:
            return IPCMessage.response(message, False, error="Feature not mounted")
        
        return IPCMessage.response(message, True, instance.to_dict())
    
    # Feature interaction handlers
    async def _handle_dispatch_feature(self, message: IPCMessage) -> IPCMessage:
        if not self.feature_registry:
            return IPCMessage.response(message, False, error="FeatureRegistry not available")
        
        instance = self.feature_registry.get_instance(message.payload["feature_id"])
        if not instance:
            return IPCMessage.response(message, False, error="Feature not mounted")
        
        try:
            # Try module-level dispatch function first (new compiled features)
            if hasattr(instance.module, "dispatch"):
                result = instance.module.dispatch(
                    message.payload["action"],
                    message.payload.get("payload", {})
                )
                return IPCMessage.response(message, True, result)
            # Try module's _runtime global (compiled features with global runtime)
            elif hasattr(instance.module, "_runtime") and instance.module._runtime is not None:
                result = instance.module._runtime.dispatch(
                    message.payload["action"],
                    message.payload.get("payload", {})
                )
                return IPCMessage.response(message, True, result)
            # Fallback: try FeatureRuntime dispatch if available
            elif hasattr(instance, "runtime") and hasattr(instance.runtime, "dispatch"):
                result = instance.runtime.dispatch(
                    message.payload["action"],
                    message.payload.get("payload", {})
                )
                return IPCMessage.response(message, True, result)
            return IPCMessage.response(message, False, error="Feature does not support dispatch")
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))
    
    async def _handle_get_feature_state(self, message: IPCMessage) -> IPCMessage:
        if not self.feature_registry:
            return IPCMessage.response(message, False, error="FeatureRegistry not available")
        
        instance = self.feature_registry.get_instance(message.payload["feature_id"])
        if not instance:
            return IPCMessage.response(message, False, error="Feature not mounted")
        
        return IPCMessage.response(message, True, instance.state)
    
    async def _handle_set_feature_state(self, message: IPCMessage) -> IPCMessage:
        if not self.feature_registry:
            return IPCMessage.response(message, False, error="FeatureRegistry not available")
        
        instance = self.feature_registry.get_instance(message.payload["feature_id"])
        if not instance:
            return IPCMessage.response(message, False, error="Feature not mounted")
        
        instance.state.update(message.payload.get("state", {}))
        
        # Notify feature if it has a state handler
        if hasattr(instance.module, "on_state_change"):
            instance.module.on_state_change(instance.state)
        
        return IPCMessage.response(message, True, instance.state)
    
    # UI handlers
    async def _handle_open_dialog(self, message: IPCMessage) -> IPCMessage:
        dialog_id = message.payload.get("dialog_id")
        config = message.payload.get("config", {})
        
        # Emit event for UI layer
        await self.router.send_notification(
            MessageType.EVENT_FEATURE_MOUNTED,
            {"dialog_id": dialog_id, "config": config},
            source="os_kernel", target="brain_v2"
        )
        
        return IPCMessage.response(message, True, {"dialog_id": dialog_id})
    
    async def _handle_close_dialog(self, message: IPCMessage) -> IPCMessage:
        dialog_id = message.payload.get("dialog_id")
        
        await self.router.send_notification(
            MessageType.EVENT_FEATURE_UNMOUNTED,
            {"dialog_id": dialog_id},
            source="os_kernel", target="brain_v2"
        )
        
        return IPCMessage.response(message, True, {"dialog_id": dialog_id})
    
    # System handlers
    async def _handle_run_task(self, message: IPCMessage) -> IPCMessage:
        code = message.payload.get("code", "")
        label = message.payload.get("label", "TASK")
        
        # This would integrate with the twin/task system
        task_id = str(uuid.uuid4())
        
        return IPCMessage.response(message, True, {
            "task_id": task_id,
            "message": f"Task '{label}' queued",
        })
    
    async def _handle_call_api(self, message: IPCMessage) -> IPCMessage:
        # Would integrate with actual HTTP client
        return IPCMessage.response(message, True, {"status": "not_implemented"})
    
    async def _handle_exec_code(self, message: IPCMessage) -> IPCMessage:
        # SECURITY: This should be heavily restricted or removed in production
        code = message.payload.get("code", "")
        context = message.payload.get("context", {})
        
        try:
            # Execute in restricted context
            local_vars = {"__builtins__": {}, **context}
            exec(code, local_vars)
            return IPCMessage.response(message, True, {"result": "executed"})
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))
    
    async def _handle_save_file(self, message: IPCMessage) -> IPCMessage:
        path = message.payload.get("path", "")
        content = message.payload.get("content", "")
        
        try:
            from pathlib import Path
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text(content, encoding="utf-8")
            return IPCMessage.response(message, True, {"path": path})
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))
    
    async def _handle_load_file(self, message: IPCMessage) -> IPCMessage:
        path = message.payload.get("path", "")
        
        try:
            from pathlib import Path
            content = Path(path).read_text(encoding="utf-8")
            return IPCMessage.response(message, True, {"content": content})
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))
    
    async def _handle_open_url(self, message: IPCMessage) -> IPCMessage:
        url = message.payload.get("url", "")
        
        try:
            import webbrowser
            webbrowser.open(url)
            return IPCMessage.response(message, True, {"url": url})
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))
    
    async def _handle_clipboard(self, message: IPCMessage) -> IPCMessage:
        text = message.payload.get("text", "")
        action = message.payload.get("action", "copy")
        
        try:
            import pyperclip
            if action == "copy":
                pyperclip.copy(text)
            elif action == "paste":
                text = pyperclip.paste()
            return IPCMessage.response(message, True, {"text": text})
        except Exception as e:
            return IPCMessage.response(message, False, error=str(e))


# ============================================================
# Factory functions
# ============================================================

def create_ipc_system(feature_registry=None, jaya_bridge=None) -> tuple[IPCRouter, BrainIPCClient, KernelIPCServer]:
    """Create a complete IPC system with router, client, and server."""
    channel = InProcessIPCChannel()
    router = IPCRouter(channel)
    client = BrainIPCClient(router)
    server = KernelIPCServer(router, feature_registry=feature_registry, jaya_bridge=jaya_bridge)
    return router, client, server


async def demo():
    """Demo the IPC system."""
    router, client, server = create_ipc_system()
    
    # Start router
    await router.start()
    
    try:
        # Test ping
        msg = IPCMessage.create(MessageType.PING, {}, source="brain_v2", target="os_kernel")
        response = await router.send_request(msg)
        print(f"Ping response: {response.payload}")
        
        # Test feature list
        result = await client.list_features()
        print(f"Features: {result}")
        
    finally:
        await router.stop()


if __name__ == "__main__":
    asyncio.run(demo())