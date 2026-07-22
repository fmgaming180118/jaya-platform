# Phase OS-3: IPC Bridge + Protocol

## Objective
Implement structured, typed communication between Brain (JAYA_CORE), House (JAYA_OS), Features, and Apps (JAYA_AGENT).

---

## Scope
- **In scope**: IPC Channel (Unix sockets/Named pipes), Message Router, Protocol Schemas, 4 Channels, Request-Response, Security
- **Out of scope**: Hardware Abstraction (OS-4), Sandbox Hardening (OS-5)

---

## Prerequisites
- ✅ OS-1 complete (standalone JAYA_OS package)
- ✅ OS-2 complete (WindowManager + Widget Runtime working)

---

## Deliverables

| # | Deliverable | File/Location | Status |
|---|---|---|---|
| 1 | IPC Channel (Unix sockets / Named pipes) | `src/jaya_os/ipc.py` | 🔄 Planned |
| 2 | Message Router (channel + type dispatch) | `src/jaya_os/ipc_router.py` | 🔄 Planned |
| 3 | Protocol Schemas (Pydantic models) | `src/jaya_os/ipc_protocol.py` | 🔄 Planned |
| 4 | Brain Channel (spec.ui, spec.feature, spec.task, spec.action) | `src/jaya_os/channels/brain.py` | 🔄 Planned |
| 5 | Features Channel (mount, unmount, action, state, event) | `src/jaya_os/channels/features.py` | 🔄 Planned |
| 6 | System Channel (shutdown, restart, status, config) | `src/jaya_os/channels/system.py` | 🔄 Planned |
| 7 | Monitor Channel (metrics, trace, health) | `src/jaya_os/channels/monitor.py` | 🔄 Planned |
| 8 | Request-Response pattern (correlation_id) | `src/jaya_os/ipc_client.py` | 🔄 Planned |
| 9 | Security (auth, authz, encryption) | `src/jaya_os/ipc_security.py` | 🔄 Planned |
| 10 | Unit tests | `tests/test_ipc.py`, etc. | 🔄 Planned |
| 11 | Integration tests | `tests/test_ipc_integration.py` | 🔄 Planned |

---

## Technical Implementation

### 3.1 Transport Layer

```python
# src/jaya_os/ipc.py
import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Any
from pathlib import Path
import sys

@dataclass
class IPCMessage:
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: __import__('datetime').datetime.utcnow().isoformat() + 'Z')
    version: str = "1.0"
    channel: str = ""
    msg_type: str = ""
    payload: Dict = field(default_factory=dict)
    correlation_id: Optional[str] = None
    reply_to: Optional[str] = None
    metadata: Dict = field(default_factory=dict)

class IPCChannel:
    def __init__(self, channel_name: str, socket_path: str = None):
        self.channel_name = channel_name
        self.socket_path = socket_path or self._default_socket_path(channel_name)
        self.handlers: Dict[str, Callable] = {}
        self.server = None
        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._pending_requests: Dict[str, asyncio.Future] = {}
    
    def _default_socket_path(self, channel: str) -> str:
        if sys.platform == "win32":
            return f"\\\\.\\pipe\\jaya_os_{channel}"
        else:
            return f"/tmp/jaya_os_{channel}.sock"
    
    async def start_server(self):
        """Start IPC server."""
        if sys.platform == "win32":
            # Named pipes on Windows
            self.server = await asyncio.start_unix_server(
                self._handle_client, self.socket_path
            )
        else:
            # Unix domain sockets on Linux/macOS
            self.server = await asyncio.start_unix_server(
                self._handle_client, self.socket_path
            )
    
    async def connect(self):
        """Connect to IPC server."""
        if sys.platform == "win32":
            # Windows named pipe connection
            import win32file
            import pywintypes
            # Simplified - would need proper async named pipe implementation
            pass
        else:
            self.reader, self.writer = await asyncio.open_unix_connection(
                self.socket_path
            )
    
    def register_handler(self, msg_type: str, handler: Callable):
        self.handlers[msg_type] = handler
    
    async def send(self, msg_type: str, payload: Dict, 
                   correlation_id: str = None, reply_to: str = None) -> bool:
        """Send message to channel."""
        message = IPCMessage(
            channel=self.channel_name,
            msg_type=msg_type,
            payload=payload,
            correlation_id=correlation_id,
            reply_to=reply_to
        )
        
        if self.writer:
            data = json.dumps(message.__dict__).encode() + b'\n'
            self.writer.write(data)
            await self.writer.drain()
            return True
        return False
    
    async def request(self, msg_type: str, payload: Dict, 
                      timeout: float = 30.0) -> Optional[Dict]:
        """Send request and wait for response."""
        correlation_id = str(uuid.uuid4())
        reply_channel = f"{self.channel_name}.reply"
        
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[correlation_id] = future
        
        await self.send(msg_type, payload, correlation_id, reply_channel)
        
        try:
            response = await asyncio.wait_for(future, timeout)
            return response
        except asyncio.TimeoutError:
            return None
        finally:
            self._pending_requests.pop(correlation_id, None)
    
    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        while True:
            line = await reader.readline()
            if not line:
                break
            try:
                data = json.loads(line.decode())
                message = IPCMessage(**data)
                
                # Check if this is a response to a pending request
                if message.correlation_id and message.correlation_id in self._pending_requests:
                    future = self._pending_requests.pop(message.correlation_id)
                    future.set_result(message.payload)
                    continue
                
                # Handle as request
                handler = self.handlers.get(message.msg_type)
                if handler:
                    try:
                        result = await handler(message.payload)
                        # Send response if correlation_id provided
                        if message.correlation_id and message.reply_to:
                            reply_msg = IPCMessage(
                                channel=message.reply_to,
                                msg_type=f"{message.msg_type}.result",
                                payload=result,
                                correlation_id=message.correlation_id
                            )
                            writer.write(json.dumps(reply_msg.__dict__).encode() + b'\n')
                            await writer.drain()
                    except Exception as e:
                        error_result = {"error": str(e), "success": False}
                        if message.correlation_id and message.reply_to:
                            reply_msg = IPCMessage(
                                channel=message.reply_to,
                                msg_type=f"{message.msg_type}.error",
                                payload=error_result,
                                correlation_id=message.correlation_id
                            )
                            writer.write(json.dumps(reply_msg.__dict__).encode() + b'\n')
                            await writer.drain()
            except json.JSONDecodeError:
                pass  # Ignore malformed messages
```

### 3.2 Protocol Schemas (Pydantic Models)

```python
# src/jaya_os/ipc_protocol.py
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any, Literal
from datetime import datetime
from uuid import UUID, uuid4
from enum import Enum

class Channel(str, Enum):
    BRAIN = "brain"
    FEATURES = "features"
    SYSTEM = "system"
    MONITOR = "monitor"

class MessageType(str, Enum):
    # Brain channel
    SPEC_UI = "spec.ui"
    SPEC_FEATURE = "spec.feature"
    SPEC_TASK = "spec.task"
    SPEC_ACTION = "spec.action"
    SPEC_RESULT = "spec.result"
    RESOURCE_UPDATE = "resource.update"
    
    # Features channel
    FEATURE_MOUNT = "feature.mount"
    FEATURE_UNMOUNT = "feature.unmount"
    FEATURE_ACTION = "feature.action"
    FEATURE_STATE = "feature.state"
    FEATURE_EVENT = "feature.event"
    FEATURE_ERROR = "feature.error"
    
    # System channel
    SYSTEM_SHUTDOWN = "system.shutdown"
    SYSTEM_RESTART = "system.restart"
    SYSTEM_STATUS = "system.status"
    SYSTEM_CONFIG = "system.config"
    SYSTEM_LOG = "system.log"
    
    # Monitor channel
    MONITOR_METRICS = "monitor.metrics"
    MONITOR_TRACE = "monitor.trace"
    MONITOR_HEALTH = "monitor.health"

class IPCEnvelope(BaseModel):
    msg_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = "1.0"
    channel: Channel
    msg_type: MessageType
    payload: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[UUID] = None
    reply_to: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

# Brain Channel Payloads
class SceneGraphPayload(BaseModel):
    name: str
    description: str
    version: str = "1.0"
    root: Dict[str, Any]  # WidgetSpec
    metadata: Dict[str, Any] = Field(default_factory=dict)

class FeatureManifestPayload(BaseModel):
    name: str
    version: str
    entry_point: str
    permissions: List[str] = Field(default_factory=list)
    dependencies: List[str] = Field(default_factory=list)
    ui_spec: Optional[SceneGraphPayload] = None
    config_schema: Dict[str, Any] = Field(default_factory=dict)

class ExecutionPlanPayload(BaseModel):
    steps: List[Dict[str, Any]]
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    parallel_groups: List[List[str]] = Field(default_factory=list)
    estimated_latency_ms: float
    required_resources: Dict[str, float] = Field(default_factory=dict)
    priority: int = 0

class ActionSpecPayload(BaseModel):
    channel: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)

class ExecutionResultPayload(BaseModel):
    success: bool
    output: Optional[Any] = None
    error: Optional[str] = None
    latency_ms: float
    cache_hit: bool = False

class ResourceReadingsPayload(BaseModel):
    cpu_pct: float
    mem_pct: float
    battery_pct: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# Features Channel Payloads
class FeatureMountPayload(BaseModel):
    feature_id: str
    config: Dict[str, Any] = Field(default_factory=dict)

class FeatureUnmountPayload(BaseModel):
    feature_id: str

class FeatureActionPayload(BaseModel):
    feature_id: str
    action: str
    payload: Dict[str, Any] = Field(default_factory=dict)

class FeatureStatePayload(BaseModel):
    feature_id: str
    state: Dict[str, Any]

class FeatureEventPayload(BaseModel):
    feature_id: str
    event_type: str
    data: Dict[str, Any] = Field(default_factory=dict)

class FeatureErrorPayload(BaseModel):
    feature_id: str
    error: str
    traceback: Optional[str] = None

# System Channel Payloads
class SystemConfigPayload(BaseModel):
    key: str
    value: Any

class SystemLogPayload(BaseModel):
    level: Literal["debug", "info", "warning", "error"]
    message: str
    source: str

# Monitor Channel Payloads
class MetricsSnapshotPayload(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    cpu_pct: float
    mem_pct: float
    battery_pct: float
    feature_count: int
    mounted_features: int
    ipc_throughput: float

class TraceEventPayload(BaseModel):
    trace_id: UUID
    span_id: UUID
    parent_span_id: Optional[UUID] = None
    operation: str
    start_time: datetime
    end_time: datetime
    tags: Dict[str, str] = Field(default_factory=dict)

class HealthCheckPayload(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    checks: Dict[str, bool]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### 3.3 Channel Implementations

```python
# src/jaya_os/channels/brain.py
from jaya_os.ipc import IPCChannel, IPCMessage
from jaya_os.ipc_protocol import (
    Channel, MessageType, SceneGraphPayload, FeatureManifestPayload,
    ExecutionPlanPayload, ActionSpecPayload, ExecutionResultPayload,
    ResourceReadingsPayload
)
from jaya_os.feature_bridge import JayaBridge
from jaya_os.intent_to_ui import IntentToUIPipeline
from jaya_os.feature_compiler import FeatureCompiler
from jaya_os.feature_registry import FeatureRegistry

class BrainChannel:
    def __init__(self, bridge: JayaBridge, pipeline: IntentToUIPipeline,
                 compiler: FeatureCompiler, registry: FeatureRegistry):
        self.channel = IPCChannel(Channel.BRAIN.value)
        self.bridge = bridge
        self.pipeline = pipeline
        self.compiler = compiler
        self.registry = registry
        self._register_handlers()
    
    def _register_handlers(self):
        self.channel.register_handler(MessageType.SPEC_UI, self._handle_ui_spec)
        self.channel.register_handler(MessageType.SPEC_FEATURE, self._handle_feature_spec)
        self.channel.register_handler(MessageType.SPEC_TASK, self._handle_task_spec)
        self.channel.register_handler(MessageType.SPEC_ACTION, self._handle_action_spec)
    
    async def _handle_ui_spec(self, payload: Dict) -> Dict:
        """Handle UI spec from brain: compile and mount."""
        scene_graph = SceneGraphPayload(**payload)
        # Convert to internal SceneGraph
        from jaya_os.ui_spec import SceneGraph
        scene = SceneGraph(**scene_graph.dict())
        
        # Compile and mount
        feature_name = scene.name.lower().replace(" ", "_")
        output_path = self.compiler.save_feature(scene, "./features", feature_name)
        
        # Mount via bridge
        feature_id = self.bridge.mount_feature(feature_name)
        
        return {"success": True, "feature_id": feature_id, "path": output_path}
    
    async def _handle_feature_spec(self, payload: Dict) -> Dict:
        """Handle feature spec from brain."""
        manifest = FeatureManifestPayload(**payload)
        # Register feature
        from jaya_os.feature_registry import FeatureManifest
        feature_manifest = FeatureManifest(**manifest.dict())
        self.registry.register(feature_manifest)
        
        # Mount if requested
        feature_id = self.bridge.mount_feature(manifest.name)
        
        return {"success": True, "feature_id": feature_id}
    
    async def _handle_task_spec(self, payload: Dict) -> Dict:
        """Handle task spec from brain: schedule for execution."""
        plan = ExecutionPlanPayload(**payload)
        # Schedule task (would integrate with task scheduler)
        task_id = str(uuid.uuid4())
        # self.task_scheduler.schedule(plan, task_id)
        
        return {"success": True, "task_id": task_id}
    
    async def _handle_action_spec(self, payload: Dict) -> Dict:
        """Handle direct action spec from brain."""
        action = ActionSpecPayload(**payload)
        # Dispatch via IPC
        from jaya_os.ipc import dispatch_ipc
        result = dispatch_ipc(action.channel, action.action, action.payload)
        return {"success": True, "result": result}
    
    async def send_resource_update(self, readings: ResourceReadingsPayload):
        """Send resource readings to brain."""
        await self.channel.send(
            MessageType.RESOURCE_UPDATE,
            readings.dict()
        )
```

```python
# src/jaya_os/channels/features.py
from jaya_os.ipc import IPCChannel
from jaya_os.ipc_protocol import Channel, MessageType
from jaya_os.feature_bridge import JayaBridge

class FeaturesChannel:
    def __init__(self, bridge: JayaBridge):
        self.channel = IPCChannel(Channel.FEATURES.value)
        self.bridge = bridge
        self._register_handlers()
    
    def _register_handlers(self):
        self.channel.register_handler(MessageType.FEATURE_MOUNT, self._handle_mount)
        self.channel.register_handler(MessageType.FEATURE_UNMOUNT, self._handle_unmount)
        self.channel.register_handler(MessageType.FEATURE_ACTION, self._handle_action)
        self.channel.register_handler(MessageType.FEATURE_STATE, self._handle_state)
    
    async def _handle_mount(self, payload: Dict) -> Dict:
        feature_id = payload.get("feature_id")
        config = payload.get("config", {})
        instance = self.bridge.mount_feature(feature_id, config)
        return {"success": True, "instance_id": instance.feature_id}
    
    async def _handle_unmount(self, payload: Dict) -> Dict:
        feature_id = payload.get("feature_id")
        success = self.bridge.unmount_feature(feature_id)
        return {"success": success}
    
    async def _handle_action(self, payload: Dict) -> Dict:
        feature_id = payload.get("feature_id")
        action = payload.get("action")
        action_payload = payload.get("payload", {})
        result = self.bridge.dispatch_action(feature_id, action, action_payload)
        return {"success": True, "result": result}
    
    async def _handle_state(self, payload: Dict) -> Dict:
        feature_id = payload.get("feature_id")
        state = payload.get("state", {})
        # Update feature state
        instance = self.bridge.mounted.get(feature_id)
        if instance:
            instance.state.update(state)
        return {"success": True}
    
    async def emit_event(self, feature_id: str, event_type: str, data: Dict):
        """Emit feature event to brain."""
        await self.channel.send(
            MessageType.FEATURE_EVENT,
            {"feature_id": feature_id, "event_type": event_type, "data": data}
        )
    
    async def emit_error(self, feature_id: str, error: str, traceback: str = None):
        """Emit feature error."""
        await self.channel.send(
            MessageType.FEATURE_ERROR,
            {"feature_id": feature_id, "error": error, "traceback": traceback}
        )
```

```python
# src/jaya_os/channels/system.py
from jaya_os.ipc import IPCChannel
from jaya_os.ipc_protocol import Channel, MessageType

class SystemChannel:
    def __init__(self):
        self.channel = IPCChannel(Channel.SYSTEM.value)
        self._register_handlers()
    
    def _register_handlers(self):
        self.channel.register_handler(MessageType.SYSTEM_SHUTDOWN, self._handle_shutdown)
        self.channel.register_handler(MessageType.SYSTEM_RESTART, self._handle_restart)
        self.channel.register_handler(MessageType.SYSTEM_STATUS, self._handle_status)
        self.channel.register_handler(MessageType.SYSTEM_CONFIG, self._handle_config)
    
    async def _handle_shutdown(self, payload: Dict) -> Dict:
        # Trigger graceful shutdown
        import sys
        sys.exit(0)
        return {"success": True}
    
    async def _handle_restart(self, payload: Dict) -> Dict:
        # Trigger restart
        import os
        import sys
        os.execv(sys.executable, [sys.executable] + sys.argv)
        return {"success": True}
    
    async def _handle_status(self, payload: Dict) -> Dict:
        # Return system status
        return {
            "success": True,
            "status": "running",
            "uptime": 0,  # Would track actual uptime
            "features_mounted": 0,
            "memory_usage": 0
        }
    
    async def _handle_config(self, payload: Dict) -> Dict:
        key = payload.get("key")
        value = payload.get("value")
        # Update config
        return {"success": True}
    
    async def log(self, level: str, message: str, source: str = "system"):
        """Send log entry to agents."""
        await self.channel.send(
            MessageType.SYSTEM_LOG,
            {"level": level, "message": message, "source": source}
        )
```

### 3.4 IPC Client for External Use

```python
# src/jaya_os/ipc_client.py
from jaya_os.ipc import IPCChannel
from jaya_os.ipc_protocol import Channel, MessageType, IPCEnvelope
from typing import Dict, Optional, Any
import uuid

class IPCClient:
    def __init__(self, channel: Channel):
        self.channel = IPCChannel(channel.value)
        self.connected = False
    
    async def connect(self):
        await self.channel.connect()
        self.connected = True
    
    async def disconnect(self):
        if self.channel.writer:
            self.channel.writer.close()
            await self.channel.writer.wait_closed()
        self.connected = False
    
    # Brain channel methods
    async def send_ui_spec(self, scene_graph: Dict) -> Dict:
        return await self.channel.request(MessageType.SPEC_UI, scene_graph)
    
    async def send_feature_spec(self, manifest: Dict) -> Dict:
        return await self.channel.request(MessageType.SPEC_FEATURE, manifest)
    
    async def send_task_spec(self, plan: Dict) -> Dict:
        return await self.channel.request(MessageType.SPEC_TASK, plan)
    
    async def send_action_spec(self, action: Dict) -> Dict:
        return await self.channel.request(MessageType.SPEC_ACTION, action)
    
    # Features channel methods
    async def mount_feature(self, feature_id: str, config: Dict = None) -> Dict:
        return await self.channel.request(
            MessageType.FEATURE_MOUNT, 
            {"feature_id": feature_id, "config": config or {}}
        )
    
    async def unmount_feature(self, feature_id: str) -> Dict:
        return await self.channel.request(
            MessageType.FEATURE_UNMOUNT, 
            {"feature_id": feature_id}
        )
    
    async def dispatch_action(self, feature_id: str, action: str, payload: Dict) -> Dict:
        return await self.channel.request(
            MessageType.FEATURE_ACTION,
            {"feature_id": feature_id, "action": action, "payload": payload}
        )
    
    # System channel methods
    async def shutdown(self) -> Dict:
        return await self.channel.request(MessageType.SYSTEM_SHUTDOWN, {})
    
    async def restart(self) -> Dict:
        return await self.channel.request(MessageType.SYSTEM_RESTART, {})
    
    async def get_status(self) -> Dict:
        return await self.channel.request(MessageType.SYSTEM_STATUS, {})
    
    async def set_config(self, key: str, value: Any) -> Dict:
        return await self.channel.request(
            MessageType.SYSTEM_CONFIG, {"key": key, "value": value}
        )
```

---

## Security

```python
# src/jaya_os/ipc_security.py
import os
import sys
from typing import Callable, Dict, Optional
from jaya_os.ipc import IPCChannel, IPCMessage
from jaya_os.ipc_protocol import Channel

class IPCSecurity:
    def __init__(self):
        self.allowed_channels: Dict[Channel, Callable] = {}
    
    def validate_connection(self, channel: Channel, peer_pid: int) -> bool:
        """Validate peer process is allowed to connect to channel."""
        # Check if peer is JAYA_CORE, JAYA_AGENT, or trusted feature
        allowed_processes = {
            Channel.BRAIN: ["jayacore", "python"],
            Channel.FEATURES: ["jayaos", "python"],
            Channel.SYSTEM: ["jayaagent", "python"],
            Channel.MONITOR: ["jayaos", "jayacore", "jayaagent", "python"],
        }
        
        # Get process name from PID
        try:
            import psutil
            proc = psutil.Process(peer_pid)
            proc_name = proc.name().lower()
            allowed = allowed_processes.get(channel, [])
            return any(a in proc_name for a in allowed)
        except:
            return False
    
    def validate_message(self, message: IPCMessage, peer_pid: int) -> bool:
        """Validate message is allowed for channel."""
        # Check message type is valid for channel
        valid_types = {
            Channel.BRAIN: ["spec.ui", "spec.feature", "spec.task", "spec.action"],
            Channel.FEATURES: ["feature.mount", "feature.unmount", "feature.action", "feature.state"],
            Channel.SYSTEM: ["system.shutdown", "system.restart", "system.status", "system.config"],
            Channel.MONITOR: ["monitor.metrics", "monitor.trace", "monitor.health"],
        }
        
        allowed = valid_types.get(message.channel, [])
        return message.msg_type in allowed
    
    def get_peer_credentials(self, reader: asyncio.StreamReader) -> Optional[Dict]:
        """Get peer process credentials (Linux: SO_PEERCRED, Windows: GetNamedPipeClientProcessId)."""
        if sys.platform == "win32":
            # Windows named pipe - would need win32api
            return None
        else:
            # Linux: SO_PEERCRED
            import socket
            sock = reader._transport.get_extra_info('socket')
            if sock:
                creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
                import struct
                pid, uid, gid = struct.unpack('3i', creds)
                return {"pid": pid, "uid": uid, "gid": gid}
        return None
```

---

## Verification Checklist

### Functional
- [ ] All 4 channels operational (brain, features, system, monitor)
- [ ] Request-response pattern works with correlation_id
- [ ] Message schemas validated (Pydantic)
- [ ] Brain → OS: spec.ui, spec.feature, spec.task, spec.action
- [ ] OS → Brain: spec.result, resource.update
- [ ] OS ↔ Features: mount, unmount, action, state, event, error
- [ ] Agent ↔ OS: shutdown, restart, status, config, log
- [ ] Security: auth, authz, message validation

### Performance
- [ ] 10,000 msg/s throughput
- [ ] Latency p50 < 1ms, p99 < 10ms
- [ ] Connection establishment < 10ms
- [ ] Memory usage < 50MB for IPC

### Quality
- [ ] Unit tests for each channel
- [ ] Integration tests: Brain → OS → Feature
- [ ] Load test: 10,000 concurrent messages
- [ ] Security tests: unauthorized access blocked
- [ ] Chaos tests: connection loss, reconnection

---

## Success Criteria
- [ ] All 4 channels operational
- [ ] Request-response pattern works
- [ ] 10,000 msg/s throughput
- [ ] Latency p50 < 1ms, p99 < 10ms
- [ ] Authentication/authorization enforced
- [ ] Schema validation on all messages
- [ ] Integration test passes

---

## Handoff to OS-4

**Contract**: OS-3 provides:
- IPCChannel with Unix sockets/Named pipes
- MessageRouter with channel + type dispatch
- 4 Channels with typed message schemas
- Request-response pattern with correlation_id
- Security (auth, authz, validation)

**Files for OS-4**:
- `src/jaya_os/hardware/` (display, input, audio, storage, network)

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [Runtime Features](../03-features/runtime-features.md)
- [UI Runtime](../03-features/ui-runtime.md)
- [Roadmap Overview](../06-roadmap/README.md)