# JAYA_OS — The House (Body, Sensors, Actuators)

> **JAYA_OS = os_kernel** — The runtime environment where JAYA (the brain) lives.

---

## Purpose

JAYA_OS provides the **execution environment** for JAYA_CORE's cognitive output. It is the "house" — the body, sensors, and actuators that validate, compile, and execute the specifications emitted by the brain.

| JAYA_CORE (Brain) | JAYA_OS (House) |
|---|---|
| Reasons, plans, understands intent | Executes, renders, manages hardware |
| Emits **specifications** (UI, Feature, Task, Action) | **Compiles & mounts** specifications |
| Sovereign, offline-first, lightweight | Policy enforcement, sandboxing, resource management |
| Never touches hardware directly | Owns device runtime, windowing, IPC |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        JAYA OS (The House)                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  os_kernel (Home Layer) — Body, Sensors, Actuators        │  │
│  │  • Device runtime, windowing, feature mounting            │  │
│  │  • Hardware abstraction, resource monitoring              │  │
│  │  • Policy enforcement, sandbox execution                  │  │
│  │  • FeatureCompiler, FeatureRegistry, JayaBridge, IPC      │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Specs (JSON)
                              │
┌─────────────────────────────────────────────────────────────────┐
│                    JAYA_CORE (The Brain)                        │
│  • IntentEngine → LinguaLogica → JayaIR → IronEngine           │
│  • SpecGenerators: UI, Feature, Task, Action                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Responsibilities

### 1. Specification Compilation & Mounting
- **FeatureCompiler** — SceneGraph → Runnable Python feature package
- **FeatureRegistry** — Versioned discovery, dependency resolution
- **JayaBridge** — Sandbox mount, action dispatch, state management

### 2. UI Runtime (Phase 3C+)
- **WindowManager** — Window lifecycle, z-order, focus
- **Widget Runtime** — Render WidgetSpec (button, input, list, chart, etc.)
- **Event Loop** — Button clicks, form submits → IPC → Brain

### 3. System Services
- **ResourceMonitor** — CPU/RAM/Battery → feeds back to Brain (adaptive top-k)
- **IPC Bridge** — Structured communication Brain ↔ House
- **Policy Enforcement** — Permissions, sandboxing, capability-based security

### 4. Hardware Abstraction
- Display, input, audio, storage, network
- Platform-specific backends (Windows, Linux, embedded)

---

## Spec Types Handled

| Spec Type | Source | Compiler | Runtime |
|---|---|---|---|
| **UI Spec** (SceneGraph) | Brain → UISpecGenerator | FeatureCompiler | WindowManager + Widget Runtime |
| **Feature Spec** (FeatureManifest) | Brain → FeatureSpecGenerator | FeatureCompiler | JayaBridge (sandboxed process) |
| **Task Spec** (ExecutionPlan) | Brain → TaskSpecGenerator | TaskScheduler | Background worker pool |
| **Action Spec** (ActionSpec) | Brain → ActionSpecGenerator | IPC Router | Direct system call |

---

## Security Model

- **Capability-based permissions** — Features declare required permissions in manifest
- **Sandbox by default** — All mounted features run in restricted Python environment
- **No direct brain→hardware** — Brain emits specs; House validates & executes
- **Signed manifests** — Feature packages verified before mount

---

## Development Status

| Component | Status |
|---|---|
| FeatureCompiler | ✅ (in JAYA_CORE/os_kernel) |
| FeatureRegistry | ✅ (in JAYA_CORE/os_kernel) |
| JayaBridge | ✅ (in JAYA_CORE/os_kernel) |
| UI Spec (SceneGraph) | ✅ (in JAYA_CORE/os_kernel) |
| IntentToUIPipeline | ✅ Phase 3C (in JAYA_CORE/os_kernel) |
| WindowManager | 🔄 Planned |
| Widget Runtime | 🔄 Planned |
| IPC Bridge | 🔄 Planned |
| ResourceMonitor | ✅ (in JAYA_CORE/brain_v2) |

> **Note**: Currently os_kernel lives in `JAYA_CORE/src/os_kernel/`. This JAYA_OS project will become the standalone home for os_kernel once the brain/house separation is complete.

---

## Roadmap

| Phase | Focus | Deliverables |
|---|---|---|
| **OS-1** | Extract os_kernel to standalone | Independent JAYA_OS repo, build system |
| **OS-2** | Window Manager + Widget Runtime | Native UI rendering, event loop |
| **OS-3** | IPC Bridge + Capability System | Structured Brain↔House comms, permissions |
| **OS-4** | Hardware Abstraction Layer | Cross-platform (Windows, Linux, embedded) |
| **OS-5** | Sandbox Hardening | WASM/container-based feature isolation |

---

## 🔗 Related

- [JAYA_CORE](../JAYA_CORE/README.md) — The Brain (cognitive core)
- [JAYA_AGENT](../JAYA_AGENT/README.md) — The Agent Framework (user-facing applications)
- [JAYA_RESEARCH](../JAYA_RESEARCH/README.md) — Research Assistant (cloud-powered)
- [Root Architecture](../docs/arsitektur_utama_jaya.md) — 40 Pillars, Dual Domain