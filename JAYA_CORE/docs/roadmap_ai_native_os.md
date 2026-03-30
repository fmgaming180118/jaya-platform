# JAYA OS AI-Native Roadmap (for JAYA_CORE)

## 1. Objective
Build an AI-native OS core where JAYA can:
- translate user intent into executable low-level operations quickly,
- improve its own execution path safely,
- generate and attach new OS features (for example a Windows-like desktop UI) on demand.

This roadmap stays inside JAYA_CORE and reuses the active V17 architecture.

## 1.1 Canonical System Boundary (House Model)
- `os_kernel` is JAYA OS itself: the house where JAYA lives.
- `brain_v2` is JAYA's AI mind: the resident/intelligence inside the house.
- JAYA language stack (Lingua Logica -> JayaIR -> execution stubs) is the internal utility layer that complements the house.

Design implication:
- OS lifecycle, shell, features, and UI belong to `os_kernel`.
- reasoning, planning, intent, and self-improvement logic belong to `brain_v2`.
- language modules must be reusable by both sides, but authority over OS resources remains in `os_kernel`.

## 2. Architectural Principles
- Runtime robustness first, then speed.
- Resource-aware by default (CPU, RAM, battery).
- Security gates cannot be bypassed by self-modification.
- Incremental evolution with benchmark-based promotion.
- Keep modules small and composable.

## 3. Target Architecture

### 3.0 Home vs Resident Split
1. `os_kernel` (Home Layer):
   - owns device-facing runtime, shell, windowing, feature mounting, and OS policy enforcement.
2. `brain_v2` (Resident Layer):
   - owns cognition, intent interpretation, memory strategy, planning, and optimization logic.
3. Language Layer (Home Utility):
   - provides intent translation and execution IR contracts used by both layers.
   - does not directly bypass `os_kernel` policy controls.

### 3.1 Jaya Intent Pipeline (Natural Language -> Machine-Ready Plan)
1. Intent capture:
   - Existing: brain_v2/engine/intent_engine.py
2. Semantic normalization:
   - Existing: brain_v2/soul/lingua_logica.py
3. Typed IR generation (new):
   - Add `JayaIR` with strict opcodes and typed operands.
4. Execution planning:
   - Existing: brain_v2/extensions/twin/task_planner.py
5. Fast execution path:
   - Existing: brain_v2/engine/runtime.py
   - New: specialize frequently used JayaIR graphs into cached callable blocks.

### 3.2 Jaya Internal Language Strategy
Do not replace all existing languages immediately. Use a staged language stack:
- Layer A: human-facing commands (Indonesian/English).
- Layer B: Lingua Logica forms.
- Layer C: JayaIR (new internal canonical language).
- Layer D: machine-proximate execution stubs (optimized Python + optional .pyd routes).

Success metric:
- p50 intent-to-action latency reduced by >= 40% on repeated tasks.

### 3.3 Self-Upgrade Engine (Safe Evolution)
Use current morphic/self-bootstrap components with stricter promotion gates:
- Candidate generation:
  - Existing: brain_v2/engine/morphic.py
  - Existing: brain_v2/engine/self_bootstrap.py
- Safety filters:
  - Existing: brain_v2/soul/ethical_heart.py
  - Existing: brain_v2/protection/zero_trust.py
- Promotion gate (new policy):
  - Functional tests pass.
  - No security regression.
  - Throughput gain >= threshold (for example 8%).
  - RAM increase <= threshold (for example 5%).
- Rollback:
  - mandatory auto-rollback if checks fail at runtime.

### 3.4 Dynamic Feature Injection (Desktop UI on Demand)
Add a feature compiler path:
1. User request: "create Windows-like desktop".
2. Convert to UI spec (`SceneGraph`, `WidgetTree`, style tokens).
3. Generate feature package module.
4. Run in sandbox first.
5. Promote and mount into OS shell if accepted.

New minimal modules:
- `src/os_kernel/ui_spec.py` (typed UI spec)
- `src/os_kernel/feature_compiler.py` (spec -> runnable feature)
- `src/os_kernel/feature_registry.py` (versioned feature mounting)

### 3.5 Resource Efficiency Plan
- Reuse resource monitor feedback loops for adaptive quality.
- Keep hot-path caches bounded and observable.
- Use sparse activation defaults for non-critical tasks.
- Prefer AOT cache of frequent JayaIR plans over continuous recompilation.

## 4. Implementation Phases

### Phase 1 (Foundation, 1-2 weeks)
- Define `JayaIR` schema and validator.
- Integrate Lingua Logica -> JayaIR translator.
- Add execution cache for repeated intents.

Boundary for this phase:
- In scope: `brain_v2` language/execution pipeline and benchmark gate.
- Out of scope: `os_kernel` shell/runtime feature mounting changes.

Deliverables:
- `src/brain_v2/engine/jaya_ir.py` (new)
- `src/brain_v2/engine/jaya_ir_exec.py` (new)
- unit tests for parse/validate/execute.

### Phase 2 (Safe self-upgrade, 1-2 weeks)
- Implement benchmark + security promotion gate.
- Add signed candidate metadata and deterministic rollback hooks.

Deliverables:
- `src/brain_v2/engine/evolution_gate.py` (new)
- tests for pass/fail promotion and rollback.

### Phase 3 (Dynamic UI features, 2-3 weeks)
- Build UI spec model + feature compiler + registry.
- Implement one reference feature: desktop shell with window manager basics.

Boundary for this phase:
- Main implementation owner is `os_kernel` (home layer).
- `brain_v2` only provides intent/spec generation and planning assistance.

Deliverables:
- `src/os_kernel/ui_spec.py` (new)
- `src/os_kernel/feature_compiler.py` (new)
- `src/os_kernel/feature_registry.py` (new)
- tests for compile/mount/unmount.

## 5. Security and Sovereignty Guardrails
- DNA anchor and hardware binding remain read-only authority.
- Self-modifying paths cannot alter immutable security modules.
- Every promoted feature must produce signed manifest and hash.
- Never execute generated feature code directly without sandbox preflight.

## 6. Measurable KPIs
- p50 intent-to-action latency.
- p95 latency under CPU stress.
- memory footprint per active feature.
- successful self-upgrade rate without rollback.
- security policy violations blocked at gate.

## 7. First Concrete Next Step
Implement Phase 1 baseline:
1. add `JayaIR` schema,
2. connect Lingua Logica output to JayaIR,
3. execute via cached plan runner,
4. benchmark repeated command workloads.
