# Roadmap — JAYA_OS

## Overview

```
OS-1 (1-2 wks)  →  OS-2 (2-3 wks)  →  OS-3 (2-3 wks)  →  OS-4 (3-4 wks)  →  OS-5 (Ongoing)
Extract          Window Manager     IPC Bridge         Hardware          Sandbox
os_kernel        + Widget Runtime   + Protocol         Abstraction       Hardening
```

---

## Phase Summary

| Phase | Focus | Duration | Key Deliverable |
|---|---|---|---|
| **OS-1** | Extract os_kernel to standalone JAYA_OS | 1-2 wks | Independent JAYA_OS repo with build system |
| **OS-2** | Window Manager + Widget Runtime | 2-3 wks | Native UI rendering, event loop |
| **OS-3** | IPC Bridge + Protocol | 2-3 wks | Structured Brain↔House↔Feature communication |
| **OS-4** | Hardware Abstraction Layer | 3-4 wks | Cross-platform (Windows, Linux, macOS) |
| **OS-5** | Sandbox Hardening | Ongoing | Process isolation, WASM, formal verification |

---

## Cross-Cutting Concerns (All Phases)

| Concern | Implementation |
|---|---|
| **Security** | Capability-based sandbox, signed manifests, audit logging |
| **Observability** | Structured logging, metrics, distributed tracing |
| **Testing** | Unit + integration + fuzz tests per component |
| **Documentation** | API docs, architecture decisions, runbooks |
| **CI/CD** | Automated tests, benchmark gates, artifact publishing |

---

## Phase OS-1: Extract os_kernel (1-2 weeks)

### Objective
Extract `os_kernel` from `JAYA_CORE` into standalone `JAYA_OS` project with independent build, test, and release pipeline.

### Prerequisites
- JAYA_CORE os_kernel modules stable (FeatureCompiler, FeatureRegistry, JayaBridge, IntentToUIPipeline, UI Spec)
- Phase 3C complete (Intent → UI Pipeline working)

### Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | Independent JAYA_OS repository structure | 🔄 Planned |
| 2 | `pyproject.toml` / `setup.py` with dependencies | 🔄 Planned |
| 3 | Build system (wheel, sdist) | 🔄 Planned |
| 4 | CI/CD pipeline (tests, lint, type-check) | 🔄 Planned |
| 5 | Documentation site (mkdocs/sphinx) | 🔄 Planned |
| 6 | Release automation (GitHub Actions) | 🔄 Planned |
| 7 | Migration guide from JAYA_CORE/os_kernel | 🔄 Planned |

### Technical Tasks

#### 1.1 Repository Structure
```
JAYA_OS/
├── pyproject.toml
├── README.md
├── LICENSE
├── src/
│   └── jaya_os/
│       ├── __init__.py
│       ├── feature_compiler.py
│       ├── feature_registry.py
│       ├── feature_bridge.py
│       ├── intent_to_ui.py
│       ├── ui_spec.py
│       ├── ipc.py
│       └── window_manager.py
├── tests/
├── scripts/
├── docs/
└── config/
```

#### 1.2 Dependencies
```toml
# pyproject.toml
[project]
name = "jaya-os"
version = "0.1.0"
description = "JAYA OS - The House (Execution Environment)"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.0",
    "numpy>=1.24",
    "psutil>=5.9",
    "requests>=2.31",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.1",
    "mypy>=1.5",
    "ruff>=0.1",
    "mkdocs>=1.5",
]
```

#### 1.3 Migration from JAYA_CORE
- Copy `JAYA_CORE/src/os_kernel/` → `JAYA_OS/src/jaya_os/`
- Update imports: `from src.os_kernel` → `from jaya_os`
- Update JAYA_CORE to depend on `jaya-os` package
- Run all Phase 3C tests to verify

### Verification
```bash
# Build
pip install -e .

# Test
python -m pytest tests/ -v

# Phase 3C regression
python -m pytest tests/test_phase3c_intent_to_ui.py -v

# Build wheel
pip wheel . -w dist/
```

### Success Criteria
- [ ] JAYA_OS builds independently
- [ ] All Phase 3C tests pass
- [ ] JAYA_CORE can import `jaya_os` as dependency
- [ ] CI/CD passes on push
- [ ] Documentation site deploys

---

## Phase OS-2: Window Manager + Widget Runtime (2-3 weeks)

### Objective
Implement native UI rendering: WindowManager, Widget Runtime, Layout Engine, Style System, Event Loop.

### Prerequisites
- OS-1 complete (standalone JAYA_OS)
- UI Spec (SceneGraph, WidgetSpec) stable

### Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | WindowManager (Win32 backend) | 🔄 Planned |
| 2 | WindowManager (X11 backend) | 🔄 Planned |
| 3 | Widget Runtime (16 widget types) | 🔄 Planned |
| 4 | Layout Engine (Flexbox + Grid) | 🔄 Planned |
| 5 | Style System (StyleTokens) | 🔄 Planned |
| 6 | Event Loop (mouse, keyboard, focus) | 🔄 Planned |
| 7 | Data Binding (reactive) | 🔄 Planned |
| 8 | Integration with JayaBridge | 🔄 Planned |

### Technical Tasks

#### 2.1 WindowManager
```python
# Windows: Win32 API via ctypes
# Linux: X11 via python-xlib
# macOS: Deferred (XQuartz initially)

class WindowManager:
    def create_window(self, spec: WidgetSpec) -> WindowHandle
    def destroy_window(self, handle: WindowHandle) -> bool
    def bring_to_front(self, handle: WindowHandle)
    def set_focus(self, handle: WindowHandle)
    def get_window_state(self, handle: WindowHandle) -> WindowState
    def set_window_state(self, handle: WindowHandle, state: WindowState)
```

#### 2.2 Widget Runtime
```python
# 16 widget types:
# WINDOW, PANEL, BUTTON, LABEL, TEXT_INPUT, TEXTAREA,
# SELECT, CHECKBOX, RADIO, SLIDER, PROGRESS, LIST,
# TABLE, CHART, IMAGE, TAB, SPLITTER

class WidgetRuntime:
    def render(self, window_handle: WindowHandle, spec: WidgetSpec)
    def update_widget(self, widget_id: str, props: Dict)
    def handle_event(self, event: NativeEvent) -> bool
```

#### 2.3 Layout Engine
```python
class LayoutEngine:
    def flex_layout(self, children: List[WidgetSpec], container: Rect, direction: LayoutType)
    def grid_layout(self, children: List[WidgetSpec], container: Rect, rows: int, cols: int)
    def absolute_layout(self, children: List[WidgetSpec], container: Rect)
```

#### 2.4 Style System
```python
@dataclass
class StyleTokens:
    # Colors, spacing, typography, borders, shadows, transitions
    color_primary: str = "#0066CC"
    spacing_unit: str = "8px"
    font_family: str = "Inter, system-ui, sans-serif"
    border_radius: str = "8px"
    shadow_elevation_1: str = "0 1px 3px rgba(0,0,0,0.1)"
    transition_normal: str = "250ms ease"
```

#### 2.5 Event Loop
```python
class EventLoop:
    def run(self)
    def stop(self)
    def post_event(self, event: Event)
    def register_hotkey(self, key: str, callback: Callable)
```

### Verification
```bash
# Unit tests
python -m pytest tests/ -k "window_manager" -v
python -m pytest tests/ -k "widget_runtime" -v
python -m pytest tests/ -k "layout_engine" -v
python -m pytest tests/ -k "event_loop" -v

# Integration
python -m pytest tests/ -k "ui_integration" -v

# Manual test: run demo app
python scripts/demo_ui.py
```

### Success Criteria
- [ ] Window creates, shows, hides, closes on Windows + Linux
- [ ] All 16 widget types render correctly
- [ ] Flexbox + Grid layouts work
- [ ] Style tokens applied correctly
- [ ] Mouse/keyboard events dispatch to JayaBridge
- [ ] Data binding updates UI reactively
- [ ] 60fps rendering for simple UIs

---

## Phase OS-3: IPC Bridge + Protocol (2-3 weeks)

### Objective
Implement structured, typed communication between Brain, House, Features, and Apps.

### Prerequisites
- OS-1 complete
- OS-2 WindowManager + Widget Runtime working

### Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | IPC Channel (Unix sockets / Named pipes) | 🔄 Planned |
| 2 | Message Router (channel + type dispatch) | 🔄 Planned |
| 3 | Protocol Schemas (JSON Schema / Pydantic) | 🔄 Planned |
| 4 | Brain Channel (spec.ui, spec.feature, spec.task, spec.action) | 🔄 Planned |
| 5 | Features Channel (mount, unmount, action, state, event) | 🔄 Planned |
| 6 | System Channel (shutdown, restart, status, config) | 🔄 Planned |
| 7 | Request-Response pattern (correlation_id) | 🔄 Planned |
| 8 | Security (auth, authz, encryption) | 🔄 Planned |

### Technical Tasks

#### 3.1 Transport Layer
```python
# Primary: Unix Domain Sockets (Linux) / Named Pipes (Windows)
# Fallback: TCP Loopback (127.0.0.1:50000-50100)

class IPCChannel:
    async def start_server(self)
    async def connect(self)
    def register_handler(self, msg_type: str, handler: Callable)
    async def send(self, msg_type: str, payload: dict, correlation_id: str = None)
```

#### 3.2 Message Envelope
```json
{
  "msg_id": "uuid",
  "timestamp": "ISO8601",
  "version": "1.0",
  "channel": "brain",
  "msg_type": "spec.ui",
  "payload": {},
  "correlation_id": "uuid",
  "reply_to": "channel"
}
```

#### 3.3 Channel Definitions
| Channel | Participants | Message Types |
|---|---|---|
| `brain` | Core ↔ OS | spec.ui, spec.feature, spec.task, spec.action, spec.result, resource.update |
| `features` | OS ↔ Features | feature.mount, feature.unmount, feature.action, feature.state, feature.event, feature.error |
| `system` | Agent ↔ OS | system.shutdown, system.restart, system.status, system.config, system.log |
| `monitor` | All → OS | monitor.metrics, monitor.trace, monitor.health |

### Verification
```bash
# Unit tests
python -m pytest tests/ -k "ipc" -v

# Integration
python -m pytest tests/ -k "ipc_integration" -v

# Load test
python scripts/ipc_load_test.py --messages 10000 --concurrent 100

# End-to-end: Brain → OS → Feature
python scripts/test_brain_to_feature.py
```

### Success Criteria
- [ ] All 4 channels operational
- [ ] Request-response pattern works
- [ ] 10,000 msg/s throughput
- [ ] Latency p50 < 1ms, p99 < 10ms
- [ ] Authentication/authorization enforced
- [ ] Schema validation on all messages

---

## Phase OS-4: Hardware Abstraction Layer (3-4 weeks)

### Objective
Cross-platform hardware abstraction: display, input, audio, storage, network.

### Prerequisites
- OS-1, OS-2, OS-3 complete

### Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | Display Abstraction (multi-monitor, DPI) | 🔄 Planned |
| 2 | Input Abstraction (keyboard, mouse, touch) | 🔄 Planned |
| 3 | Audio Abstraction (playback, capture) | 🔄 Planned |
| 4 | Storage Abstraction (filesystem, block) | 🔄 Planned |
| 5 | Network Abstraction (TCP, UDP, DNS) | 🔄 Planned |
| 6 | Power Management (battery, sleep) | 🔄 Planned |
| 6 | Platform Backends (Win32, X11/Wayland, Cocoa) | 🔄 Planned |

### Technical Tasks

#### 4.1 Display
```python
class DisplayManager:
    def get_monitors(self) -> List[MonitorInfo]
    def get_primary_monitor(self) -> MonitorInfo
    def set_resolution(self, monitor: Monitor, resolution: Resolution)
    def get_dpi_scale(self, monitor: Monitor) -> float
```

#### 4.2 Input
```python
class InputManager:
    def get_keyboard_state(self) -> KeyboardState
    def get_mouse_state(self) -> MouseState
    def get_touch_state(self) -> List[TouchPoint]
    def register_hotkey(self, key: str, callback: Callable)
```

#### 4.3 Audio
```python
class AudioManager:
    def play(self, sound: Sound) -> PlaybackHandle
    def capture(self, duration: float) -> AudioBuffer
    def get_devices(self) -> List[AudioDevice]
    def set_volume(self, device: AudioDevice, volume: float)
```

#### 4.4 Platform Backends
| Platform | Display | Input | Audio |
|---|---|---|---|
| Windows | Win32/DXGI | Raw Input/XInput | WASAPI |
| Linux | X11/Wayland | libinput/evdev | PulseAudio/PipeWire |
| macOS | Cocoa/Metal | NSEvent | Core Audio |

### Verification
```bash
# Platform-specific tests
python -m pytest tests/ -k "display" -v
python -m pytest tests/ -k "input" -v
python -m pytest tests/ -k "audio" -v

# Cross-platform CI (run on Windows, Linux, macOS)
```

### Success Criteria
- [ ] Multi-monitor works on Windows + Linux
- [ ] DPI scaling correct
- [ ] Keyboard/mouse/touch input captured
- [ ] Audio playback/capture works
- [ ] All backends pass tests on respective platforms

---

## Phase OS-5: Sandbox Hardening (Ongoing)

### Objective
Progressively harden the sandbox: process isolation, WASM runtime, formal verification.

### Prerequisites
- OS-1 through OS-4 complete

### Deliverables

| # | Deliverable | Status |
|---|---|---|
| 1 | Process Isolation (multiprocessing) | 🔄 Planned |
| 2 | User Namespace Isolation (Linux) | 🔄 Planned |
| 3 | Container Integration (Docker/Podman) | 🔄 Planned |
| 4 | WASM Runtime (wasmtime) | 🔄 Planned |
| 5 | Formal Verification (TLA+/Coq) | 🔄 Planned |
| 6 | Capability-based FS (FUSE) | 🔄 Planned |
| 7 | Network Namespace Isolation | 🔄 Planned |
| 8 | Audit Log Integrity (Merkle tree) | 🔄 Planned |

### Technical Tasks

#### 5.1 Process Isolation
```python
# Each feature runs in separate process
# Communication via IPC (not shared memory)
# Resource limits via cgroups (Linux) / Job Objects (Windows)
```

#### 5.2 WASM Runtime
```python
# Compile features to WASM
# Run in wasmtime with capability-based imports
# Near-native performance, strong isolation
```

#### 5.3 Formal Verification
```python
# Model sandbox in TLA+
# Verify: no capability leakage, no deadlocks, resource bounds
# Generate proof certificates
```

### Verification
```bash
# Sandbox tests
python -m pytest tests/ -k "sandbox" -v

# Penetration testing
python scripts/penetration_test.py

# Formal verification
tlc sandbox_model.tla
```

### Success Criteria
- [ ] Features run in isolated processes
- [ ] WASM features execute with same API
- [ ] Formal model verified
- [ ] Zero critical vulnerabilities in audit
- [ ] Sandbox escape attempts all fail

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md)
- [Runtime Features](../03-features/runtime-features.md)
- [UI Runtime](../03-features/ui-runtime.md)
- [IPC Bridge](../03-features/ipc-bridge.md)
- [Sandbox Security](../03-features/sandbox-security.md)
- [Capability System](../05-research-notes/capability-system.md)