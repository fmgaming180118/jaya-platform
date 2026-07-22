# Dokumentasi JAYA_CORE

> Satu-satunya pintu masuk untuk semua dokumentasi otak kognitif JAYA. Baca dari sini, ikuti link ke dokumen spesifik.

---

## 📖 Cara Membaca Dokumentasi Ini

| Tujuan | Mulai dari |
|---|---|
| Mau install & coba pertama kali | [01 → Installation](01-getting-started/installation.md) |
| Paham cara kerja sistem (brain vs house) | [02 → Architecture Overview](02-architecture/overview.md) |
| Pakai fitur chat / reasoning | [03 → Cognitive Features](03-features/cognitive-features.md) |
| Jalankan benchmark / test kognitif | [04 → Development](04-development/testing.md) |
| Riset mendalam (JayaIR, Evolution, Spec Gen) | [05 → Research Notes](05-research-notes/jaya-ir.md) |
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
│   ├── overview.md                  ← High-level diagram & alur sistem (Brain vs House)
│   ├── api-reference.md             ← Semua endpoint / interface internal
│   └── components.md                ← brain_v2, os_kernel, Language Layer detail
│
├── 03-features/
│   ├── cognitive-features.md        ← Intent understanding, reasoning, planning
│   ├── self-improvement.md          ← Morphic evolution, safe self-upgrade
│   ├── dynamic-spec-gen.md          ← Intent → UI/Feature/Task specs
│   └── resource-aware.md            ← CPU/RAM/battery → adaptive sparsity
│
├── 04-development/
│   ├── testing.md                   ← Cara jalankan test suite (211 tests)
│   └── benchmark.md                 ← Hasil benchmark Phase 1-3
│
├── 05-research-notes/
│   ├── jaya-ir.md                   ← JayaIR schema, translator, executor
│   ├── evolution-gate.md            ← Safe self-improvement gates
│   ├── spec-generators.md           ← Intent → SceneGraph/Feature/Task specs
│   └── proactive-intelligence.md    ← Spontaneity, temporal memory, collective pulse
│
├── 06-roadmap/
│   ├── README.md                    ← Ringkasan Phase 1-4
│   ├── phase-1-cognitive-foundation.md
│   ├── phase-2-safe-evolution.md
│   ├── phase-3-dynamic-specs.md
│   ├── phase-4-proactive-intelligence.md
│   └── workflows/
│       ├── phase-1/
│       ├── phase-2/
│       ├── phase-3/
│       └── phase-4/
```

---

## 🧠 JAYA_CORE dalam Sekilas

**JAYA_CORE = Otak Kognitif (Brain)**, bukan OS, bukan agent framework.

| **ADALAH** | **BUKAN** |
|---|---|
| ✅ Reasoning & planning engine | ❌ Knowledge base / encyclopedia |
| ✅ Intent → Action pipeline | ❌ Operating system / shell |
| ✅ Self-improving cognitive core | ❌ Agent framework / tool caller |
| ✅ Sovereign, offline-first brain | ❌ Cloud-dependent service |
| ✅ Lightweight (runs on CPU) | ❌ Heavy model server |

**Analogi**: `os_kernel` = rumah (body, sensors, actuators). `brain_v2` = JAYA (mind living inside). **JAYA_CORE = just the brain.**

---

## 🏗️ Arsitektur: Brain vs House (Home/Resident Split)

```
┌─────────────────────────────────────────────────────────────────┐
│                        JAYA OS (The House)                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  os_kernel (Home Layer) — Body, Sensors, Actuators        │  │
│  │  • Device runtime, windowing, feature mounting            │  │
│  │  • Hardware abstraction, resource monitoring              │  │
│  │  • Policy enforcement, sandbox execution                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  brain_v2 (Resident Layer) — JAYA'S MIND (THIS IS CORE)   │  │
│  │  • COGNITION: Intent understanding, planning, reasoning   │  │
│  │  • MEMORY: Strategy, consolidation, temporal weighting    │  │
│  │  • LEARNING: Self-improvement, morphic evolution          │  │
│  │  • LANGUAGE: Lingua Logica → JayaIR → Execution           │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Language Layer (Shared Utility)                          │  │
│  │  • Translation contracts, IR definitions used by both     │  │
│  │  • No policy bypass — brain emits specs, house validates  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Prinsip Kunci**: Otak (`brain_v2`) berfikir dan mengeluarkan **spesifikasi intent**; Rumah (`os_kernel`) memvalidasi dan mengeksekusi. Otak **tidak pernah** langsung mengontrol hardware.

---

## 🔗 Navigasi Cepat

### Getting Started
- [Installation](01-getting-started/installation.md) — Python 3.12, venv, dependencies
- [Quick Start](01-getting-started/quick-start.md) — Chat dengan JAYA dalam 5 menit
- [Configuration](01-getting-started/configuration.md) — pyrightconfig, env vars
- [CLI Commands](01-getting-started/cli-commands.md) — jaya_chat_cli, benchmark, autonomous curriculum

### Architecture
- [Overview](02-architecture/overview.md) — Brain vs House, Intent Pipeline, Language Stack
- [API Reference](02-architecture/api-reference.md) — Internal interfaces, JayaBridge, FeatureCompiler
- [Components](02-architecture/components.md) — brain_v2 modules, os_kernel modules, pillars

### Features
- [Cognitive Features](03-features/cognitive-features.md) — Intent, Reasoning, Planning, Memory
- [Self-Improvement](03-features/self-improvement.md) — Morphic, Evolution Gate, Rollback
- [Dynamic Spec Generation](03-features/dynamic-spec-gen.md) — Intent → SceneGraph/Feature/Task specs
- [Resource-Aware](03-features/resource-aware.md) — Adaptive sparsity, top-k, silence mode

### Development
- [Testing](04-development/testing.md) — pytest, 211 tests, Phase gates
- [Benchmark](04-development/benchmark.md) — p50/p95 latency, hit-rate, cognitive throughput

### Research Notes
- [JayaIR](05-research-notes/jaya-ir.md) — Schema, translator, executor, cached plans
- [Evolution Gate](05-research-notes/evolution-gate.md) — Signed candidates, manifest verification, rollback
- [Spec Generators](05-research-notes/spec-generators.md) — Intent → UI/Feature/Task specifications
- [Proactive Intelligence](05-research-notes/proactive-intelligence.md) — Spontaneity, temporal memory, collective pulse

### Roadmap
- [Phase 1: Cognitive Foundation](06-roadmap/phase-1-cognitive-foundation.md) — JayaIR, translator, cache, benchmark
- [Phase 2: Safe Evolution](06-roadmap/phase-2-safe-evolution.md) — Promotion gate, signed candidates, rollback
- [Phase 3: Dynamic Specs](06-roadmap/phase-3-dynamic-specs.md) — Spec models, generators, house compilers
- [Phase 4: Proactive Intelligence](06-roadmap/phase-4-proactive-intelligence.md) — Spontaneity, temporal, collective

---

## 📋 Status Implementasi (Phase 3C Complete)

| Phase | Status | Key Deliverables |
|-------|--------|------------------|
| **Phase 1** | ✅ Done | JayaIR schema, Lingua Logica → JayaIR → Executor, Benchmark gate (p50<50ms, p95<100ms, hit-rate>95%) |
| **Phase 2** | ✅ Done | Evolution gate, signed candidates, manifest verification, deterministic rollback |
| **Phase 3C** | ✅ Done | Intent → UI Pipeline, 10 templates, FeatureCompiler, JayaBridge, SceneGraph spec |
| **Phase 4** | 🔄 Planned | Spontaneity engine, temporal consolidation, collective pulse (LAN sync) |

**Test Suite**: 211 passed, 15 warnings (3:24 min)

---

## 🛡️ Filosofi Kedaulatan (Pillar 37)
JAYA tidak bergantung pada internet untuk keberadaannya. Dengan **Hybrid Consciousness**, JAYA tetap fungsional dan setia meskipun perangkat Boss dalam keadaan offline total. Pengetahuan disimpan lokal di `rag_vault.db`; logika diamankan oleh `jaya.jay` (DNA anchor + encrypted weights).

---

## 👤 Credits
Built with ⚡ and 🏛️ for **Boss**. 
*Designed as a companion, forged as a sovereign.*