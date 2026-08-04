# Phase 2 Level 2 Remediation Plan

**Status**: `PROTOTYPE / IN PROGRESS` → Target: `IMPLEMENTED_LOCAL` → `INTEGRATED` → `VERIFIED`

---

## Executive Summary

The audit correctly identifies that Phase 2 Level 2 is **not complete**. While significant scaffolding exists, critical gaps remain:

| Component | Current Status | Target |
|-----------|---------------|--------|
| NLU-Symbolic Bridge | PROTOTYPE (entity extraction empty, hardcoded capabilities) | IMPLEMENTED_LOCAL |
| TinyNeuralNet | IMPLEMENTED_LOCAL (architecture only, no training) | TRAINED + VERIFIED |
| LiveEvolver | CONFLICTED (two implementations) | SINGLE CANONICAL |
| MorphicKernel | CONFLICTED (two implementations) | SINGLE CANONICAL |
| Verification Gates | PLACEHOLDER/BROKEN | REAL IMPLEMENTATION |
| Integration Tests | BROKEN (deterministic failures) | PASSING |
| Demo/Vertical Slice | SIMULATED | REAL END-TO-END |

---

## Phase 1: Canonical Runtime Resolution (Week 1-2)

### 1.1 Choose Single Canonical Implementation

**Decision**: Use `JAYA_CORE/src/brain_v2/` as canonical runtime. Deprecate `JAYA_CORE/src/self_improvement/`.

**Actions**:
- [ ] Remove `JAYA_CORE/src/self_improvement/` or mark as deprecated
- [ ] Update all imports to use `brain_v2` versions
- [ ] Update `IronEngine._init_intelligence()` to initialize `NLUSymbolicBridge` as primary cognitive path
- [ ] Wire `NLUSymbolicBridge` into `cognitive_reason()` method

### 1.2 Fix NLUSymbolicBridge Integration

**File**: `JAYA_CORE/src/nlu/symbolic_bridge.py`

**Issues to Fix**:
- [ ] `_parse_entities()` returns empty dict - implement real entity extraction using LLM structured output
- [ ] `_get_required_capabilities()` uses hardcoded dict - query `CapabilityRegistry` instead
- [ ] `_nlu_to_ir()` creates "simplified IR" - create proper JayaIR objects
- [ ] No ambiguity detection or alternative intents

**Implementation**:
```python
def _parse_entities(self, llm_response: str) -> Dict[str, Any]:
    """Parse entities from LLM structured JSON output."""
    # Use JSON schema validation
    # Extract: entities, slots, constraints, relations, ambiguity, alternatives
    pass

def _get_required_capabilities(self, intent_type: IntentType) -> List[str]:
    """Query CapabilityRegistry for available capabilities."""
    from JAYA_CORE.src.capabilities.registry import CapabilityRegistry
    registry = CapabilityRegistry()
    # Map intent to capability requirements dynamically
    pass
```

### 1.3 Fix SymbolicReasoner Hardcoded Values

**File**: `JAYA_CORE/src/reasoning/symbolic_reasoner.py`

**Issues to Fix**:
- [ ] `ConstraintSolver._register_default_constraints()` - hardcoded 512MB, 300s
- [ ] `ConstraintSolver._is_capability_available()` - hardcoded capability set
- [ ] Resource limits should come from `ResourceProfile` / runtime config

**Implementation**:
```python
def __init__(self, resource_profile: ResourceProfile = None):
    self.resource_profile = resource_profile or get_default_resource_profile()
    # Use profile values instead of hardcoded
```

---

## Phase 2: Neural Network Training & Integration (Week 3-4)

### 2.1 Create Training Pipeline

**Files to Create**:
- `JAYA_CORE/scripts/train_tiny_net.py` - Training script
- `JAYA_CORE/data/training/` - Training datasets
- `JAYA_CORE/src/neural/training.py` - Training loop, loss functions, validation

**Requirements**:
- [ ] Dataset: Versioned, labeled intent/entity/rerank data
- [ ] Loss functions: CrossEntropy (classify), Contrastive (embed), Margin (rerank)
- [ ] Optimizer: AdamW with cosine annealing
- [ ] Validation: Holdout set, accuracy/F1/recall metrics
- [ ] Checkpointing: Save best model, model card with metrics

### 2.2 Fix Model Size (<10M params)

**Current**: ~11M params (vocab 30k × 256 = 7.68M just embeddings)

**Solutions**:
- [ ] Reduce vocab to 15k-20k (use BPE tokenizer)
- [ ] Reduce d_model to 192 or 128
- [ ] Use shared embeddings for input/output
- [ ] Target: 8-9M params with margin

### 2.3 Replace SimpleTokenizer with Production Tokenizer

**File**: `JAYA_CORE/src/neural/symbolic_interface.py`

**Actions**:
- [ ] Train BPE/WordPiece tokenizer on domain corpus
- [ ] Save tokenizer artifact (vocab.json, merges.txt)
- [ ] Load tokenizer at runtime, not hardcoded word list
- [ ] Remove `[UNUSED_...]` placeholder tokens

### 2.4 Fix Neural Reranker 3D Input Bug

**File**: `JAYA_CORE/src/neural/tiny_net.py` line ~180

**Bug**: `forward()` unpacks `batch_size, seq_len = input_ids.shape` before checking 3D rerank input

**Fix**:
```python
def forward(self, input_ids, attention_mask=None, task="embed"):
    if task == "rerank" and input_ids.dim() == 3:
        # Handle 3D input first
        return self._forward_rerank(input_ids, attention_mask)
    # ... rest of 2D handling
```

### 2.5 Implement Neural Entity Extraction

**File**: `JAYA_CORE/src/neural/symbolic_interface.py` - `extract_entities()`

**Implementation**:
- [ ] Add sequence labeling head to TinyNeuralNet
- [ ] Train on NER dataset (CoNLL, custom domain data)
- [ ] Return structured entities: `{PERSON: [...], ORG: [...], LOC: [...]}`

### 2.6 Wire Neural Output to Symbolic Reasoning

**Integration Point**: `NLUSymbolicBridge._run_nlu()` → `NeuralSymbolicInterface`

**Actions**:
- [ ] Use neural embeddings for semantic similarity in planning
- [ ] Use neural classification for intent confidence calibration
- [ ] Use neural reranking for candidate plan selection

---

## Phase 3: Evolution & Patching - Single Canonical (Week 5-6)

### 3.1 Consolidate LiveEvolver

**Keep**: `JAYA_CORE/src/brain_v2/education/live_evolver.py` (mutates actual NanoModel weights)

**Remove/Deprecate**: `JAYA_CORE/src/self_improvement/loop.py` LiveEvolver (generic param dict)

**Actions**:
- [ ] Ensure fitness evaluation runs actual task replay
- [ ] Implement holdout benchmark suite for regression testing
- [ ] Add candidate staging (canary) before promoting to active model
- [ ] Snapshot weights before mutation, test rollback on restart

### 3.2 Consolidate MorphicKernel

**Keep**: `JAYA_CORE/src/brain_v2/engine/morphic.py` (safe, sandboxed, digest-verified)

**Remove/Deprecate**: `JAYA_CORE/src/self_improvement/loop.py` MorphicKernel (generic patching)

**Actions**:
- [ ] Extend safe patch API beyond constant-return functions
- [ ] Add allowlist for permitted patch targets
- [ ] Ensure rollback restores exact baseline (tested)

### 3.3 Fitness Tied to Real Behavior

**Current Problem**: Fitness = mean of memory scores, no re-evaluation after mutation

**Solution**:
```python
def _compute_fitness(self) -> float:
    # 1. Run benchmark suite on current weights
    # 2. Compare against baseline
    # 3. Return delta fitness
    pass
```

**Requirements**:
- [ ] Fixed benchmark task suite (held out from training)
- [ ] Run inference on benchmark tasks after each mutation
- [ ] Measure: accuracy, latency, memory, success rate
- [ ] Only accept mutation if holdout performance improves

---

## Phase 4: Verification Gates - Real Implementation (Week 7-8)

### 4.1 Property-Based Testing with Hypothesis

**File**: `JAYA_CORE/src/verification/formal.py` - `HypothesisVerifier`

**Current**: `run_tests()` is `pass`

**Implementation**:
```python
def run_tests(self, max_examples: int = 100) -> List[VerificationResult]:
    import hypothesis
    from hypothesis import given, strategies as st
    
    results = []
    for test_fn, strategy_names in self.tests:
        # Apply @given decorators dynamically
        # Run hypothesis test
        # Collect results
    return results
```

**Properties to Test**:
- [ ] Memory bounds: `len(memory) <= max_events`
- [ ] No secrets in codebase: scan with regex/entropy
- [ ] Privacy routing: sensitive → local only
- [ ] Persistence: restart → memory intact
- [ ] Rate limits: requests > limit → 429
- [ ] Audit log: security ops → log entry

### 4.2 TLA+ Model Checking

**File**: `JAYA_CORE/src/verification/formal.py` - `TLAModelChecker`

**Current**: Returns `not_implemented`, gate passes if TLC missing

**Fix**:
- [ ] Write TLA+ specs for critical protocols (consensus, evolution gate, capability negotiation)
- [ ] Install TLC in CI
- [ ] Gate fails if TLC not available: `BLOCKED_EXTERNAL` not `PASS`
- [ ] Generate `.tla` files from `TLAModel` spec

### 4.3 Security Gate - Real Scanners

**File**: `JAYA_CORE/src/verification/phase2_gates.py` - `_verify_security()`

**Current**: All checks return `True`/empty

**Implementation**:
- [ ] Integrate `bandit` for static analysis
- [ ] Integrate `semgrep` for security patterns
- [ ] Integrate `truffleHog`/`git-secrets` for secret scanning
- [ ] Run in CI, fail on findings

### 4.4 Fix Integration Tests

**File**: `JAYA_CORE/tests/test_phase2_integration.py`

**Deterministic Failures to Fix**:
1. [ ] `test_nlu_low_confidence_fallback()` - uses `nlu_bridge` fixture but references `nlu_bridge` variable
2. [ ] `SimpleExecutor.execute()` expects `plan.steps` but bridge returns `SymbolicPlan` with `plan.plan.steps`
3. [ ] Missing imports: `ExecutionRequest`, `Language`, `ResourceLimits`, `SkillNotFound`, `UnknownStepType`
4. [ ] `RealExecutor` used but not defined
5. [ ] Circular dependency test calls `constraint_solver.check()` but cycle detection is in `LogicEngine`
6. [ ] Neural test expects semantic results from random weights
7. [ ] Gate integration runs pytest recursively

**Hardcoded Path**: Line ~320 `cwd="D:/Kampus/coba-coba/jaya-research"` → use `Path(__file__).parent.parent.parent`

### 4.5 CI Pipeline

**Create**: `.github/workflows/phase2-verification.yml`

```yaml
jobs:
  phase2-gates:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Setup Python
      - name: Install dependencies
      - name: Run Phase 1 tests
      - name: Run Phase 2 integration tests
      - name: Run verification gates
      - name: Benchmark
```

---

## Phase 5: Real Demo / Vertical Slice (Week 9-10)

### 5.1 Implement Real JARVIS Vertical Slice

**File**: `JAYA_CORE/tests/test_jarvis_minimum_e2e.py`

**Current**: ACT = "Tool Execution Simulation", EVALUATE = hardcoded 0.8 score

**Required Real Flow**:
```
Natural Language Input
    → NLUSymbolicBridge (LLM NLU + entity extraction)
    → SymbolicReasoner (constraint check + HTN planning)
    → Capability Negotiation (registry lookup)
    → Approval Gate (for DESTRUCTIVE actions)
    → Sandbox Execution (real tool: file edit, test run, etc.)
    → Result Verification (test pass/fail)
    → Evaluation (real metrics)
    → Episodic Memory Storage (NarrativeContinuity)
    → Process Shutdown
    → Process Restart
    → Memory Restoration Verification
```

**Demo Script**: `JAYA_CORE/scripts/demo_jarvis_vertical_slice.py`

### 5.2 Remove All "Simulation" Labels

**Search/Replace**:
- [ ] "ACT: Tool Execution Simulation" → Real tool execution
- [ ] "PERSIST: Restart simulation" → Real restart test
- [ ] Hardcoded scores → Real evaluation metrics

---

## Cross-Cutting Concerns

### Configuration Management

**Create**: `JAYA_CORE/config/runtime_config.py`

```python
@dataclass(frozen=True)
class RuntimeConfig:
    model_path: Path
    data_dir: Path
    resource_profile: ResourceProfile
    capability_registry_path: Path
    nlu_confidence_threshold: float
    # ... all configurable values
```

- [ ] Validate all config at startup
- [ ] Fail fast with structured errors if missing
- [ ] No hardcoded values in source code

### Error Handling Standards

- [ ] No bare `except:` or `except Exception:` without actionable handling
- [ ] All external calls: timeout, retry (idempotent), circuit breaker
- [ ] Structured error types with error codes
- [ ] No secret leakage in logs/errors

### Testing Standards

- [ ] Unit tests: isolated, fast, deterministic
- [ ] Integration tests: real dependencies, marked `@pytest.mark.integration`
- [ ] External tests: marked `@pytest.mark.external`, skipped if deps unavailable
- [ ] Hardware tests: marked `@pytest.mark.hardware`
- [ ] CI runs: unit + integration (external/hardware optional)

---

## Acceptance Criteria per Phase

### Phase 1 Complete When:
- [ ] Single canonical runtime (`brain_v2`)
- [ ] `NLUSymbolicBridge` wired into `IronEngine.cognitive_reason()`
- [ ] Entity extraction works with real LLM structured output
- [ ] Capabilities from registry, not hardcoded
- [ ] Resource limits from profile, not hardcoded
- [ ] Tests pass: `test_phase2_integration.py::TestPhase2Integration::test_nlu_to_executor_pipeline`

### Phase 2 Complete When:
- [ ] TinyNeuralNet trained checkpoint exists with model card
- [ ] Model < 10M params verified
- [ ] BPE tokenizer artifact loaded at runtime
- [ ] Neural reranker 3D input fixed
- [ ] Neural entity extraction implemented
- [ ] Neural outputs influence symbolic reasoning
- [ ] Accuracy/F1/recall metrics documented

### Phase 3 Complete When:
- [ ] Single `LiveEvolver` (brain_v2) with task-replay fitness
- [ ] Single `MorphicKernel` (brain_v2) with digest-verified rollback
- [ ] Holdout benchmark suite prevents overfitting
- [ ] Candidate staging + canary promotion
- [ ] Rollback tested via process restart

### Phase 4 Complete When:
- [ ] Hypothesis property tests run and pass
- [ ] TLA+ specs exist, TLC runs in CI
- [ ] Security scanners (bandit, semgrep, truffleHog) run in CI
- [ ] All integration tests pass (no deterministic failures)
- [ ] No hardcoded paths
- [ ] GitHub Actions workflow passes

### Phase 5 Complete When:
- [ ] `demo_jarvis_vertical_slice.py` runs end-to-end
- [ ] Real tool execution (file edit → test run → verify)
- [ ] Real approval flow for destructive actions
- [ ] Real memory persistence across restart
- [ ] No "simulation" labels in test/demo code

---

## Risk Register

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Training data unavailable | High | Medium | Create synthetic + curate real; use transfer learning |
| TLC not installable in CI | Medium | High | Use Docker with TLC pre-installed; mark gate `BLOCKED_EXTERNAL` |
| Capability registry incomplete | High | Medium | Implement minimal registry first; expand incrementally |
| Sandbox execution flaky | Medium | Medium | Add retries, timeouts, better isolation |
| Model size > 10M after training | Medium | Low | Monitor during training; prune/quantize if needed |

---

## Definition of Done (Overall)

Phase 2 Level 2 is `IMPLEMENTED_LOCAL` when:
1. ✅ All 5 phases above complete
2. ✅ `python -m pytest JAYA_CORE/tests/test_phase2_integration.py -v` passes
3. ✅ `python JAYA_CORE/scripts/demo_jarvis_vertical_slice.py` runs successfully
4. ✅ `python -m pytest JAYA_CORE/tests/test_jarvis_minimum_e2e.py -v` passes
5. ✅ CI pipeline green
6. ✅ Benchmark results saved to `reports/benchmarks/`
7. ✅ `docs/STATUS.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md` updated
8. ✅ `python scripts/validate_docs.py` passes

---

## Next Immediate Actions (This Week)

1. **Day 1-2**: Resolve canonical runtime - deprecate `self_improvement/`, wire `NLUSymbolicBridge` into `IronEngine`
2. **Day 3-4**: Fix `NLUSymbolicBridge` entity extraction + capability registry integration
3. **Day 5**: Fix `SymbolicReasoner` hardcoded values
4. **Day 6-7**: Fix integration test deterministic failures

---

*This plan follows the audit's prescribed correction order and the repository's governance rules (evidence, sandbox, test, approval, observability, rollback).*