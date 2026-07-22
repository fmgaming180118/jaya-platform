# Self-Improvement — JAYA_CORE

## Overview

JAYA_CORE implements **safe, auditable self-improvement** — the brain's ability to evolve its own cognitive capabilities without compromising sovereignty or security.

---

## Architecture: Morphic Kernel + Evolution Gate

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SELF-IMPROVEMENT PIPELINE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  CANDIDATE GENERATION                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  Morphic Kernel (brain_v2/engine/morphic.py)                        │   │
│  │  • AST-based code transformation                                    │   │
│  │  • Targeted mutations (opcode substitution, operand optimization)   │   │
│  │  • Self-Bootstrap (brain_v2/engine/self_bootstrap.py)               │   │
│  │  • Generates candidate cognitive modules                            │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│                         SAFETY FILTERS (IMMUTABLE)                          │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • EthicalHeart — moral vector evaluation (Pillar 15)               │   │
│  │  • ZeroTrust — prompt injection / unknown source blocking (Pillar 18)│   │
│  │  • DNAAnchor — hardware-bound identity (Pillar 11)                  │   │
│  │  • CryptographicSkin — state encryption (Pillar 13)                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│                         PROMOTION GATE (EvolutionGate)                      │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  brain_v2/engine/evolution_gate.py                                  │   │
│  │  ✅ Functional tests pass                                           │   │
│  │  ✅ No security regression                                          │   │
│  │  ✅ Throughput gain ≥ threshold (default 8%)                        │   │
│  │  ✅ RAM increase ≤ threshold (default 5%)                           │   │
│  │  ✅ Signed candidate manifest (PQC/Dilithium3)                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│                         DEPLOYMENT WITH ROLLBACK                            │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  • Deterministic rollback hooks                                     │   │
│  │  • Signed manifest verification                                     │   │
│  │  • Auto-rollback on runtime failure                                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Morphic Kernel (Candidate Generation)

### `src/brain_v2/engine/morphic.py`

**Mutation Strategies:**
| Strategy | Description | Example |
|---|---|---|
| `opcode_substitution` | Replace opcode with semantically equivalent | `SEQ` → `PAR` (if independent) |
| `operand_optimization` | Simplify operand expressions | `LOAD x; LOAD y; ADD` → `LOAD (x+y)` |
| `loop_unrolling` | Unroll small fixed loops | `LOOP 3 {CALL f}` → `CALL f; CALL f; CALL f` |
| `cache_injection` | Add plan caching hints | Insert `CHECKPOINT` before expensive ops |
| `sparsity_adaptation` | Adjust top-k based on resource profile | Dynamic `topk_ratio` per opcode |

**Safety Constraints:**
- Cannot modify: `EthicalHeart`, `ZeroTrust`, `DNAAnchor`, `CryptographicSkin`
- Cannot increase: attack surface, external dependencies
- Must preserve: JayaIR schema compatibility (v0.1 frozen)

---

## 2. Self-Bootstrap (Autonomous Curriculum)

### `src/brain_v2/engine/self_bootstrap.py`

**Phases:**
1. **Idle Detection** — ResourceMonitor signals low CPU
2. **Curriculum Selection** — Pick learning topic from gap analysis
3. **Sandboxed Experiment** — Run in isolated Ghost Instance
4. **Evaluation** — Benchmark against baseline
5. **Candidate Generation** — If improvement, create morphic candidate

**Ghost Instance:**
- Full brain_v2 clone in memory
- No access to: hardware, network, persistent storage
- Resource limits: CPU 50%, RAM 200MB, time 30s
- Rollback on any anomaly

---

## 3. Evolution Gate (Promotion)

### `src/brain_v2/engine/evolution_gate.py`

```python
@dataclass
class CandidateManifest:
    candidate_id: str
    parent_version: str
    mutations: List[MutationRecord]
    benchmark_results: BenchmarkResult
    security_audit: SecurityAuditResult
    signature: bytes              # PQC/Dilithium3 signature
    timestamp: datetime

@dataclass
class PromotionResult:
    promoted: bool
    candidate_id: str
    reason: str
    rollback_plan: RollbackPlan
```

**Gate Criteria (Configurable via AgiConfig):**
```python
promotion_throughput_gain: float = 0.08    # 8% minimum improvement
promotion_ram_increase: float = 0.05       # 5% maximum RAM increase
promotion_latency_p95_max: float = 1.10    # p95 latency ≤ 110% of baseline
```

**Test Suite Required:**
- Unit tests for modified modules
- Integration tests for affected pipelines
- Benchmark comparison (baseline vs candidate)
- Security regression tests

---

## 4. Deterministic Rollback

### `src/brain_v2/engine/rollback.py`

**Rollback Plan:**
```python
@dataclass
class RollbackPlan:
    candidate_id: str
    previous_version: str
    restore_steps: List[RestoreStep]
    verification_checks: List[Callable]
    timeout_seconds: int = 30
```

**Trigger Conditions:**
- Automatic: Runtime error rate > 1%
- Automatic: Benchmark regression detected
- Manual: Operator command
- Security: EthicalHeart/ZeroTrust violation

**Rollback Process:**
1. Freeze candidate execution
2. Restore previous module versions (atomic)
3. Verify critical paths functional
4. Log rollback event with full context
5. Alert operator

---

## 5. Signed Manifest Verification

### PQC/Dilithium3 Signing

```python
# Signing (offline, by maintainer)
private_key = load_private_key("evolution_private.key")
manifest_bytes = serialize(candidate_manifest)
signature = dilithium3_sign(private_key, manifest_bytes)
candidate_manifest.signature = signature

# Verification (runtime, automatic)
public_key = load_public_key("evolution_public.key")
is_valid = dilithium3_verify(public_key, manifest_bytes, signature)
```

**Key Management:**
- Private key: Offline, hardware security module (HSM)
- Public key: Embedded in `jaya.jay` (DNA anchor)
- Rotation: Legacy Protocol (Pillar 19) with resurrection token

---

## Testing Self-Improvement

```bash
# Evolution Gate Tests
python -m pytest tests/test_phase2_evolution_gate.py -v

# Rollback Tests
python -m pytest tests/test_phase2_rollback.py -v

# Manifest Verification Tests
python -m pytest tests/test_phase2_manifest.py -v

# Morphic Kernel Tests
python -m pytest tests/test_new_pillars.py::test_morphic_patch_function -v
python -m pytest tests/test_new_pillars.py::test_morphic_refuses_protected_target -v
```

---

## Configuration

### AgiConfig (Evolution Section)
```python
@dataclass
class AgiConfig:
    # Evolution
    evolution_enabled: bool = True
    promotion_throughput_gain: float = 0.08
    promotion_ram_increase: float = 0.05
    promotion_latency_p95_max: float = 1.10
    
    # Morphic
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

## Security Guarantees

| Guarantee | Mechanism |
|---|---|
| **No unauthorized code execution** | Sandbox + blocked builtins + import whitelist |
| **No security module modification** | Immutable pillar protection (EthicalHeart, ZeroTrust, DNAAnchor) |
| **No silent degradation** | Benchmark gate + auto-rollback |
| **Audit trail** | Signed manifests + rollback logs + narrative continuity |
| **Sovereign control** | Operator approval required for promotion (configurable) |

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md) — Self-improvement in pipeline
- [API Reference](../02-architecture/api-reference.md) — EvolutionGate, CandidateManifest interfaces
- [Cognitive Features](cognitive-features.md) — Base cognitive pipeline
- [Roadmap Phase 2](../06-roadmap/phase-2-safe-evolution.md) — Implementation plan