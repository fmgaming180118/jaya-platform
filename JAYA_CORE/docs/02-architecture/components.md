# Components — JAYA_CORE Module Breakdown

## Brain_v2 (Resident Layer) — The Mind

### `src/brain_v2/engine/` — Execution & Language Pipeline

| Module | Purpose | Key Classes |
|---|---|---|
| `intent_engine.py` | Intent classification + online learning | `IntentEngine`, `IntentMatch` |
| `jaya_ir.py` | JayaIR schema, opcodes, validation | `JayaIR`, `OpCode`, `Operand`, `ValidationResult` |
| `jaya_ir_exec.py` | JayaIR executor (interpreter) | `JayaIRExecutor` |
| `runtime.py` | IronEngine — cached execution, resource integration | `IronEngine`, `AgiConfig`, `ExecutionResult` |
| `evolution_gate.py` | Safe self-upgrade promotion gate | `EvolutionGate`, `CandidateManifest`, `PromotionResult` |

### `src/brain_v2/soul/` — Cognitive Core

| Module | Purpose | Key Classes |
|---|---|---|
| `lingua_logica.py` | Semantic normalization (NL → S-expr) | `LinguaLogica`, `SExpression` |
| `ethical_heart.py` | Moral guardrails, action evaluation | `EthicalHeart`, `EthicalVerdict`, `ValueVector` |

### `src/brain_v2/organism/` — Biological Systems

| Module | Purpose | Key Classes |
|---|---|---|
| `resource_monitor.py` | CPU/RAM/battery → adaptive sparsity | `ResourceMonitor`, `get_readings()` |

### `src/brain_v2/protection/` — Sovereignty Shield

| Module | Purpose | Key Classes |
|---|---|---|
| `zero_trust.py` | Prompt injection defense, source validation | `ZeroTrustValidator`, `SourcePolicy` |
| `dna_anchor.py` | Hardware-bound identity (SHA3-256) | `DNAAnchor`, `HardwareFingerprint` |

### `src/brain_v2/extensions/twin/` — Digital Twin

| Module | Purpose | Key Classes |
|---|---|---|
| `task_planner.py` | Execution planning from JayaIR | `TaskPlanner`, `ExecutionPlan` |

### `src/brain_v2/genesis.py` — Identity & Bootstrap

- Binary identity loading (`jaya.jay`)
- DNA anchor verification
- Initial pillar activation

---

## Os_Kernel (Home Layer) — The Body

### `src/os_kernel/` — Feature & UI Runtime

| Module | Purpose | Key Classes |
|---|---|---|
| `feature_compiler.py` | SceneGraph → runnable Python feature | `FeatureCompiler`, `CompiledFeature` |
| `feature_registry.py` | Versioned feature discovery & mounting | `FeatureRegistry`, `FeatureManifest` |
| `feature_bridge.py` | JayaBridge — mount/dispatch/unmount | `JayaBridge` |
| `intent_to_ui.py` | Intent → UI Pipeline (Phase 3C) | `IntentToUIPipeline`, `UITemplate`, `PipelineResult` |
| `ui_spec.py` | SceneGraph, WidgetSpec, StyleTokens, factories | `SceneGraph`, `WidgetSpec`, `WidgetType`, `LayoutType`, `StyleTokens`, `create_window`, `create_button`, ... |
| `ipc.py` | Inter-process communication | `IPCChannel`, `register_ipc_handler`, `dispatch_ipc` |
| `window_manager.py` | Window lifecycle management | `WindowManager` |

### `src/os_kernel/intent_to_ui.py` — Built-in UI Templates (10)

| Template | Description | Parameters |
|---|---|---|
| `login_dialog` | Username/password form | `title`, `show_remember` |
| `dashboard` | Metric cards + charts | `metrics`, `charts` |
| `settings_dialog` | Categorized settings panels | `categories` |
| `file_explorer` | Tree view + file ops | `root_path`, `show_hidden` |
| `chat_interface` | Message list + input | `history`, `placeholder` |
| `confirm_dialog` | Yes/No/Cancel modal | `message`, `title`, `danger` |
| `progress_dialog` | Progress bar + cancel | `title`, `max_value`, `cancellable` |
| `list_view` | Selectable item list | `items`, `multi_select` |
| `form` | Dynamic form from schema | `fields`, `submit_action` |
| `generic_dialog` | Flexible content window | `title`, `content_widgets` |

---

## Language Layer (Shared) — `src/jaya_language/`

| Module | Purpose |
|---|---|
| `ui_spec.py` | **Moved to os_kernel** — UI spec types shared via import |
| `contracts.py` | Cross-layer contracts: `IntentMatch`, `PipelineResult`, `JayaActions` |
| `ir_definitions.py` | JayaIR schema definitions (OpCode, Operand) |

> **Note**: `ui_spec.py` physically lives in `os_kernel/` but is imported by both layers as the shared UI specification language.

---

## Pillar Implementations (40 Pillars)

### Layer I: Biological Soul (1-10)
| Pillar | Module | Status |
|---|---|---|
| 1. Pure Logic | `engine/runtime.py` (IronEngine) | ✅ |
| 2. Resource Aware | `organism/resource_monitor.py` | ✅ |
| 3. Active Dreaming | `engine/self_bootstrap.py` | 🔄 |
| 4. Multimodal Reflex | `engine/intent_engine.py` | ✅ |
| 5. Logical Homeostasis | `engine/twin/task_planner.py` | ✅ |
| 6. Stochastic Spontaneity | `engine/spontaneity.py` | 🔄 |
| 7. Cognitive Silence | `engine/runtime.py` (silence mode) | ✅ |
| 8. Holographic Memory | `soul/memory.py` | 🔄 |
| 9. Neural Regeneration | `engine/morphic.py` | ✅ |
| 10. Affective Metabolism | `soul/ethical_heart.py` (urgency) | ✅ |

### Layer II: Sovereignty Shield (11-20)
| Pillar | Module | Status |
|---|---|---|
| 11. DNA Anchor | `protection/dna_anchor.py` | ✅ |
| 12. Immune System | `protection/immune_system.py` | 🔄 |
| 13. Cryptographic Skin | `protection/crypto_skin.py` | ✅ |
| 14. Hardware Locked | `protection/dna_anchor.py` | ✅ |
| 15. Ethical Heart | `soul/ethical_heart.py` | ✅ |
| 16. Quantum-Resistant | `protection/pqc.py` | ✅ |
| 17. Socratic Mirror | `soul/socratic_mirror.py` | 🔄 |
| 18. Zero-Trust | `protection/zero_trust.py` | ✅ |
| 19. Legacy Protocol | `protection/legacy_protocol.py` | 🔄 |
| 20. Sovereign Privacy | `protection/privacy.py` | ✅ |

### Layer III: Iron Engine (21-29)
| Pillar | Module | Status |
|---|---|---|
| 21. Lingua Logica | `soul/lingua_logica.py` | ✅ |
| 22. Ternary Precision | `engine/ternary.py` | 🔄 |
| 23. Sandboxed Imagination | `engine/sandbox.py` | ✅ |
| 24. Morphic Kernel | `engine/morphic.py` | ✅ |
| 25. Digital Epigenetics | `engine/epigenetics.py` | 🔄 |
| 26. Semantic Bridge | `engine/semantic_bridge.py` | ✅ |
| 27. Temporal Weighting | `soul/temporal_memory.py` | ✅ |
| 28. Self-Bootstrapping | `engine/self_bootstrap.py` | 🔄 |
| 29. Binary Cortex | `genesis.py` + `engine/nano_model.py` | ✅ |

### Layer IV: Transcendental (30-40)
| Pillar | Module | Status |
|---|---|---|
| 30. Twin Protocol | `extensions/twin/twin_protocol.py` | 🔄 |
| 31. Narrative Continuity | `soul/narrative.py` | ✅ |
| 32. Collective Pulse | `engine/collective_pulse.py` | 🔄 |
| 33. Agentic RAG | `engine/agentic_rag.py` | 🔄 |
| 34. Dynamic Sparsity (MoE) | `engine/moe.py` | 🔄 |
| 35. Activation Sparsity | `engine/runtime.py` (top-k) | ✅ |
| 36. Speculative Reasoning | `engine/speculative.py` | 🔄 |
| 37. Hybrid Consciousness | `engine/hybrid.py` | ✅ |
| 38. Meta Cognitive Planning | `extensions/twin/meta_planner.py` | 🔄 |
| 39. Dynamic Objective | `soul/dynamic_objective.py` | 🔄 |
| 40. Intent Extrapolation | `engine/intent_extrapolation.py` | 🔄 |

**Legend**: ✅ Implemented | 🔄 Partial/Planned | ❌ Not Started

---

## Test Coverage (211 Tests)

| Test File | Area | Tests |
|---|---|---|
| `test_phase1_jaya_ir.py` | JayaIR parse/validate/execute | 15 |
| `test_phase1_ir_benchmark.py` | IR benchmark | 8 |
| `test_phase1_benchmark_gate.py` | Benchmark gate pass/fail | 6 |
| `test_phase1_architecture_boundary.py` | Brain↔House boundary | 4 |
| `test_phase2_evolution_gate.py` | Evolution promotion gate | 5 |
| `test_phase2_rollback.py` | Deterministic rollback | 4 |
| `test_phase2_manifest.py` | Signed manifest verification | 3 |
| `test_phase3c_intent_to_ui.py` | Intent→UI pipeline | 1 |
| `test_new_pillars.py` | Pillars 1-40 integration | 45 |
| `test_core_twin.py` | Digital twin | 12 |
| `test_speaker_id.py` | Voice identity | 9 |
| `test_connection_manager.py` | Connectivity hierarchy | 6 |
| `test_v18_nano.py` | NanoModel V18 | 18 |
| Other pillar-specific gates | Activation sparsity, MoE, Collective, etc. | ~75 |

---

## 🔗 Lanjutkan ke

- [Cognitive Features](../03-features/cognitive-features.md) — Intent, Reasoning, Planning, Memory
- [Self-Improvement](../03-features/self-improvement.md) — Morphic, Evolution Gate, Rollback
- [Dynamic Spec Generation](../03-features/dynamic-spec-gen.md) — Intent → UI/Feature/Task specs
- [Resource-Aware](../03-features/resource-aware.md) — Adaptive sparsity, top-k, silence mode