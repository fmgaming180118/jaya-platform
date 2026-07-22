# Dokumentasi JAYA_OS

> Satu-satunya pintu masuk untuk semua dokumentasi lingkungan eksekusi JAYA. Baca dari sini, ikuti link ke dokumen spesifik.

---

## 📖 Cara Membaca Dokumentasi Ini

| Tujuan | Mulai dari |
|---|---|
| Mau install & coba pertama kali | [01 → Installation](01-getting-started/installation.md) |
| Paham cara kerja sistem (House/Body) | [02 → Architecture Overview](02-architecture/overview.md) |
| Pakai fitur UI/Feature mounting | [03 → Runtime Features](03-features/runtime-features.md) |
| Jalankan test & development | [04 → Development](04-development/testing.md) |
| Riset mendalam (WindowManager, IPC, Sandbox) | [05 → Research Notes](05-research-notes/window-manager.md) |
| Roadmap implementasi & checklist fase | [06 → Roadmap](06-roadmap/README.md) |

---

## 📁 Struktur Dokumentasi

```
docs/
├── README.md                        ← (file ini)
│
├── 01-getting-started/
│   ├── installation.md              ← Install Python, setup venv, dependencies
│   ├── quick-start.md               ← Jalankan dalam 5 menit
│   ├── configuration.md             ← Penjelasan config & env var
│   └── cli-commands.md              ← CLI Reference & Fitur Otomatisasi
│
├── 02-architecture/
│   ├── overview.md                  ← High-level diagram & alur sistem (House/Body)
│   ├── api-reference.md             ← Semua interface internal
│   └── components.md                ← Module-by-module breakdown
│
├── 03-features/
│   ├── runtime-features.md          ← FeatureCompiler, FeatureRegistry, JayaBridge
│   ├── ui-runtime.md                ← WindowManager, Widget Runtime, Event Loop
│   ├── ipc-bridge.md                ← Inter-Process Communication
│   └── sandbox-security.md          ← Capability-based permissions, sandboxing
│
├── 04-development/
│   ├── testing.md                   ← Cara jalankan test suite
│   └── benchmark.md                 ← Hasil benchmark runtime
│
├── 05-research-notes/
│   ├── window-manager.md            ← Window management research
│   ├── ipc-protocol.md              ← IPC protocol design
│   ├── sandbox-isolation.md         ← Sandbox isolation techniques
│   └── capability-system.md         ← Capability-based security
│
├── 06-roadmap/
│   ├── README.md                    ← Ringkasan OS-1 to OS-5
│   ├── os-1-extract-os-kernel.md
│   ├── os-2-window-manager.md
│   ├── os-3-ipc-bridge.md
│   ├── os-4-hardware-abstraction.md
│   ├── os-5-sandbox-hardening.md
│   └── workflows/
│       ├── os-1/
│       ├── os-2/
│       ├── os-3/
│       ├── os-4/
│       └── os-5/
```

---

## 🏠 JAYA_OS dalam Sekilas

**JAYA_OS = os_kernel** — The runtime environment where JAYA (the brain) lives.

| **ADALAH** | **BUKAN** |
|---|---|
| ✅ Execution environment (House/Body) | ❌ Cognitive brain (that's JAYA_CORE) |
| ✅ Feature compiler & runtime | ❌ Agent framework (that's JAYA_AGENT) |
| ✅ Window manager & UI renderer | ❌ Cloud research assistant (that's JAYA_RESEARCH) |
| ✅ Hardware abstraction layer | ❌ Knowledge base |
| ✅ Policy enforcement & sandboxing | ❌ Decision maker |

**Analogi**: `JAYA_CORE` = Mind (pikiran). `JAYA_OS` = Body (tubuh, sensor, aktuator). `JAYA_AGENT` = Apps (aplikasi user-facing).

---

## 🏗️ Arsitektur: House/Body Layer

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           JAYA OS (The House)                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  os_kernel (Home Layer) — Body, Sensors, Actuators                    │  │
│  │  • Device runtime, windowing, feature mounting                        │  │
│  │  • Hardware abstraction, resource monitoring                          │  │
│  │  • Policy enforcement, sandbox execution                              │  │
│  │  • FeatureCompiler, FeatureRegistry, JayaBridge, IPC                  │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ Specs (JSON)
                              │
┌─────────────────────────────────────────────────────────────────────────────┐
│                    JAYA_CORE (The Brain)                                    │
│  • IntentEngine → LinguaLogica → JayaIR → IronEngine                       │
│  • SpecGenerators: UI, Feature, Task, Action                               │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Prinsip Kunci**: Otak (`JAYA_CORE`) berfikir dan mengeluarkan **spesifikasi**; Rumah (`JAYA_OS`) **memvalidasi, mengompilasi, dan mengeksekusi** spesifikasi. Otak tidak pernah langsung mengontrol hardware.

---

## 🔧 Core Responsibilities

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

## 🔗 Lanjutkan ke

- [Installation](01-getting-started/installation.md) — Python 3.12, venv, dependencies
- [Quick Start](01-getting-started/quick-start.md) — Run JAYA_OS in 5 minutes
- [Architecture Overview](../02-architecture/overview.md) — Full pipeline diagram
- [Runtime Features](../03-features/runtime-features.md) — FeatureCompiler, Registry, Bridge
- [Roadmap OS-1 to OS-5](../06-roadmap/README.md) — Implementation plan