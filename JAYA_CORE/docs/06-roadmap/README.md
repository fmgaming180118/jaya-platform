# Roadmap — JAYA_CORE Cognitive Development

## Overview

```
Phase 1 (1-2 wks)  →  Phase 2 (1-2 wks)  →  Phase 3 (2-3 wks)  →  Phase 4 (Ongoing)
Cognitive          Safe Evolution        Dynamic Specs         Proactive Intelligence
Foundation         (Self-Upgrade)        Generation            (Anticipation)
```

---

## Phase 1: Cognitive Foundation ✅ COMPLETE

**Goal**: Establish core reasoning pipeline — Intent → Lingua Logica → JayaIR → Cached Execution

### Deliverables ✅
- [x] `JayaIR` schema (v0.1 frozen) — `src/brain_v2/engine/jaya_ir.py`
- [x] Lingua Logica → JayaIR translator — `src/brain_v2/soul/lingua_logica.py`
- [x] JayaIR executor — `src/brain_v2/engine/jaya_ir_exec.py`
- [x] IronEngine with plan caching — `src/brain_v2/engine/runtime.py`
- [x] Benchmark gate (p50<0.05ms, p95<0.10ms, hit-rate>95%) — `scripts/benchmark_phase1_ir.py`
- [x] Architecture boundary tests — `tests/test_phase1_architecture_boundary.py`

### Verification
```bash
python -m pytest tests/test_phase1_jaya_ir.py -v
python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate \
  --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

---

## Phase 2: Safe Evolution ✅ COMPLETE

**Goal**: Enable safe, auditable self-improvement with promotion gates and deterministic rollback.

### Deliverables ✅
- [x] Evolution Gate — `src/brain_v2/engine/evolution_gate.py`
- [x] Signed candidate manifests (PQC/Dilithium3)
- [x] Deterministic rollback hooks — `src/brain_v2/engine/rollback.py`
- [x] Manifest verification tests — `tests/test_phase2_manifest.py`
- [x] Rollback tests — `tests/test_phase2_rollback.py`
- [x] Promotion gate tests — `tests/test_phase2_evolution_gate.py`

### Verification
```bash
python -m pytest tests/test_phase2_evolution_gate.py tests/test_phase2_rollback.py tests/test_phase2_manifest.py -v
```

---

## Phase 3: Dynamic Specification Generation 🔄 IN PROGRESS (Phase 3C Done)

**Goal**: Brain generates specs (UI, Feature, Task) → House compiles & mounts.

### Phase 3C: Intent → UI Pipeline ✅ COMPLETE
- [x] `IntentToUIPipeline` — `src/os_kernel/intent_to_ui.py`
- [x] 10 built-in UI templates (login, dashboard, settings, file_explorer, chat, confirm, progress, list, form, generic)
- [x] `FeatureCompiler` — `src/os_kernel/feature_compiler.py`
- [x] `FeatureRegistry` — `src/os_kernel/feature_registry.py`
- [x] `JayaBridge` — `src/os_kernel/feature_bridge.py`
- [x] `SceneGraph` / `WidgetSpec` — `src/os_kernel/ui_spec.py`
- [x] Integration test — `tests/test_phase3c_intent_to_ui.py`

### Phase 3: Full Spec Generation (Planned)
- [ ] `SpecGeneratorRouter` — `src/brain_v2/engine/spec_generators.py`
- [ ] `UISpecGenerator` with template registry
- [ ] `FeatureSpecGenerator` for background capabilities
- [ ] `TaskSpecGenerator` delegating to TaskPlanner
- [ ] `ActionSpecGenerator` for direct IPC
- [ ] Brain-side spec generation (move from os_kernel)
- [ ] House-side compilers for all spec types

### Verification
```bash
python -m pytest tests/test_phase3c_intent_to_ui.py -v
# Future:
python -m pytest tests/ -k "spec_generator" -v
```

---

## Phase 4: Proactive Intelligence (Planned)

**Goal**: Anticipatory, autonomous intelligence — JARVIS-like proactive behavior.

### Deliverables
- [ ] Spontaneity Engine (Pillars 3, 6) — `src/brain_v2/engine/spontaneity.py`
- [ ] Speculative Reasoner (Pillar 36) — `src/brain_v2/engine/speculative.py`
- [ ] Meta-Cognitive Planner (Pillar 38) — `src/brain_v2/extensions/twin/meta_planner.py`
- [ ] Narrative Continuity (Pillar 31) — `src/brain_v2/soul/narrative.py`
- [ ] Collective Pulse (Pillar 32) — `src/brain_v2/engine/collective_pulse.py`
- [ ] Dynamic Objective (Pillar 39) — `src/brain_v2/soul/dynamic_objective.py`
- [ ] Intent Extrapolation (Pillar 40) — `src/brain_v2/engine/intent_extrapolation.py`
- [ ] Proactive Loop integration — `src/brain_v2/engine/proactive_loop.py`

### Verification
```bash
# Future tests
python -m pytest tests/ -k "spontaneity or speculative or meta_cognitive or narrative or collective or dynamic_objective or intent_extrapolation" -v
```

---

## Cross-Cutting Concerns (All Phases)

| Concern | Implementation |
|---|---|
| **Security** | Immutable pillars (EthicalHeart, ZeroTrust, DNAAnchor, CryptoSkin) |
| **Resource Awareness** | ResourceMonitor → adaptive top-k, silence mode |
| **Sovereignty** | Offline-first, LAN sync, vetted internet fallback |
| **Observability** | Narrative continuity, benchmark snapshots, signed manifests |
| **Testing** | Phase gates + 211 integration tests |

---

## Current Status Summary

| Phase | Status | Completion | Key Metric |
|---|---|---|---|
| 1: Cognitive Foundation | ✅ Done | 100% | p50=0.032ms, hit-rate=97.5% |
| 2: Safe Evolution | ✅ Done | 100% | Gate pass, rollback verified |
| 3C: Intent→UI | ✅ Done | 100% | 10 templates, pipeline test pass |
| 3: Full Spec Gen | 🔄 Planned | 0% | Spec generators in brain |
| 4: Proactive Intelligence | 📋 Planned | 0% | 8 pillars to implement |

---

## Next Immediate Steps

1. **Complete Phase 3**: Move spec generation to brain_v2 (`spec_generators.py`)
2. **House compilers**: Ensure os_kernel compiles all spec types (UI, Feature, Task, Action)
3. **Integration test**: End-to-end brain→spec→house→mount→dispatch
4. **Begin Phase 4**: Implement Spontaneity Engine as first proactive pillar

---

## 🔗 Related Docs

- [Phase 1 Detail](phase-1-cognitive-foundation.md)
- [Phase 2 Detail](phase-2-safe-evolution.md)
- [Phase 3 Detail](phase-3-dynamic-specs.md)
- [Phase 4 Detail](phase-4-proactive-intelligence.md)
- [Architecture Overview](../02-architecture/overview.md)
- [API Reference](../02-architecture/api-reference.md)