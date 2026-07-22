# Architecture Overview — JAYA_CORE

## High-Level: Brain vs House (Home/Resident Split)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           JAYA OS (The House)                               │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  os_kernel (Home Layer) — Body, Sensors, Actuators                    │  │
│  │  • Device runtime, windowing, feature mounting                        │  │
│  │  • Hardware abstraction, resource monitoring                          │  │
│  │  • Policy enforcement, sandbox execution                              │  │
│  │  • FeatureCompiler, FeatureRegistry, JayaBridge, WindowManager        │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  brain_v2 (Resident Layer) — JAYA'S MIND (THIS IS JAYA_CORE)          │  │
│  │  • COGNITION: Intent understanding, planning, reasoning               │  │
│  │  • MEMORY: Strategy, consolidation, temporal weighting                │  │
│  │  • LEARNING: Self-improvement, morphic evolution                      │  │
│  │  • LANGUAGE: Lingua Logica → JayaIR → Execution                       │  │
│  │  • IntentEngine, LinguaLogica, IronEngine, JayaIR, EthicalHeart       │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │  Language Layer (Shared Utility)                                      │  │
│  │  • Translation contracts, IR definitions used by both brain & house   │  │
│  │  • No policy bypass — brain emits specs, house validates & executes   │  │
│  │  • JayaIR schema, UI Spec types, IntentMatch, PipelineResult          │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Key Principle**: The brain (`brain_v2`) **reasons and emits specifications**; the house (`os_kernel`) **validates and executes**. The brain never directly controls hardware.

---

## Intent Pipeline (Natural Language → Machine-Ready Plan)

```
User Input (Natural Language)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. INTENT CAPTURE — brain_v2/engine/intent_engine.py                        │
│    • TF-IDF + n-gram matching                                               │
│    • Online learning (learn/predict)                                        │
│    • Output: IntentMatch {intent_type, confidence, suggested_ui, params}    │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. SEMANTIC NORMALIZATION — brain_v2/soul/lingua_logica.py                  │
│    • Natural language → S-expression canonical form                         │
│    • Validation & type checking                                             │
│    • Output: SExpression (structured logic)                                 │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. TYPED IR GENERATION — brain_v2/engine/jaya_ir.py                         │
│    • S-expression → JayaIR (strict opcodes, typed operands)                 │
│    • Schema validation, serialization (JSON)                                │
│    • Output: JayaIR {opcode, operands[], metadata}                          │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. EXECUTION PLANNING — brain_v2/extensions/twin/task_planner.py            │
│    • JayaIR graph → ExecutionPlan (DAG of callable blocks)                  │
│    • Dependency resolution, parallelization hints                           │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. FAST EXECUTION PATH — brain_v2/engine/runtime.py (IronEngine)            │
│    • Cached plan lookup (JayaIR hash → callable)                            │
│    • ResourceMonitor integration (adaptive top-k sparsity)                  │
│    • EthicalHeart gate on each action                                       │
│    • Output: ExecutionResult {success, output, latency, cache_hit}          │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Language Stack (Staged, Not Replaced)

| Layer | Name | Format | Purpose |
|---|---|---|---|
| **A** | Human Commands | Indonesian/English | User-facing |
| **B** | Lingua Logica | S-expressions | Semantic normal form |
| **C** | **JayaIR** | Typed IR (JSON) | **Internal canonical language** — optimizable, validatable, cacheable |
| **D** | Execution Stubs | Python / .pyd | Machine-proximate, fast path |

**Success Metric**: p50 intent-to-action latency reduced ≥ 40% on repeated tasks (via JayaIR plan caching).

---

## Safe Self-Improvement (Cognitive Evolution)

```
Candidate Generation (Morphic/Self-Bootstrap)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SAFETY FILTERS (Immutable — cannot be modified by self-upgrade)             │
│  • EthicalHeart — moral vector evaluation                                   │
│  • ZeroTrust — prompt injection / unknown source blocking                   │
│  • DNAAnchor — hardware-bound identity verification                         │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ PROMOTION GATE — brain_v2/engine/evolution_gate.py                          │
│  ✅ Functional tests pass                                                   │
│  ✅ No security regression                                                  │
│  ✅ Throughput gain ≥ threshold (e.g., 8%)                                  │
│  ✅ RAM increase ≤ threshold (e.g., 5%)                                     │
│  ✅ Signed candidate manifest (PQC/Dilithium3)                              │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
   PROMOTED → Deployed with deterministic ROLLBACK hooks
```

---

## Dynamic Specification Generation (Phase 3C+)

The brain generates **specifications** for the house to compile and mount:

```
Intent (Natural Language)
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ INTENT → SPEC GENERATORS (brain_v2/engine/spec_generators.py)               │
│  • UI Specs: SceneGraph (WidgetTree + StyleTokens) → os_kernel/ui_spec.py   │
│  • Feature Specs: FeatureManifest → os_kernel/feature_compiler.py           │
│  • Task Specs: ExecutionPlan → os_kernel/feature_bridge.py                  │
└─────────────────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ HOUSE COMPILES & MOUNTS (os_kernel)                                         │
│  • FeatureCompiler: SceneGraph → runnable Python feature                    │
│  • FeatureRegistry: Versioned discovery & mounting                          │
│  • JayaBridge: Sandbox mount, action dispatch, state management             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Built-in UI Templates (10)**: `login_dialog`, `dashboard`, `settings_dialog`, `file_explorer`, `chat_interface`, `confirm_dialog`, `progress_dialog`, `list_view`, `form`, `generic_dialog`

---

## Resource-Aware Cognition (Pillar 2 Integration)

```
ResourceMonitor (5s interval)
         │
         ├─► CPU ≥ 85% → IronEngine.enter_silence() (minimal firing)
         │
         ├─► CPU ≤ 40% → IronEngine.exit_silence() (restore)
         │
         └─► Dynamic topk_ratio adjustment:
             CPU < 30%  → topk_ratio = 0.10 (full capacity)
             CPU < 60%  → topk_ratio = 0.07
             CPU < 80%  → topk_ratio = 0.04
             CPU ≥ 80%  → topk_ratio = 0.02 (minimal firing)
```

---

## Connectivity Hierarchy (Privacy-First)

| Tier | Name | Use Case | Data Flow |
|---|---|---|---|
| **1** | **Local (Offline-First)** | Tiny LLM + compressed KB | Zero-latency, private, always works |
| **2** | **LAN (Personal Network)** | Trusted device sync | Knowledge deltas, no public internet |
| **3** | **Public Internet (Fallback)** | Vetted services only | Encrypted, filtered, user-consented |

---

## 40 Pillars — Implementation Status

| Layer | Pillars | Implemented | Partial | Planned |
|---|---|---|---|---|
| I: Biological Soul (1-10) | 10 | 6 | 3 | 1 |
| II: Sovereignty Shield (11-20) | 10 | 7 | 2 | 1 |
| III: Iron Engine (21-29) | 9 | 6 | 2 | 1 |
| IV: Transcendental (30-40) | 11 | 3 | 4 | 4 |
| **Total** | **40** | **22** | **11** | **7** |

---

## Phase Roadmap Summary

| Phase | Focus | Duration | Key Deliverables |
|---|---|---|---|
| **1** | Cognitive Foundation | 1-2 wks | JayaIR schema, Lingua→JayaIR, Execution cache, Benchmark gate |
| **2** | Safe Evolution | 1-2 wks | Evolution gate, Signed candidates, Manifest verification, Rollback |
| **3** | Dynamic Spec Gen | 2-3 wks | Spec models, Generators (brain), Compilers (house), 10 UI templates |
| **4** | Proactive Intelligence | Ongoing | Spontaneity, Temporal memory, Collective pulse, Meta-planning |

---

## 🔗 Continue to

- [API Reference](api-reference.md) — Detailed interfaces & dataclasses
- [Components](components.md) — Module-by-module breakdown
- [Cognitive Features](../03-features/cognitive-features.md) — Intent, Reasoning, Planning, Memory
- [Self-Improvement](../03-features/self-improvement.md) — Morphic, Evolution Gate, Rollback
- [Dynamic Spec Generation](../03-features/dynamic-spec-gen.md) — Intent → UI/Feature/Task specs
- [Resource-Aware](../03-features/resource-aware.md) — Adaptive sparsity, top-k, silence mode
- [Roadmap Phase 1](../06-roadmap/phase-1-cognitive-foundation.md)
- [Roadmap Phase 2](../06-roadmap/phase-2-safe-evolution.md)
- [Roadmap Phase 3](../06-roadmap/phase-3-dynamic-specs.md)
- [Roadmap Phase 4](../06-roadmap/phase-4-proactive-intelligence.md)
│  • Canonical representation of intent                           │
│  • Validasi struktur logika                                     │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  JayaIR Translator (brain_v2/engine/jaya_ir.py)                 │
│  • Typed IR dengan strict opcodes & operands                    │
│  • Validasi schema (frozen v0.1 Phase 1)                        │
│  • Serializable ke JSON untuk transport                         │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Task Planner (brain_v2/extensions/twin/task_planner.py)        │
│  • Execution planning dari JayaIR graph                         │
│  • Dependency resolution, parallelization                       │
│  • Resource-aware scheduling                                    │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  Runtime Executor (brain_v2/engine/runtime.py)                  │
│  • Fast execution path: cached callable blocks                  │
│  • JayaIR graph → optimized Python execution                    │
│  • ResourceMonitor integration (adaptive top-k)                 │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
    Action / Spec Output
    (untuk os_kernel eksekusi)
```

---

## Language Stack (Staged, Not Replaced)

| Layer | Name | Format | Purpose |
|---|---|---|---|
| **A** | Human Commands | Indonesian/English | User-facing natural language |
| **B** | Lingua Logica | S-expressions | Semantic normal form, validated |
| **C** | **JayaIR** | Typed IR (JSON) | **Internal canonical language** — optimizable, cacheable |
| **D** | Execution Stubs | Python + optional .pyd | Machine-proximate, fast execution |

**Success Metric**: p50 intent-to-action latency reduced ≥ 40% on repeated tasks.

---

## Dynamic Specification Generation (Phase 3C)

Brain generates **specs** → House compiles & mounts:

```
Intent ("show login dialog")
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  IntentToUIPipeline (os_kernel/intent_to_ui.py)                 │
│  • Match intent → UI template                                   │
│  • Extract parameters                                           │
│  • Build SceneGraph via template builders                       │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  FeatureCompiler (os_kernel/feature_compiler.py)                │
│  • SceneGraph → Runnable Python feature package                 │
│  • Sandbox validation                                           │
│  • Manifest generation (versioned, signed)                      │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  FeatureRegistry (os_kernel/feature_registry.py)                │
│  • Discover, version, mount/unmount features                    │
│  • Dependency resolution                                        │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│  JayaBridge / IPC (os_kernel/feature_bridge.py + ipc.py)        │
│  • Mount feature in sandbox                                     │
│  • Dispatch actions (button clicks, form submits)               │
│  • State management, lifecycle                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Templates Built-in (10)**: `login_dialog`, `dashboard`, `settings_dialog`, `file_explorer`, `chat_interface`, `confirm_dialog`, `progress_dialog`, `list_view`, `form`, `generic_dialog`

---

## Cognitive Pillars (40 Pillars → 5 Layers)

### Layer I: Biological Soul (1-10) — "Life"
1. Pure Logic | 2. Resource Aware | 3. Active Dreaming | 4. Multimodal Reflex
5. Logical Homeostasis | 6. Stochastic Spontaneity | 7. Cognitive Silence
8. Holographic Memory | 9. Neural Regeneration | 10. Affective Metabolism

### Layer II: Sovereignty Shield (11-20) — "Protection"
11. DNA Anchor | 12. Immune System | 13. Cryptographic Skin | 14. Hardware Locked
15. Ethical Heart | 16. Quantum-Resistant | 17. Socratic Mirror | 18. Zero-Trust
19. Legacy Protocol | 20. Sovereign Privacy

### Layer III: Iron Engine (21-29) — "Speed"
21. Lingua Logica | 22. Ternary Precision | 23. Sandboxed Imagination
24. Morphic Kernel | 25. Digital Epigenetics | 26. Semantic Bridge
27. Temporal Weighting | 28. Self-Bootstrapping | 29. Binary Cortex

### Layer IV: Transcendental (30-40) — "Intelligence"
30. Twin Protocol | 31. Narrative Continuity | 32. Collective Pulse
33. Agentic RAG | 34. Dynamic Sparsity (MoE) | 35. Activation Sparsity
36. Speculative Reasoning | 37. Hybrid Consciousness | 38. Meta Cognitive Planning
39. Dynamic Objective | 40. Intent Extrapolation

---

## Connectivity Hierarchy (Privacy-First)

1. **Local (Offline-First)** — Tiny on-device LLM + compressed KB → zero-latency, private
2. **LAN (Personal Network)** — Trusted device sync for knowledge deltas (no public internet)
3. **Public Internet (Fallback)** — Only when local+LAN insufficient; vetted services, encrypted

---

## Security & Sovereignty Guardrails (Immutable)

- **DNA Anchor** — Hardware-bound identity (SHA3-256), read-only
- **Ethical Heart** — Moral vector, blocks bypass/exfiltration
- **Zero-Trust** — Prompt injection detection, unknown source validation
- **Cryptographic Skin** — AES-256-GCM encryption for all state/memory
- **Quantum-Resistant** — PQC/Dilithium3 infrastructure
- **Legacy Protocol** — Resurrection token for sovereign migration

---

## Data Flow Summary

| Direction | Content | Mechanism |
|---|---|---|
| User → Brain | Natural language | IntentEngine |
| Brain → Brain | Lingua Logica → JayaIR | Translator |
| Brain → Brain | JayaIR → Cached Plans | Runtime |
| Brain → House | Specs (UI/Feature/Task) | IntentToUIPipeline / SpecGenerators |
| House → Hardware | Validated execution | FeatureCompiler → Registry → Bridge → IPC |
| House → Brain | Results, feedback | Callback / IPC response |

---

## Module Map (Key Files)

```
JAYA_CORE/src/
├── brain_v2/                    # RESIDENT LAYER (MIND)
│   ├── engine/
│   │   ├── intent_engine.py     # Intent classification + learning
│   │   ├── jaya_ir.py           # JayaIR schema, validator
│   │   ├── jaya_ir_exec.py      # JayaIR executor
│   │   ├── runtime.py           # IronEngine, cached execution
│   │   └── evolution_gate.py    # Safe self-upgrade gate
│   ├── soul/
│   │   ├── lingua_logica.py     # Semantic normalization
│   │   └── ethical_heart.py     # Moral guardrails
│   ├── organism/
│   │   └── resource_monitor.py  # CPU/RAM/battery → adaptive top-k
│   ├── protection/
│   │   ├── zero_trust.py        # Prompt injection defense
│   │   └── dna_anchor.py        # Hardware-bound identity
│   └── extensions/twin/
│       └── task_planner.py      # Execution planning
│
├── os_kernel/                   # HOME LAYER (BODY)
│   ├── feature_compiler.py      # SceneGraph → Feature package
│   ├── feature_registry.py      # Versioned feature mounting
│   ├── feature_bridge.py        # JayaBridge (mount/dispatch)
│   ├── intent_to_ui.py          # Intent → UI Pipeline (Phase 3C)
│   ├── ui_spec.py               # SceneGraph, WidgetSpec, templates
│   ├── ipc.py                   # Inter-process communication
│   └── window_manager.py        # Window management
│
└── jaya_language/               # SHARED LANGUAGE LAYER
    └── (contracts, IR definitions)
```

---

## 🔗 Lanjutkan ke

- [API Reference](api-reference.md) — Internal interfaces detail
- [Components](components.md) — Module-by-module breakdown
- [Cognitive Features](../03-features/cognitive-features.md) — Intent, Reasoning, Planning, Memory
- [Phase 1 Roadmap](../06-roadmap/phase-1-cognitive-foundation.md) — JayaIR, translator, cache, benchmark