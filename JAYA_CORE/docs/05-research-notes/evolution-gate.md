# Evolution Gate — JAYA_CORE Safe Self-Improvement

## Overview

The Evolution Gate is the **safety-critical promotion pipeline** for cognitive self-improvement. It ensures every candidate upgrade is functionally correct, secure, performant, and auditable before deployment.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         EVOLUTION GATE PIPELINE                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. CANDIDATE GENERATION                                                    │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ Morphic Kernel (brain_v2/engine/morphic.py)                     │    │
│     │ • AST-based mutations on cognitive modules                      │    │
│     │ • Self-Bootstrap (brain_v2/engine/self_bootstrap.py)            │    │
│     │ • Ghost Instance sandboxed experiments                          │    │
│     │ • Output: CandidateModule + MutationRecord[]                    │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  2. SAFETY FILTERS (IMMUTABLE — Cannot be modified by self-upgrade)        │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ EthicalHeart (Pillar 15) — Moral vector evaluation              │    │
│     │ ZeroTrust (Pillar 18) — Prompt injection / source validation    │    │
│     │ DNAAnchor (Pillar 11) — Hardware-bound identity                 │    │
│     │ CryptographicSkin (Pillar 13) — State encryption                │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  3. BENCHMARK EVALUATION                                                    │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ • Functional test suite (unit + integration)                    │    │
│     │ • Benchmark comparison: baseline vs candidate                   │    │
│     │ • Throughput gain ≥ 8% (configurable)                           │    │
│     │ • RAM increase ≤ 5% (configurable)                              │    │
│     │ • p95 latency ≤ 110% of baseline                                │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  4. MANIFEST CREATION & SIGNING                                             │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ CandidateManifest {                                             │    │
│     │   candidate_id, parent_version, mutations[],                    │    │
│     │   benchmark_results, security_audit,                            │    │
│     │   signature (PQC/Dilithium3), timestamp                         │    │
│     │ }                                                               │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  5. PROMOTION GATE (EvolutionGate)                                          │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ brain_v2/engine/evolution_gate.py                               │    │
│     │ evaluate(candidate_manifest) → PromotionResult                  │    │
│     │   ✅ All gates pass → PROMOTED                                  │    │
│     │   ❌ Any gate fails → REJECTED + rollback_plan                  │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                    │                                        │
│                                    ▼                                        │
│  6. DEPLOYMENT WITH DETERMINISTIC ROLLBACK                                  │
│     ┌─────────────────────────────────────────────────────────────────┐    │
│     │ • Atomic module replacement                                     │    │
│     │ • RollbackPlan with verification checks                         │    │
│     │ • Auto-rollback triggers:                                       │    │
│     │     - Runtime error rate > 1%                                   │    │
│     │     - Benchmark regression detected                             │    │
│     │     - EthicalHeart/ZeroTrust violation                          │    │
│     │     - Manual operator command                                   │    │
│     └─────────────────────────────────────────────────────────────────┘    │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Candidate Manifest

```python
@dataclass
class CandidateManifest:
    candidate_id: str                    # UUID
    parent_version: str                  # e.g., "v1.2.3"
    mutations: List[MutationRecord]      # What changed
    benchmark_results: BenchmarkResult   # Before/after metrics
    security_audit: SecurityAuditResult  # Safety filter results
    signature: bytes                     # PQC/Dilithium3 signature
    timestamp: datetime
    metadata: Dict = field(default_factory=dict)

@dataclass
class MutationRecord:
    module: str                          # e.g., "brain_v2.engine.runtime"
    mutation_type: str                   # opcode_substitution, operand_optimization, etc.
    diff: str                            # Unified diff
    rationale: str                       # Why this mutation
    risk_level: str                      # LOW, MEDIUM, HIGH

@dataclass
class BenchmarkResult:
    baseline: MetricSnapshot
    candidate: MetricSnapshot
    throughput_gain_pct: float
    ram_change_pct: float
    latency_p95_ratio: float
    hit_rate_change: float

@dataclass
class MetricSnapshot:
    p50_latency_ms: float
    p95_latency_ms: float
    hit_rate: float
    ram_mb: float
    cpu_pct: float
```

---

## EvolutionGate Interface

```python
class EvolutionGate:
    def __init__(self, config: AgiConfig):
        self.config = config
        self.ethical_heart = EthicalHeart()
        self.zero_trust = ZeroTrustValidator()
        self.dna_anchor = DNAAnchor()
    
    def evaluate(self, manifest: CandidateManifest) -> PromotionResult:
        """Full gate evaluation."""
        # 1. Verify signature
        if not self._verify_signature(manifest):
            return PromotionResult(False, manifest.candidate_id, "Invalid signature")
        
        # 2. Safety filters (immutable)
        if not self.ethical_heart.is_safe(manifest):
            return PromotionResult(False, manifest.candidate_id, "EthicalHeart rejection")
        
        if not self.zero_trust.validate(manifest):
            return PromotionResult(False, manifest.candidate_id, "ZeroTrust rejection")
        
        if not self.dna_anchor.verify(manifest):
            return PromotionResult(False, manifest.candidate_id, "DNAAnchor rejection")
        
        # 3. Benchmark gates
        if not self._check_benchmarks(manifest.benchmark_results):
            return PromotionResult(False, manifest.candidate_id, "Benchmark gate failed")
        
        # 4. Functional tests
        if not self._run_functional_tests(manifest):
            return PromotionResult(False, manifest.candidate_id, "Functional tests failed")
        
        # 5. All gates passed
        rollback_plan = self._generate_rollback_plan(manifest)
        return PromotionResult(True, manifest.candidate_id, "Promoted", rollback_plan)
    
    def _check_benchmarks(self, results: BenchmarkResult) -> bool:
        return (results.throughput_gain_pct >= self.config.promotion_throughput_gain and
                results.ram_change_pct <= self.config.promotion_ram_increase and
                results.latency_p95_ratio <= self.config.promotion_latency_p95_max)
```

---

## PQC/Dilithium3 Signing

### Key Generation (Offline)
```bash
# Generate keypair (run once, store private key in HSM)
python -m src.brain_v2.protection.pqc_keygen --algorithm dilithium3 \
  --private evolution_private.key --public evolution_public.key
```

### Signing (Maintainer, Offline)
```python
from src.brain_v2.protection.pqc import dilithium3_sign, load_private_key

private_key = load_private_key("evolution_private.key")
manifest_bytes = serialize(candidate_manifest)
signature = dilithium3_sign(private_key, manifest_bytes)
candidate_manifest.signature = signature
```

### Verification (Runtime, Automatic)
```python
from src.brain_v2.protection.pqc import dilithium3_verify, load_public_key

public_key = load_public_key("evolution_public.key")  # Embedded in jaya.jay
is_valid = dilithium3_verify(public_key, manifest_bytes, signature)
```

---

## Deterministic Rollback

### RollbackPlan
```python
@dataclass
class RollbackPlan:
    candidate_id: str
    previous_version: str
    restore_steps: List[RestoreStep]
    verification_checks: List[Callable[[], bool]]
    timeout_seconds: int = 30

@dataclass
class RestoreStep:
    module: str
    previous_code: str          # Source code to restore
    previous_bytecode: bytes    # Compiled bytecode hash
```

### Rollback Execution
```python
def execute_rollback(plan: RollbackPlan) -> RollbackResult:
    for step in plan.restore_steps:
        # Atomic module replacement
        importlib.reload(sys.modules[step.module])
        # Verify bytecode hash matches
        assert hash_module(step.module) == step.previous_bytecode
    
    # Run verification checks
    for check in plan.verification_checks:
        if not check():
            raise RollbackVerificationError("Post-rollback verification failed")
    
    return RollbackResult(success=True, restored_version=plan.previous_version)
```

### Auto-Rollback Triggers
```python
class AutoRollbackMonitor:
    def __init__(self, engine: IronEngine, rollback_plan: RollbackPlan):
        self.engine = engine
        self.plan = rollback_plan
        self.error_count = 0
        self.total_requests = 0
    
    def on_request(self, success: bool):
        self.total_requests += 1
        if not success:
            self.error_count += 1
        
        # Check error rate
        if self.total_requests >= 100:
            error_rate = self.error_count / self.total_requests
            if error_rate > 0.01:  # 1%
                execute_rollback(self.plan)
    
    def on_benchmark(self, results: MetricSnapshot):
        # Compare with baseline
        if results.p95_latency_ms > self.plan.baseline.p95_latency_ms * 1.1:
            execute_rollback(self.plan)
```

---

## Configuration

```python
@dataclass
class AgiConfig:
    # Evolution Gate
    evolution_enabled: bool = True
    promotion_throughput_gain: float = 0.08      # 8%
    promotion_ram_increase: float = 0.05         # 5%
    promotion_latency_p95_max: float = 1.10      # 110% of baseline
    
    # Morphic Kernel
    morphic_max_mutations_per_candidate: int = 5
    morphic_sandbox_timeout: int = 30            # seconds
    morphic_ghost_instance_cpu_limit: float = 0.5
    morphic_ghost_instance_ram_limit_mb: int = 200
    
    # Rollback
    rollback_auto_on_error_rate: float = 0.01
    rollback_auto_on_benchmark_regression: bool = True
    rollback_timeout_seconds: int = 30
```

---

## Testing

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
python -m pytest tests/test_new_pillars.py::test_morphic_refuses_bad_syntax -v
```

---

## Security Guarantees

| Guarantee | Mechanism |
|---|---|
| **No unauthorized code execution** | Ghost Instance sandbox + blocked builtins + import whitelist |
| **No security module modification** | Immutable pillar protection (EthicalHeart, ZeroTrust, DNAAnchor, CryptoSkin) |
| **No silent degradation** | Benchmark gate + auto-rollback on regression |
| **Audit trail** | Signed manifests + rollback logs + narrative continuity (Pillar 31) |
| **Sovereign control** | Operator approval required (configurable); private key offline in HSM |
| **Quantum-resistant** | PQC/Dilithium3 signatures |

---

## 🔗 Related Docs

- [Architecture Overview](../02-architecture/overview.md) — Evolution in pipeline
- [API Reference](../02-architecture/api-reference.md) — EvolutionGate, CandidateManifest interfaces
- [Self-Improvement](../03-features/self-improvement.md) — Full self-improvement architecture
- [Roadmap Phase 2](../06-roadmap/phase-2-safe-evolution.md) — Implementation plan