# Phase 1: Cognitive Foundation

## Objective
Establish the core reasoning pipeline: **Intent → Lingua Logica → JayaIR → Cached Execution**

---

## Scope
- **In scope**: `brain_v2` language/execution pipeline, benchmark gate
- **Out of scope**: `os_kernel` shell/runtime feature mounting changes

---

## Deliverables

| # | Deliverable | File | Status |
|---|---|---|---|
| 1 | JayaIR schema (v0.1 frozen) | `src/brain_v2/engine/jaya_ir.py` | ✅ |
| 2 | JayaIR validator | `src/brain_v2/engine/jaya_ir.py` | ✅ |
| 3 | Lingua Logica → JayaIR translator | `src/brain_v2/soul/lingua_logica.py` | ✅ |
| 4 | JayaIR executor | `src/brain_v2/engine/jaya_ir_exec.py` | ✅ |
| 5 | IronEngine with plan caching | `src/brain_v2/engine/runtime.py` | ✅ |
| 6 | Benchmark gate script | `scripts/benchmark_phase1_ir.py` | ✅ |
| 7 | Unit tests | `tests/test_phase1_jaya_ir.py` | ✅ |
| 8 | Benchmark tests | `tests/test_phase1_ir_benchmark.py` | ✅ |
| 9 | Benchmark gate tests | `tests/test_phase1_benchmark_gate.py` | ✅ |
| 10 | Architecture boundary tests | `tests/test_phase1_architecture_boundary.py` | ✅ |

---

## Technical Details

### JayaIR Schema (v0.1 Frozen)
```python
@dataclass
class JayaIR:
    opcode: str                   # From JayaIROpcode enum (22 opcodes)
    operands: List[Operand]       # Typed: INT, FLOAT, STRING, BOOL, REF, VECTOR
    metadata: Dict = field(default_factory=dict)
```

### Pipeline Flow
```
User Input
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
JayaIRTranslator.translate() → JayaIR Graph
    │
    ▼
TaskPlanner → ExecutionPlan (DAG)
    │
    ▼
IronEngine.execute_jaya_ir()
    │
    ├─► Cache lookup (hash → callable) → HIT: execute (0.03ms)
    │
    └─► MISS: compile → cache → execute (2.3ms)
```

### Benchmark Gate Thresholds
| Metric | Threshold | Rationale |
|---|---|---|
| p50 warm latency | ≤ 0.05 ms | Sub-millisecond cognitive step |
| p95 warm latency | ≤ 0.10 ms | Predictable tail latency |
| Cache hit rate | ≥ 95% | Effective plan reuse |

---

## Verification Commands

```bash
# Unit tests
python -m pytest tests/test_phase1_jaya_ir.py -v

# Benchmark tests
python -m pytest tests/test_phase1_ir_benchmark.py tests/test_phase1_benchmark_gate.py -v

# Architecture boundary
python -m pytest tests/test_phase1_architecture_boundary.py -v

# Full Phase 1 gate
python scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate \
  --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95

# Snapshot for docs
python scripts/benchmark_phase1_ir.py --rounds 80 --gate \
  --json-out docs/phase1_benchmark_latest.json
```

---

## Success Criteria ✅ ALL MET

- [x] JayaIR schema defined, validated, serializable
- [x] Lingua Logica → JayaIR translation working
- [x] Execution cache functional (hit rate > 95%)
- [x] Benchmark gate passes (p50=0.032ms, p95=0.078ms, hit-rate=97.5%)
- [x] Architecture boundary enforced (brain_v2 ↛ os_kernel imports)
- [x] All 15+ Phase 1 tests passing

---

## Handoff to Phase 2

**Document**: `docs/PHASE1_TO_PHASE2_HANDOFF.md`

**Key Contracts:**
- JayaIR schema v0.1 frozen — changes require handoff doc
- Benchmark thresholds established
- Plan cache interface stable
- IronEngine API stable

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [API Reference](../02-architecture/api-reference.md)
- [JayaIR Research Notes](../05-research-notes/jaya-ir.md)
- [Roadmap Overview](../06-roadmap/README.md)