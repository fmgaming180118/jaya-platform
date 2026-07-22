# IPC Protocol Design — JAYA_OS

## Overview

The IPC (Inter-Process Communication) protocol enables structured, typed communication between JAYA_CORE (Brain), JAYA_OS (House), JAYA_AGENT (Apps), and mounted Features.

---

## Design Principles

1. **Typed Messages** — Every message has a schema (JSON Schema / Pydantic)
2. **Channel-based** — Messages routed by channel + message type
3. **Async-first** — Non-blocking send/receive with timeouts
4. **Schema Evolution** — Versioned messages, backward compatible
5. **Observability** — All messages loggable, traceable

---

## Transport Layer Options

### Option 1: Unix Domain Sockets / Named Pipes (Recommended)
- **Windows**: Named Pipes (`\\.\pipe\jaya_os_*`)
- **Linux/macOS**: Unix Domain Sockets (`/tmp/jaya_os_*.sock`)
- **Pros**: Fast, reliable, kernel-managed, supports credentials
- **Cons**: Local only (no network)

### Option 2: TCP Loopback
- **Port**: 127.0.0.1:50000-50100 (dynamic allocation)
- **Pros**: Network transparent, debuggable
- **Cons**: Port conflicts, firewall, slower

### Option 3: Shared Memory + Eventfd (High Performance)
- **Mechanism**: mmap + eventfd for signaling
- **Pros**: Zero-copy, ultra-low latency
- **Cons**: Complex, platform-specific, no network

### Decision: **Unix Domain Sockets / Named Pipes** as primary, with TCP fallback for remote debugging.

---

## Message Envelope

```json
{
  "msg_id": "550e8400-e29b-41d4-a716-446655440000",
  "timestamp": "2026-07-21T10:30:00.123Z",
  "version": "1.0",
  "channel": "brain",
  "msg_type": "spec.ui",
  "payload": { ... },
  "correlation_id": "optional-uuid-for-request-response",
  "reply_to": "optional-channel-for-reply",
  "metadata": {
    "source": "jayacore",
    "destination": "jayaos",
    "priority": "normal"
  }
}
```

### Field Definitions

| Field | Type | Required | Description |
|---|---|---|---|
| `msg_id` | UUID v4 | Yes | Globally unique message identifier |
| `timestamp` | ISO 8601 UTC | Yes | Message creation time |
| `version` | string | Yes | Protocol version (semver) |
| `channel` | string | Yes | Routing channel |
| `msg_type` | string | Yes | Message type within channel |
| `payload` | object | Yes | Message-specific data |
| `correlation_id` | UUID v4 | No | Links request/response |
| `reply_to` | string | No | Channel for reply |
| `metadata` | object | No | Additional routing info |

---

## Channel Definitions

### 1. `brain` — JAYA_CORE ↔ JAYA_OS

**Purpose**: Brain emits specs; House executes and returns results.

| Message Type | Direction | Payload Schema | Description |
|---|---|---|---|
| `spec.ui` | Core → OS | `SceneGraph` | UI specification to compile & mount |
| `spec.feature` | Core → OS | `FeatureManifest` | Feature specification to compile & mount |
| `spec.task` | Core → OS | `ExecutionPlan` | Task specification to schedule |
| `spec.action` | Core → OS | `ActionSpec` | Direct action to execute |
| `spec.result` | OS → Core | `ExecutionResult` | Result of spec execution |
| `resource.update` | OS → Core | `ResourceReadings` | CPU/RAM/Battery readings |

### 2. `features` — JAYA_OS ↔ Mounted Features

**Purpose**: Feature lifecycle management and action dispatch.

| Message Type | Direction | Payload Schema | Description |
|---|---|---|---|
| `feature.mount` | OS → Feature | `{feature_id, config}` | Mount feature in sandbox |
| `feature.unmount` | OS → Feature | `{feature_id}` | Unmount feature |
| `feature.action` | OS → Feature | `{action, payload}` | Dispatch action to feature |
| `feature.state` | Feature → OS | `{feature_id, state}` | Feature state update |
| `feature.event` | Feature → OS | `{event_type, data}` | Feature emits event |
| `feature.error` | Feature → OS | `{feature_id, error}` | Feature error report |

### 3. `system` — JAYA_AGENT ↔ JAYA_OS

**Purpose**: System-level commands and status.

| Message Type | Direction | Payload Schema | Description |
|---|---|---|---|
| `system.shutdown` | Agent → OS | `{}` | Request graceful shutdown |
| `system.restart` | Agent → OS | `{}` | Request restart |
| `system.status` | Agent → OS | `{}` | Request status |
| `system.config` | Agent → OS | `{key, value}` | Update config |
| `system.log` | OS → Agent | `{level, message}` | Log entry |

### 4. `monitor` — All → JAYA_OS

**Purpose**: Health, metrics, debugging.

| Message Type | Direction | Payload Schema | Description |
|---|---|---|---|
| `monitor.metrics` | Any → OS | `MetricsSnapshot` | Periodic metrics |
| `monitor.trace` | Any → OS | `TraceEvent` | Distributed trace |
| `monitor.health` | Any → OS | `HealthCheck` | Health status |

---

## Payload Schemas

### SceneGraph (spec.ui)
```json
{
  "name": "login_dialog",
  "description": "Login form",
  "version": "1.0",
  "root": {
    "id": "root",
    "type": "window",
    "props": {"title": "Login", "width": "400px", "height": "300px"},
    "children": [...]
  }
}
```

### FeatureManifest (spec.feature)
```json
{
  "name": "data_processor",
  "version": "1.0",
  "entry_point": "features.data_processor:run",
  "permissions": ["fs_read", "cpu_compute"],
  "dependencies": [],
  "config_schema": {"input_path": "string", "output_path": "string"}
}
```

### ExecutionPlan (spec.task)
```json
{
  "steps": [
    {"id": "step1", "action": "load_data", "params": {"path": "input.csv"}},
    {"id": "step2", "action": "transform", "params": {"method": "normalize"}}
  ],
  "dependencies": {"step2": ["step1"]},
  "parallel_groups": [["step1"], ["step2"]],
  "estimated_latency_ms": 500,
  "required_resources": {"cpu_percent": 10, "memory_mb": 100}
}
```

### ActionSpec (spec.action)
```json
{
  "channel": "system",
  "action": "shutdown",
  "payload": {}
}
```

### ExecutionResult (spec.result)
```json
{
  "correlation_id": "uuid",
  "success": true,
  "output": {"feature_id": "login_dialog_123"},
  "error": null,
  "latency_ms": 45.2
}
```

### ResourceReadings (resource.update)
```json
{
  "cpu_pct": 25.3,
  "mem_pct": 45.1,
  "battery_pct": 87.0,
  "timestamp": "2026-07-21T10:30:00.123Z"
}
```

---

## Request-Response Pattern

For synchronous operations, use `correlation_id` and `reply_to`:

```python
# Request
{
  "msg_id": "req-123",
  "channel": "brain",
  "msg_type": "spec.ui",
  "payload": {...},
  "correlation_id": "corr-456",
  "reply_to": "brain.reply"
}

# Response (sent to "brain.reply" channel)
{
  "msg_id": "resp-789",
  "channel": "brain.reply",
  "msg_type": "spec.result",
  "payload": {...},
  "correlation_id": "corr-456"
}
```

---

## Error Handling

### Transport Errors
- Connection lost → Reconnect with exponential backoff
- Message too large → Split or reject (max 1MB)
- Timeout → Retry or fail based on policy

### Schema Errors
- Invalid payload → Return `error.schema` with details
- Unknown message type → Return `error.unknown_type`
- Version mismatch → Return `error.version`

### Application Errors
- Feature execution error → `feature.error` message
- Spec validation error → `spec.result` with `success: false`

---

## Security

### Authentication
- Local sockets: Peer credentials (SO_PEERCRED on Linux, GetNamedPipeClientProcessId on Windows)
- Only trusted processes (same user, known paths) can connect

### Authorization
- Channel-based: Brain can only send to `brain` channel
- Feature can only send to `features` channel
- Agent can only send to `system` channel

### Encryption
- Local: Not encrypted (kernel-enforced isolation)
- Remote (if TCP): TLS 1.3 with mutual auth

---

## Implementation

### Python IPC Channel
```python
class IPCChannel:
    def __init__(self, channel_name: str, socket_path: str):
        self.channel_name = channel_name
        self.socket_path = socket_path
        self.handlers: Dict[str, Callable] = {}
        self.server = None
        self.client = None
    
    async def start_server(self):
        self.server = await asyncio.start_unix_server(
            self._handle_client, self.socket_path
        )
    
    async def connect(self):
        self.reader, self.writer = await asyncio.open_unix_connection(
            self.socket_path
        )
    
    def register_handler(self, msg_type: str, handler: Callable):
        self.handlers[msg_type] = handler
    
    async def send(self, msg_type: str, payload: dict, 
                   correlation_id: str = None, reply_to: str = None):
        envelope = create_envelope(self.channel_name, msg_type, payload,
                                   correlation_id, reply_to)
        self.writer.write(json.dumps(envelope).encode() + b'\n')
        await self.writer.drain()
    
    async def _handle_client(self, reader, writer):
        while True:
            line = await reader.readline()
            if not line:
                break
            envelope = json.loads(line.decode())
            handler = self.handlers.get(envelope['msg_type'])
            if handler:
                await handler(envelope)
```

---

## Testing

```bash
# Unit tests for message schemas
python -m pytest tests/ -k "ipc_schema" -v

# Integration tests
python -m pytest tests/ -k "ipc_integration" -v

# Load test
python scripts/ipc_load_test.py --messages 10000 --concurrent 100
```

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md)
- [Runtime Features](../03-features/runtime-features.md) — JayaBridge uses IPC
- [UI Runtime](../03-features/ui-runtime.md) — Event loop uses IPC
- [Roadmap OS-3](../06-roadmap/os-3-ipc-bridge.md)