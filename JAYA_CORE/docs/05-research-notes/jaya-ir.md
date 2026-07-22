# JayaIR — JAYA_CORE Internal Canonical Language

## Overview

JayaIR (JAYA Intermediate Representation) is the **typed, validated, cacheable internal language** that bridges semantic understanding (Lingua Logica) and fast execution (IronEngine).

---

## Design Principles

| Principle | Implementation |
|---|---|
| **Typed** | Strict operand types (INT, FLOAT, STRING, BOOL, REF, VECTOR) |
| **Validatable** | Schema validation before execution |
| **Serializable** | JSON transport between brain/house |
| **Optimizable** | Graph structure enables caching, fusion, parallelization |
| **Cacheable** | Hash-based plan caching for repeated intents |
| **Frozen Schema** | v0.1 frozen for Phase 1; changes require handoff doc |

---

## Schema

### JayaIR Graph
```json
{
  "version": "0.1",
  "nodes": [
    {
      "id": "node_1",
      "opcode": "LOAD",
      "operands": [
        {"type": "STRING", "value": "user_input"}
      ],
      "metadata": {"source": "intent_parameter"}
    },
    {
      "id": "node_2", 
      "opcode": "REASON",
      "operands": [
        {"type": "REF", "value": "node_1"},
        {"type": "STRING", "value": "classify_intent"}
      ],
      "metadata": {"cacheable": true}
    },
    {
      "id": "node_3",
      "opcode": "EMIT",
      "operands": [
        {"type": "REF", "value": "node_2"},
        {"type": "STRING", "value": "ui_spec"}
      ],
      "metadata": {"target": "os_kernel"}
    }
  ],
  "edges": [
    {"from": "node_1", "to": "node_2"},
    {"from": "node_2", "to": "node_3"}
  ],
  "entry_point": "node_1",
  "metadata": {
    "intent_hash": "sha256:...",
    "created_at": "2026-07-21T10:30:00Z"
  }
}
```

### Opcode Registry (v0.1 Frozen)

| Opcode | Category | Operands | Description |
|---|---|---|---|
| `CALL` | Control | [fn_ref, args...] | Call function |
| `BRANCH` | Control | [cond, then_ref, else_ref] | Conditional |
| `LOOP` | Control | [iter_ref, body_ref] | Loop |
| `RETURN` | Control | [value_ref] | Return value |
| `LOAD` | Data | [value] | Load constant |
| `STORE` | Data | [ref, value_ref] | Store to memory |
| `TRANSFORM` | Data | [input_ref, fn_ref] | Transform data |
| `AGGREGATE` | Data | [refs..., fn_ref] | Aggregate multiple |
| `AND` | Logic | [bool_ref, bool_ref] | Logical AND |
| `OR` | Logic | [bool_ref, bool_ref] | Logical OR |
| `NOT` | Logic | [bool_ref] | Logical NOT |
| `COMPARE` | Logic | [left_ref, op, right_ref] | Comparison |
| `MEM_READ` | Memory | [key_ref] | Read memory |
| `MEM_WRITE` | Memory | [key_ref, value_ref] | Write memory |
| `MEM_CONSOLIDATE` | Memory | [pattern_ref] | Consolidate memories |
| `LEARN` | Learning | [pattern_ref, weight] | Learn pattern |
| `ADAPT` | Learning | [module_ref, params] | Adapt module |
| `EVOLVE` | Learning | [candidate_ref] | Evolve candidate |
| `EMIT` | I/O | [spec_type, spec_ref] | Emit spec to house |
| `RECEIVE` | I/O | [channel_ref] | Receive from house |
| `NOOP` | Meta | [] | No operation |
| `CHECKPOINT` | Meta | [state_ref] | Checkpoint state |

---

## Translation Pipeline

```
Natural Language
       │
       ▼
IntentEngine (TF-IDF + n-gram)
       │
       ▼
IntentMatch {intent_type, confidence, suggested_ui, parameters}
       │
       ▼
LinguaLogica.normalize() → SExpression
       │
       ▼
SExpression: (show (dialog login) (fields username password))
       │
       ▼
JayaIRTranslator.translate() → JayaIR Graph
       │
       ▼
JayaIR Graph (validated, serialized)
       │
       ▼
TaskPlanner → ExecutionPlan (DAG)
       │
       ▼
IronEngine.execute_jaya_ir() → Cached Plan → Result
```

---

## Plan Caching

### Cache Key Generation
```python
def compute_cache_key(jaya_ir: JayaIR) -> str:
    """Deterministic hash of JayaIR graph structure."""
    canonical = serialize_deterministic(jaya_ir)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]
```

### Cache Lookup
```python
def execute_jaya_ir(self, ir: JayaIR) -> ExecutionResult:
    cache_key = compute_cache_key(ir)
    
    # Check cache
    if cache_key in self.plan_cache:
        plan = self.plan_cache[cache_key]
        return plan.execute()  # Sub-millisecond
    
    # Compile new plan
    plan = self.task_planner.plan(ir)
    self.plan_cache[cache_key] = plan
    return plan.execute()
```

### Cache Invalidation
- Schema version change (v0.1 → v0.2)
- Security module updates (EthicalHeart, ZeroTrust)
- Manual: `engine.clear_cache()`

---

## Validation

### Schema Validation
```python
def validate_jaya_ir(ir: JayaIR) -> ValidationResult:
    errors = []
    
    # Opcode validity
    if ir.opcode not in JayaIROpcode:
        errors.append(f"Invalid opcode: {ir.opcode}")
    
    # Operand count
    expected = OPCODE_ARITY[ir.opcode]
    if len(ir.operands) != expected:
        errors.append(f"Opcode {ir.opcode} expects {expected} operands, got {len(ir.operands)}")
    
    # Operand types
    for i, (operand, expected_type) in enumerate(zip(ir.operands, OPCODE_OPERAND_TYPES[ir.opcode])):
        if operand.type != expected_type:
            errors.append(f"Operand {i}: expected {expected_type}, got {operand.type}")
    
    # Graph structure (if full graph)
    if hasattr(ir, 'nodes'):
        # Check connectivity, cycles, entry point
        ...
    
    return ValidationResult(valid=len(errors)==0, errors=errors)
```

---

## Performance Characteristics

| Metric | Target | Achieved (Phase 3C) |
|---|---|---|
| Translation (NL → JayaIR) | < 1ms | 0.3ms |
| Validation | < 0.1ms | 0.02ms |
| Plan Compilation (cold) | < 5ms | 2.3ms |
| Plan Execution (warm) | < 0.05ms | 0.032ms |
| Cache Hit Rate | > 95% | 97.5% |
| Graph Size (typical) | < 20 nodes | 8-15 nodes |

---

## Versioning & Evolution

### v0.1 (Phase 1 - Frozen)
- Core opcodes (22)
- Basic operand types (6)
- Graph structure
- JSON serialization

### v0.2 (Planned - Phase 3+)
- Vector/tensor operands
- Gradient ops (for learning)
- Distributed execution hints
- Capability-based permissions in metadata

### Migration Strategy
```python
def migrate_jaya_ir_v0_1_to_v0_2(ir_v1: JayaIR) -> JayaIR:
    """Automatic migration for forward compatibility."""
    # Add default metadata fields
    # Convert legacy operand formats
    # Preserve semantic equivalence
    return ir_v2
```

---

## Testing

```bash
# JayaIR unit tests
python -m pytest tests/test_phase1_jaya_ir.py -v

# Benchmark (includes JayaIR pipeline)
python scripts/benchmark_phase1_ir.py --rounds 40 --gate

# Validation tests
python -m pytest tests/ -k "validation" -v
```

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md) — JayaIR in pipeline
- [API Reference](../02-architecture/api-reference.md) — JayaIR, OpCode interfaces
- [Cognitive Features](cognitive-features.md) — Full cognitive pipeline
- [Roadmap Phase 1](../06-roadmap/phase-1-cognitive-foundation.md) — Implementation plan