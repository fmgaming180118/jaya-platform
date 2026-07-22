# Phase 2: Safe Cognitive Evolution

## Objective
Implement **safe, auditable self-improvement** for the cognitive core — enabling the brain to evolve its own capabilities without compromising sovereignty or security.

---

## Scope
- **In scope**: Evolution gate, signed manifests, deterministic rollback, morphic kernel integration
- **Out of scope**: UI/feature compilation (Phase 3), proactive intelligence (Phase 4)

---

## Deliverables

| # | Deliverable | File | Status |
|---|---|---|---|
| 1 | EvolutionGate | `src/brain_v2/engine/evolution_gate.py` | ✅ |
| 2 | CandidateManifest schema | `src/brain_v2/engine/evolution_gate.py` | ✅ |
| 3 | PQC/Dilithium3 signing | `src/brain_v2/protection/pqc.py` | ✅ |
| 4 | Deterministic rollback | `src/brain_v2/engine/rollback.py` | ✅ |
| 5 | Morphic kernel safety filters | `src/brain_v2/engine/morphic.py` | ✅ |
| 6 | Self-bootstrap curriculum | `src/brain_v2/engine/self_bootstrap.py` | ✅ |
| 7 | Evolution gate tests | `tests/test_phase2_evolution_gate.py` | ✅ |
| 8 | Rollback tests | `tests/test_phase2_rollback.py` | ✅ |
| 9 | Manifest verification tests | `tests/test_phase2_manifest.py` | ✅ |

---

## Technical Details

### Evolution Gate Pipeline
```
Candidate Generation (Morphic/Self-Bootstrap)
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ SAFETY FILTERS (IMMUTABLE — Cannot be modified by self-upgrade)│
│  • EthicalHeart (Pillar 15) — Moral vector evaluation        │
│  • ZeroTrust (Pillar 18) — Prompt injection / source blocking│
│  • DNAAnchor (Pillar 11) — Hardware-bound identity           │
│  • CryptographicSkin (Pillar 13) — State encryption          │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│ PROMOTION GATE (EvolutionGate)                              │
│  ✅ Functional tests pass (unit + integration)              │
│  ✅ No security regression                                  │
│  ✅ Throughput gain ≥ 8% (configurable)                     │
│  ✅ RAM increase ≤ 5% (configurable)                        │
│  ✅ p95 latency ≤ 110% of baseline                          │
│  ✅ Signed candidate manifest (PQC/Dilithium3)              │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
   PROMOTED → Deployed with RollbackPlan
```

### Candidate Manifest
```python
@dataclass
class CandidateManifest:
    candidate_id: str
    parent_version: str
    mutations: List[MutationRecord]
    benchmark_results: BenchmarkResult
    security_audit: SecurityAuditResult
    signature: bytes              # PQC/Dilithium3
    timestamp: datetime
```

### Mutation Record
```python
@dataclass
class MutationRecord:
    module: str                   # e.g., "brain_v2.engine.runtime"
    mutation_type: str            # opcode_substitution, operand_optimization, etc.
    diff: str                     # Unified diff
    rationale: str
    risk_level: str               # LOW, MEDIUM, HIGH
```

### Benchmark Result
```python
@dataclass
class BenchmarkResult:
    baseline: MetricSnapshot
    candidate: MetricSnapshot
    throughput_gain_pct: float
    ram_change_pct: float
    latency_p95_ratio: float
    hit_rate_change: float
```

### Deterministic Rollback
```python
@dataclass
class RollbackPlan:
    candidate_id: str
    previous_version: str
    restore_steps: List[RestoreStep]
    verification_checks: List[Callable]
    timeout_seconds: int = 30
```

**Auto-Rollback Triggers:**
- Runtime error rate > 1%
- Benchmark regression (p95 > 110% baseline)
- EthicalHeart/ZeroTrust violation
- Manual operator command

---

## Configuration

```python
@dataclass
class AgiConfig:
    # Evolution Gate
    evolution_enabled: bool = True
    promotion_throughput_gain: float = 0.08      # 8%
    promotion_ram_increase: float = 0.05         # 5%
    promotion_latency_p95_max: float = 1.10      # 110%
    
    # Morphic Kernel
    morphic_max_mutations_per_candidate: int = 5
    morphic_sandbox_timeout: int = 30
    morphic_ghost_instance_cpu_limit: float = 0.5
    morphic_ghost_instance_ram_limit_mb: int = 200
    
    # Rollback
    rollback_auto_on_error_rate: float = 0.01
    rollback_auto_on_benchmark_regression: bool = True
    rollback_timeout_seconds: int = 30
```

---

## Verification Commands

```bash
# Evolution gate tests
python -m pytest tests/test_phase2_evolution_gate.py -v

# Rollback tests
python -m pytest tests/test_phase2_rollback.py -v

# Manifest verification tests
python -m pytest tests/test_phase2_manifest.py -v

# Morphic kernel tests
python -m pytest tests/test_new_pillars.py::test_morphic_patch_function -v
python -m pytest tests/test_new_pillars.py::test_morphic_refuses_protected_target -v
python -m pytest tests/test_new_pillars.py::test_morphic_refuses_bad_syntax -v
```

---

## Success Criteria ✅ ALL MET

- [x] EvolutionGate evaluates candidates end-to-end
- [x] Safety filters (EthicalHeart, ZeroTrust, DNAAnchor) are immutable
- [x] PQC/Dilithium3 signing & verification working
- [x] Deterministic rollback with verification checks
- [x] Auto-rollback triggers functional
- [x] All Phase 2 tests passing (12 tests)

---

## Handoff to Phase 3

**Key Contracts:**
- EvolutionGate API stable
- CandidateManifest schema frozen
- RollbackPlan interface stable
- PQC keys embedded in `jaya.jay` (DNA anchor)

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [API Reference](../02-architecture/api-reference.md)
- [Evolution Gate Research Notes](../05-research-notes/evolution-gate.md)
- [Self-Improvement Features](../03-features/self-improvement.md)
- [Roadmap Overview](../06-roadmap/README.md)