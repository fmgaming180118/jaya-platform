# Cognitive Features — JAYA_CORE

## Overview

JAYA_CORE implements **cognitive capabilities** — the brain's ability to understand, reason, plan, and remember. These are not knowledge retrieval features; they are **intelligence primitives**.

---

## 1. Intent Understanding

### Pipeline: Natural Language → Structured Intent

```
User Input → IntentEngine → IntentMatch → LinguaLogica → SExpression → JayaIR
```

### IntentEngine (`src/brain_v2/engine/intent_engine.py`)

**Capabilities:**
- **TF-IDF + n-gram matching** — Fast, lightweight intent classification
- **Online learning** — `learn(text)` adds new patterns incrementally
- **Confidence scoring** — Probabilistic output with threshold filtering
- **Parameter extraction** — Named entity recognition for template parameters

**API:**
```python
engine = IntentEngine()
engine.learn("show login dialog with username and password")
engine.learn("create dashboard with metrics and charts")

matches = engine.match("show login dialog")
# Returns: [IntentMatch(intent_type="show_login_dialog", confidence=0.92, 
#                      suggested_ui="login_dialog", parameters={"fields": ["username", "password"]})]
```

**Key Features:**
- Incremental vocabulary building (no retraining needed)
- Multi-intent support (returns ranked list)
- Persistence via `save()` / `load()`

---

## 2. Semantic Normalization (Lingua Logica)

### Purpose
Convert ambiguous natural language into **canonical logical forms** (S-expressions) that can be validated, optimized, and translated to JayaIR.

### Example
```
Input: "show me the login dialog with username and password fields"
         │
         ▼
SExpression: (show (dialog login) (fields username password))
         │
         ▼
JayaIR: {opcode: EMIT, operands: [UI_SPEC, login_dialog, {fields: [username, password]}]}
```

### Validation
- Type checking on operands
- Arity validation per opcode
- Semantic consistency (e.g., required fields present)

---

## 3. Reasoning Pipeline (JayaIR)

### JayaIR — Internal Canonical Language

**Design Goals:**
- **Typed** — Strict operand types (INT, FLOAT, STRING, BOOL, REF, VECTOR)
- **Validatable** — Schema validation before execution
- **Serializable** — JSON transport between brain/house
- **Optimizable** — Graph structure enables caching, fusion, parallelization
- **Cacheable** — Hash-based plan caching for repeated intents

### Opcode Categories

| Category | Opcodes | Purpose |
|---|---|---|
| **Control Flow** | CALL, BRANCH, LOOP, RETURN | Execution structure |
| **Data Ops** | LOAD, STORE, TRANSFORM, AGGREGATE | Data manipulation |
| **Logic** | AND, OR, NOT, COMPARE | Boolean reasoning |
| **Memory** | MEM_READ, MEM_WRITE, MEM_CONSOLIDATE | Memory operations |
| **Learning** | LEARN, ADAPT, EVOLVE | Self-improvement |
| **I/O** | EMIT, RECEIVE | Brain↔House communication |
| **Meta** | NOOP, CHECKPOINT | Debugging, snapshots |

### Execution Flow
```
JayaIR Graph → TaskPlanner → ExecutionPlan (DAG) → IronEngine → Cached Plans → Result
```

**Caching Strategy:**
- Hash JayaIR graph → lookup in `plan_cache`
- Cache hit: execute callable directly (sub-ms)
- Cache miss: compile → cache → execute

---

## 4. Planning

### TaskPlanner (`src/brain_v2/extensions/twin/task_planner.py`)

**Responsibilities:**
- Convert JayaIR graph → ExecutionPlan (DAG of callable blocks)
- Dependency resolution (data flow between ops)
- Parallelization hints (independent branches → PAR)
- Resource-aware scheduling (respects ResourceMonitor)

**Output:**
```python
@dataclass
class ExecutionPlan:
    steps: List[ExecutionStep]      # Ordered callable blocks
    dependencies: Dict[str, List[str]]  # Step ID → prerequisite IDs
    parallel_groups: List[List[str]]    # Steps that can run in parallel
    estimated_latency_ms: float
    required_resources: Dict[str, float]
```

---

## 5. Memory Strategy

### Temporal Weighting (Pillar 27)
- Exponential decay on memory relevance
- Short-term: high weight, fast access
- Long-term: consolidated, compressed

### Holographic Memory (Pillar 8)
- Distributed representation (fault-tolerant)
- Fuzzy recall (approximate matching)
- Noise-resistant

### Consolidation Pipeline
```
Working Memory → (sleep/idle) → Consolidation → Long-term Storage
     │                                    │
     └─ ResourceMonitor triggers ────────┘ (Pillar 2 integration)
```

---

## 6. Proactive Intelligence (Pillars 4-5, 30-40)

### Spontaneity (Pillar 6)
- Entropy-based exploration during idle
- Generates hypotheses, explores knowledge gaps
- Controlled by `StochasticSpontaneity` engine

### Narrative Continuity (Pillar 31)
- Persistent autobiographical log
- Daily summaries, decision rationale
- Enables long-term coherence

### Collective Pulse (Pillar 32)
- LAN-sync of algorithmic discoveries (ZK-proof)
- No private data shared
- Federated learning lite

### Meta-Cognitive Planning (Pillar 38)
- Internal scratchpad for strategy evaluation
- "Thinking about thinking" before acting
- Adapts approach based on past outcomes

---

## Integration Points

| Cognitive Feature | Output | Consumed By |
|---|---|---|
| Intent Understanding | `IntentMatch` | LinguaLogica, IntentToUIPipeline |
| Semantic Normalization | `SExpression` | JayaIRTranslator |
| JayaIR Generation | `JayaIR` | TaskPlanner, IronEngine |
| Planning | `ExecutionPlan` | IronEngine |
| Memory | `MemoryCapsule` | IntentEngine (context), Reasoning |
| Proactive | `Hypothesis` | SelfBootstrap, EvolutionGate |

---

## Testing Cognitive Features

```bash
# Intent Engine
python -m pytest tests/test_new_pillars.py::test_intent_engine_learn_and_predict -v

# JayaIR Pipeline
python -m pytest tests/test_phase1_jaya_ir.py -v

# Full Pipeline (Phase 1)
python -m pytest tests/test_phase1_ir_benchmark.py tests/test_phase1_benchmark_gate.py -v

# Phase 3C: Intent → UI
python -m pytest tests/test_phase3c_intent_to_ui.py -v
```

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md) — Full pipeline diagram
- [API Reference](../02-architecture/api-reference.md) — Interface definitions
- [Self-Improvement](self-improvement.md) — Morphic, Evolution Gate
- [Dynamic Spec Generation](dynamic-spec-gen.md) — Intent → UI/Feature specs
- [Resource-Aware](resource-aware.md) — Adaptive sparsity
- [Roadmap Phase 1](../06-roadmap/phase-1-cognitive-foundation.md)