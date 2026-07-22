# IPC Bridge — JAYA_OS

## Overview

The IPC (Inter-Process Communication) Bridge enables structured communication between:

- **JAYA_CORE (Brain)** ↔ **JAYA_OS (House)**
- **JAYA_AGENT (Apps)** ↔ **JAYA_OS (House)**
- **Features** ↔ **JAYA_OS (House)**

All communication uses **JSON messages** over named channels with typed message schemas.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            IPC BRIDGE                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                  │
│  │   Channel    │    │   Channel    │    │   Channel    │                  │
│  │  "brain"     │    │  "features"  │    │   "system"   │                  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                  │
│         │                   │                   │                           │
│         ▼                   ▼                   ▼                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                    Message Router                                    │   │
│  │  • Route by channel + message_type                                   │   │
│  │  • Validate schema                                                   │   │
│  │  • Dispatch to registered handlers                                   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Channels

| Channel | Purpose | Participants |
|---|---|---|
| `brain` | Brain ↔ House spec exchange | JAYA_CORE → JAYA_OS |
| `features` | Feature lifecycle & actions | Features ↔ JAYA_OS |
| `system` | System commands & events | JAYA_AGENT ↔ JAYA_OS |
| `monitor` | Resource & health monitoring | All → JAYA_OS |

---

## Message Format

All messages are JSON with this envelope:

```json
{
  "msg_id": "uuid-v4",
  "timestamp": "2026-07-21T10:30:00.000Z",
  "channel": "brain",
  "msg_type": "spec.ui",
  "payload": { ... },
  "correlation_id": "optional-uuid",
  "reply_to": "optional-channel"
}
```

---

## Message Types

### Brain Channel (`brain`)

| Message Type | Direction | Payload | Description |
|---|---|---|---|
| `spec.ui` | Brain → House | `SceneGraph` | UI specification to compile & mount |
| `spec.feature` | Brain → House | `FeatureManifest` | Feature specification to compile & mount |
| `spec.task` | Brain → House | `ExecutionPlan` | Task specification to schedule |
| `spec.action` | Brain → House | `ActionSpec` | Direct action to execute |
| `spec.result` | House → Brain | `ExecutionResult` | Result of spec execution |
| `resource.update` | House → Brain | `ResourceReadings` | CPU/RAM/Battery readings |

### Features Channel (`features`)

| Message Type | Direction | Payload | Description |
|---|---|---|---|
| `feature.mount` | House → Feature | `{feature_id, config}` | Mount feature in sandbox |
| `feature.unmount` | House → Feature | `{feature_id}` | Unmount feature |
| `feature.action` | House → Feature | `{action, payload}` | Dispatch action to feature |
| `feature.state` | Feature → House | `{feature_id, state}` | Feature state update |
| `feature.event` | Feature → House | `{event_type, data}` | Feature emits event |
| `feature.error` | Feature → House | `{feature_id, error}` | Feature error report |

### System Channel (`system`)

| Message Type | Direction | Payload | Description |
|---|---|---|---|
| `system.shutdown` | Agent → House | `{}` | Request graceful shutdown |
| `system.restart` | Agent → House | `{}` | Request restart |
| `system.status` | Agent → House | `{}` | Request status |
| `system.config` | Agent → House | `{key, value}` | Update config |
| `system.log` | House → Agent | `{level, message}` | Log entry |

---

## API

### IPCChannel
```python
class IPCChannel:
    def __init__(self, channel_name: str):
        self.channel_name = channel_name
        self.handlers: Dict[str, Callable] = {}
    
    def send(self, message: Dict) -> bool:
        """Send message to channel."""
        ...
    
    def receive(self, timeout: float = 5.0) -> Optional[Dict]:
        """Receive message from channel."""
        ...
    
    def register_handler(self, msg_type: str, handler: Callable) -> None:
        """Register handler for message type."""
        ...
    
    def unregister_handler(self, msg_type: str) -> None:
        """Unregister handler."""
        ...
```

### Global IPC Registry
```python
# Register a channel
def register_ipc_channel(channel: IPCChannel) -> None:
    ...

# Get channel by name
def get_ipc_channel(name: str) -> IPCChannel:
    ...

# Register handler for channel + message type
def register_ipc_handler(channel: str, msg_type: str, handler: Callable) -> None:
    ...

# Dispatch message
def dispatch_ipc(channel: str, msg_type: str, payload: Dict) -> Any:
    ...
```

---

## Usage Examples

### Brain → House: Send UI Spec
```python
from src.os_kernel.ipc import dispatch_ipc

scene_graph = {
    "name": "login_dialog",
    "description": "Login form",
    "root": {
        "id": "root",
        "type": "window",
        "props": {"title": "Login", "width": "400px", "height": "300px"},
        "children": [...]
    }
}

dispatch_ipc("brain", "spec.ui", scene_graph)
```

### House → Feature: Mount Feature
```python
from src.os_kernel.ipc import dispatch_ipc

dispatch_ipc("features", "feature.mount", {
    "feature_id": "login_dialog_123",
    "config": {"theme": "dark"}
})
```

### Feature → House: Emit Event
```python
# Inside feature code
from src.os_kernel.ipc import dispatch_ipc

def handle_submit(payload):
    # ... process ...
    dispatch_ipc("features", "feature.event", {
        "feature_id": "login_dialog_123",
        "event_type": "login_success",
        "data": {"user": "admin", "token": "abc123"}
    })
    return {"success": True}
```

### Agent → House: System Command
```python
from src.os_kernel.ipc import dispatch_ipc

# Request system status
dispatch_ipc("system", "system.status", {})

# Update config
dispatch_ipc("system", "system.config", {"key": "theme", "value": "dark"})
```

---

## Handler Registration

### In JAYA_OS (House)
```python
from src.os_kernel.ipc import register_ipc_handler, get_ipc_channel

# Handle UI spec from brain
def handle_ui_spec(payload):
    pipeline = get_intent_to_ui_pipeline()
    result = pipeline.compile_and_mount(payload)
    return {"feature_id": result.feature_id}

register_ipc_handler("brain", "spec.ui", handle_ui_spec)

# Handle feature action
def handle_feature_action(payload):
    feature_id = payload["feature_id"]
    action = payload["action"]
    data = payload["payload"]
    bridge = get_jaya_bridge()
    return bridge.dispatch_action(feature_id, action, data)

register_ipc_handler("features", "feature.action", handle_feature_action)
```

### In Feature (Sandboxed)
```python
# Feature code has limited IPC access
from src.os_kernel.ipc import dispatch_ipc

# Can only send to "features" channel
def on_button_click():
    dispatch_ipc("features", "feature.event", {
        "feature_id": FEATURE_ID,
        "event_type": "button_click",
        "data": {"button": "submit"}
    })
```

---

## Security

| Mechanism | Description |
|---|---|
| **Channel isolation** | Features can only use `features` channel |
| **Message validation** | All messages validated against schema |
| **Capability checks** | Features must declare permissions in manifest |
| **Rate limiting** | Max 100 messages/sec per feature |
| **Size limits** | Max 1MB per message |

---

## Testing

```bash
# IPC tests
python -m pytest tests/ -k "ipc" -v

# Channel tests
python -m pytest tests/ -k "channel" -v

# Integration tests
python -m pytest tests/ -k "ipc_integration" -v
```

---

## 🔗 Related Docs

- [Runtime Features](../03-features/runtime-features.md) — FeatureCompiler, Registry, Bridge
- [UI Runtime](../03-features/ui-runtime.md) — WindowManager, Widget Runtime
- [Sandbox Security](../03-features/sandbox-security.md) — Capability-based permissions
- [Architecture Overview](../02-architecture/overview.md)
- [API Reference](../02-architecture/api-reference.md)