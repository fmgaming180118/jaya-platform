# JAYA_CORE Cognitive Roadmap — Building the Brain

## 1. Objective
Build a **sovereign, offline-first cognitive core** — the "brain" of a JARVIS-inspired AI assistant.

> **"The goal is to build a *smart brain*, not a brain stuffed with knowledge."**

JAYA_CORE focuses on **cognitive capabilities** — reasoning, planning, intent understanding, self-improvement — not on storing facts or acting as an OS. Knowledge is external (retrieved on demand); intelligence is internal (the core competency).

**Analogy**: `os_kernel` = the house (body, sensors, actuators). `brain_v2` = JAYA (the mind living inside). **JAYA_CORE = just the brain.**

## 2. Architectural Principles
- **Cognition first, execution second** — The brain reasons; the house executes.
- **Resource-aware by default** — CPU, RAM, battery awareness baked into cognitive loops.
- **Security gates cannot be bypassed by self-modification** — DNA anchor, ethical heart, zero-trust are immutable.
- **Incremental evolution with benchmark-based promotion** — Every cognitive upgrade measured, gated, rollback-ready.
- **Keep modules small and composable** — Cognitive primitives, not monolithic pipelines.

## 3. Target Architecture: Brain vs House (Home/Resident Split)

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

**Key Principle**: The brain (`brain_v2`) reasons and emits **intent specifications**; the house (`os_kernel`) validates and executes. The brain never directly controls hardware.

## 4. Cognitive Capabilities Roadmap

### 4.1 Intent Understanding Pipeline (Natural Language → Structured Intent)
1. **Intent Capture** — `brain_v2/engine/intent_engine.py` (existing)
2. **Semantic Normalization** — `brain_v2/soul/lingua_logica.py` (existing)
3. **Typed IR Generation** — `JayaIR` with strict opcodes & typed operands (new)
4. **Execution Planning** — `brain_v2/extensions/twin/task_planner.py` (existing)
5. **Fast Execution Path** — `brain_v2/engine/runtime.py` + cached callable blocks (new)

### 4.2 Internal Language Stack (Staged, Not Replaced)
- **Layer A**: Human-facing commands (Indonesian/English)
- **Layer B**: Lingua Logica forms (semantic normal form)
- **Layer C**: **JayaIR** (new internal canonical language — typed, validated, optimizable)
- **Layer D**: Machine-proximate execution stubs (optimized Python + optional .pyd)

**Success Metric**: p50 intent-to-action latency reduced ≥ 40% on repeated tasks.

### 4.3 Safe Self-Improvement (Cognitive Evolution)
Leverage existing morphic/self-bootstrap with stricter promotion gates:
- **Candidate Generation**: `brain_v2/engine/morphic.py`, `self_bootstrap.py`
- **Safety Filters**: `brain_v2/soul/ethical_heart.py`, `brain_v2/protection/zero_trust.py`
- **Promotion Gate** (new policy):
  - Functional tests pass
  - No security regression
  - Throughput gain ≥ threshold (e.g., 8%)
  - RAM increase ≤ threshold (e.g., 5%)
- **Rollback**: Mandatory auto-rollback if runtime checks fail

### 4.4 Dynamic Specification Generation (For House to Execute)
The brain generates **specifications** (UI specs, feature specs, action plans) that the house compiles and mounts:
- Intent → SceneGraph / WidgetTree / StyleTokens (UI specs)
- Intent → Feature package manifests (capability specs)
- Intent → Task plans (execution specs)

**Boundary**: Brain generates specs; House compiles, sandboxes, mounts.

### 4.5 Resource-Aware Cognition (Pillar 2 Integration)
- Reuse `ResourceMonitor` feedback for adaptive cognitive quality
- Sparse activation defaults for non-critical reasoning paths
- Bounded, observable hot-path caches (JayaIR plan cache)
- Prefer AOT caching of frequent cognitive plans over continuous recompilation

## 5. Implementation Phases

### Phase 1: Cognitive Foundation (1-2 weeks)
- Define `JayaIR` schema and validator
- Integrate Lingua Logica → JayaIR translator
- Add execution cache for repeated intents (cognitive plan reuse)

**Boundary**: In scope: `brain_v2` language/execution pipeline + benchmark gate. Out of scope: `os_kernel` changes.

**Deliverables**:
- `src/brain_v2/engine/jaya_ir.py` (new)
- `src/brain_v2/engine/jaya_ir_exec.py` (new)
- Unit tests for parse/validate/execute
- Benchmark gate for cognitive throughput

### Phase 2: Safe Cognitive Evolution (1-2 weeks)
- Implement benchmark + security promotion gate for cognitive upgrades
- Add signed candidate metadata and deterministic rollback hooks

**Deliverables**:
- `src/brain_v2/engine/evolution_gate.py` (new)
- Tests for pass/fail promotion and rollback

### Phase 3: Dynamic Spec Generation (2-3 weeks)
- Build spec models (UI spec, feature spec, task plan spec)
- Implement spec generators in `brain_v2` (intent → spec)
- House (`os_kernel`) implements compilers/registries for these specs

**Boundary**: Brain generates specs; House compiles and mounts.

**Deliverables**:
- `src/brain_v2/engine/spec_generators.py` (new) — intent → UI/feature/task specs
- `src/os_kernel/ui_spec.py`, `feature_compiler.py`, `feature_registry.py` (house side)
- Tests for spec generation, compilation, mount/unmount

### Phase 4: Proactive Intelligence (Ongoing)
- Spontaneity engine (idle-time reasoning)
- Temporal memory consolidation
- Collective pulse (multi-brain sync over LAN)
- Advanced ethical reasoning scenarios

## 6. Security and Sovereignty Guardrails (Immutable)
- DNA anchor and hardware binding remain read-only authority
- Self-modifying paths cannot alter immutable security modules (`ethical_heart`, `zero_trust`, `dna_anchor`)
- Every promoted cognitive upgrade must produce signed manifest and hash
- Never execute generated code directly without sandbox preflight (house responsibility)

## 7. Measurable Cognitive KPIs
| KPI | Target |
|-----|--------|
| p50 intent-to-action latency (cognitive path only) | < 50ms warm |
| p95 latency under CPU stress | < 100ms |
| Cognitive memory footprint (brain_v2 only) | < 200MB base |
| Successful self-upgrade rate without rollback | ≥ 90% |
| Security policy violations blocked at gate | 100% |
| Spec generation accuracy (intent → valid spec) | ≥ 95% |

## 8. First Concrete Next Step
Implement Phase 1 baseline:
1. Add `JayaIR` schema (typed, validated, serializable)
2. Connect Lingua Logica output to JayaIR translator
3. Execute via cached plan runner (cognitive plan reuse)
4. Benchmark repeated cognitive workloads
