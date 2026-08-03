# JAYA Level 2 & Phase 2 Implementation Plan

**Status: PLANNED** — Belum diimplementasikan. Dokumentasi ini adalah rencana implementasi nyata sesuai aturan AGENTS.md.

---

## 1. Ringkasan Eksekutif

### Target Level 2: Neural-Symbolic Hybrid
- **LLM hanya untuk NLU** (Natural Language Understanding)
- **Reasoning & Planning** → Symbolic Engine (HTN/PDDL) + Tiny Neural Net (<10M params)
- **Creativity/Generation** → Evolutionary Algorithms + MorphicKernel
- **Embedding/Similarity** → Graph-based + TF-IDF (tanpa LLM)

### Target Phase 2: Production Hardening + Capability Expansion
- Semua komponen Level 2 terintegrasi end-to-end
- Zero mock di production path
- Formal verification terintegrasi
- Observability lengkap (logging, metrics, tracing)
- Security hardening lengkap

---

## 2. Arsitektur Level 2 (Neural-Symbolic Hybrid)

```
┌─────────────────────────────────────────────────────────────────┐
│                    JAYA LEVEL 2 ARCHITECTURE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────┐ │
│  │   NLU Module    │    │  Symbolic       │    │  Tiny Neural  │ │
│  │  (LLM Only)     │───►│  Reasoner       │◄──►│  Net (<10M)   │ │
│  │  - Intent       │    │  - HTN Planner  │    │  - Embedding  │ │
│  │  - Entity Ext.  │    │  - Logic Engine │    │  - Classifier │ │
│  │  - Slot Fill    │    │  - Constraint   │    │  - Reranker   │ │
│  └─────────────────┘    └────────┬────────┘    └─────────────┘ │
│                                  │                              │
│                    ┌─────────────┼─────────────┐                │
│                    ▼             ▼             ▼                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              MORPHIC KERNEL (Runtime Patching)           │   │
│  │  - LiveEvolver (1+1 ES)    │  MetaCognitivePlanner       │   │
│  │  - Patch Generator         │  Patch Applier              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                  │                              │
│         ┌────────────────────────┼────────────────────────┐    │
│         ▼                        ▼                        ▼    │
│  ┌─────────────┐         ┌─────────────┐         ┌─────────────┐│
│  │   MEMORY    │         │   TOOLS     │         │  EXECUTOR   ││
│  │  - Episodic │         │  - Sandbox  │         │  - JayaIR   ││
│  │  - Semantic │         │  - Skills   │         │  - HTN Exec ││
│  │  - Procedural│        │  - Adapters │         │  - Verifier ││
│  └─────────────┘         └─────────────┘         └─────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Integration Points (Real, Not Mock)

### 3.1 NLU Module → Symbolic Reasoner
```python
# JAYA_CORE/src/nlu/symbolic_bridge.py (BARU - IMPLEMENTASI NYATA)
class NLUSymbolicBridge:
    """Bridge NLU output ke Symbolic Reasoner tanpa mock."""
    
    def __init__(self, nlu_adapter: CognitiveModelAdapter, 
                 symbolic_reasoner: SymbolicReasoner):
        self.nlu = nlu_adapter
        self.reasoner = symbolic_reasoner
    
    def process(self, user_input: str, context: Dict) -> SymbolicPlan:
        # 1. NLU: Intent + Entity + Slot (pakai LLM kecil/local)
        nlu_result = self.nlu.classify_intent(user_input, context)
        
        # 2. Validasi: Jika confidence < threshold → fallback ke clarifikasi
        if nlu_result.confidence < 0.7:
            return ClarificationNeeded(nlu_result.alternatives)
        
        # 3. Convert ke Symbolic IR (JayaIR)
        ir = self._nlu_to_ir(nlu_result)
        
        # 4. Verifikasi IR sebelum eksekusi
        if not self.reasoner.verify_ir(ir):
            return IRVerificationFailed(ir.errors)
        
        return SymbolicPlan(ir=ir, nlu_result=nlu_result)
```

### 3.2 Symbolic Reasoner → Executor (Real Integration)
```python
# JAYA_CORE/src/reasoning/symbolic_reasoner.py (EXISTING - PERLU DIPERBAIKI)
class SymbolicReasoner:
    """Symbolic reasoning engine - TIDAK BOLEH MOCK."""
    
    def __init__(self, htn_planner: HTNPlanner, 
                 logic_engine: LogicEngine,
                 constraint_solver: ConstraintSolver):
        self.planner = htn_planner
        self.logic = logic_engine
        self.constraints = constraint_solver
    
    def reason(self, ir: JayaIR, context: Context) -> ExecutionPlan:
        # 1. Constraint checking (real, not mock)
        violations = self.constraints.check(ir, context)
        if violations:
            raise ConstraintViolation(violations)
        
        # 2. HTN Planning (real implementation)
        plan = self.planner.create_plan(ir.goal, context)
        
        # 3. Logic verification (real, not mock)
        if not self.logic.verify_plan(plan):
            raise LogicVerificationFailed(plan.errors)
        
        return ExecutionPlan(plan=plan, ir=ir)
```

### 3.3 Executor → Tools/Sandbox (Real, No Mock)
```python
# JAYA_CORE/src/execution/real_executor.py (EXISTING - PERLU DIPERBAIKI)
class RealExecutor:
    """Executor yang benar-benar menjalankan tools, bukan mock."""
    
    def __init__(self, sandbox: SandboxManager, 
                 skill_registry: SkillRegistry,
                 jaya_ir_executor: JayaIRExecutor):
        self.sandbox = sandbox
        self.skills = skill_registry
        self.ir_exec = jaya_ir_executor
    
    async def execute(self, plan: ExecutionPlan) -> ExecutionResult:
        results = []
        for step in plan.steps:
            # Real tool execution, bukan mock
            if step.type == ToolType.CODE:
                result = await self.sandbox.execute_python(step.code)
            elif step.type == ToolType.SKILL:
                skill = self.skills.get(step.skill_id)
                if not skill:
                    raise SkillNotFound(step.skill_id)
                result = await skill.execute(step.params)
            elif step.type == ToolType.JAYA_IR:
                result = await self.ir_exec.execute(step.ir)
            else:
                raise UnknownStepType(step.type)
            
            # Real validation, bukan mock
            if not self._validate_result(step, result):
                raise StepValidationFailed(step, result)
            
            results.append(result)
        
        return ExecutionResult(steps=results, success=all(r.success for r in results))
```

---

## 4. Level 2 Components Implementation Plan

### 4.1 Tiny Neural Net (<10M params) - BARU
```python
# JAYA_CORE/src/neural/tiny_net.py (BARU - IMPLEMENTASI NYATA)
class TinyNeuralNet(nn.Module):
    """Neural net kecil (<10M params) untuk tugas spesifik."""
    
    def __init__(self, config: TinyNetConfig):
        super().__init__()
        # Embedding layer (shared)
        self.embedding = nn.Embedding(config.vocab_size, config.d_model)
        
        # Transformer encoder (2-4 layers, 4-8 heads)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=config.d_model,
            nhead=config.n_heads,
            dim_feedforward=config.d_ff,
            dropout=0.1,
            batch_first=True
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, config.n_layers)
        
        # Task-specific heads
        self.embedding_head = nn.Linear(config.d_model, config.embed_dim)
        self.classifier_head = nn.Linear(config.d_model, config.n_classes)
        self.reranker_head = nn.Linear(config.d_model * 2, 1)
    
    def forward(self, input_ids, attention_mask=None, task="embed"):
        x = self.embedding(input_ids)
        x = self.encoder(x, src_key_padding_mask=attention_mask)
        
        if task == "embed":
            return self.embedding_head(x[:, 0])  # CLS token
        elif task == "classify":
            return self.classifier_head(x[:, 0])
        elif task == "rerank":
            # x shape: [batch, 2, d_model] untuk pair
            return self.reranker_head(x.view(x.size(0), -1))
```

### 4.2 Neural-Symbolic Interface - BARU
```python
# JAYA_CORE/src/neural/symbolic_interface.py (BARU - IMPLEMENTASI NYATA)
class NeuralSymbolicInterface:
    """Interface antara Neural Net dan Symbolic Reasoner."""
    
    def __init__(self, neural_net: TinyNeuralNet, 
                 symbolic_reasoner: SymbolicReasoner,
                 tokenizer: Tokenizer):
        self.net = neural_net
        self.reasoner = symbolic_reasoner
        self.tokenizer = tokenizer
    
    def neural_embed(self, texts: List[str]) -> np.ndarray:
        """Generate embeddings untuk semantic search (real, not mock)."""
        inputs = self.tokenizer(texts, padding=True, truncation=True, 
                               return_tensors="pt")
        with torch.no_grad():
            embeddings = self.net(inputs.input_ids, 
                                 inputs.attention_mask, 
                                 task="embed")
        return embeddings.cpu().numpy()
    
    def neural_classify(self, text: str, labels: List[str]) -> Dict[str, float]:
        """Classification untuk intent/entity (real, not mock)."""
        # Format: "Classify: text | labels: label1, label2, ..."
        prompt = f"Classify: {text} | labels: {', '.join(labels)}"
        inputs = self.tokenizer(prompt, return_tensors="pt")
        with torch.no_grad():
            logits = self.net(inputs.input_ids, task="classify")
        probs = torch.softmax(logits, dim=-1)
        return {label: float(prob) for label, prob in zip(labels, probs[0])}
    
    def neural_rerank(self, query: str, candidates: List[str]) -> List[float]:
        """Rerank candidates untuk RAG (real, not mock)."""
        scores = []
        for cand in candidates:
            prompt = f"Query: {query} | Candidate: {cand}"
            inputs = self.tokenizer(prompt, return_tensors="pt")
            with torch.no_grad():
                score = self.net(inputs.input_ids, task="rerank")
            scores.append(float(score))
        return scores
```

### 4.3 LiveEvolver Integration (Real) - EXISTING PERLU DIPERBAIKI
```python
# JAYA_CORE/src/evolution/live_evolver.py (EXISTING - PERLU DIPERBAIKI)
class LiveEvolver:
    """Evolusi parameter real-time dengan (1+1)-ES."""
    
    def __init__(self, parameter_space: ParameterSpace,
                 fitness_fn: Callable[[Dict], float],
                 neural_net: Optional[TinyNeuralNet] = None):
        self.space = parameter_space
        self.fitness_fn = fitness_fn
        self.neural_net = neural_net  # Bisa evolve neural net weights
        self.current_best = None
        self.generation = 0
    
    def evolve_step(self) -> EvolutionResult:
        """Satu langkah evolusi - REAL, bukan mock."""
        # 1. Mutasi parameter
        candidate = self._mutate(self.current_best)
        
        # 2. Evaluasi fitness REAL (bukan mock)
        fitness = self.fitness_fn(candidate.params)
        
        # 3. Seleksi (1+1)-ES
        if fitness > self.current_best.fitness:
            self.current_best = candidate
            self._apply_to_system(candidate)
        
        return EvolutionResult(
            generation=self.generation,
            best_fitness=self.current_best.fitness,
            improvement=fitness - self.current_best.fitness,
            params_changed=list(candidate.params.keys())
        )
    
    def _apply_to_system(self, candidate: EvolutionCandidate):
        """Apply parameter changes ke sistem REAL."""
        if self.neural_net and "neural_" in candidate.params:
            # Update neural net weights
            self._update_neural_weights(candidate.params)
        # Update symbolic reasoner params, dll.
```

---

## 5. Phase 2 Production Hardening Checklist

### 5.1 Zero Mock in Production (WAJIB)
| Komponen | Status | Aksi Diperlukan |
|----------|--------|-----------------|
| NLU Module | ❌ Mock LLM | Ganti dengan real LLM adapter |
| Symbolic Reasoner | ⚠️ Partial | Lengkapi HTN Planner, Logic Engine |
| Executor | ⚠️ Partial | Lengkapi sandbox integration |
| Memory Systems | ✅ Ready | Sudah real (SQLite, Graph) |
| LiveEvolver | ⚠️ Partial | Lengkapi fitness function real |
| MorphicKernel | ⚠️ Partial | Lengkapi patch application real |

### 5.2 Formal Verification Integration (WAJIB)
```python
# JAYA_CORE/src/verification/phase2_gates.py (BARU)
class Phase2VerificationGates:
    """Gerbang verifikasi Phase 2 - WAJIB LULUS."""
    
    def __init__(self):
        self.gates = [
            ("contract_verification", self._verify_contracts),
            ("property_testing", self._verify_properties),
            ("tla_model_checking", self._verify_tla_models),
            ("integration_testing", self._verify_integration),
            ("security_audit", self._verify_security),
            ("performance_benchmark", self._verify_performance),
        ]
    
    def run_all_gates(self) -> VerificationReport:
        results = {}
        for name, gate_fn in self.gates:
            try:
                result = gate_fn()
                results[name] = {"passed": result.passed, "details": result.details}
            except Exception as e:
                results[name] = {"passed": False, "error": str(e)}
        
        all_passed = all(r["passed"] for r in results.values())
        return VerificationReport(
            phase="Phase 2",
            all_passed=all_passed,
            gates=results,
            timestamp=time.time()
        )
```

### 5.3 Observability Lengkap (WAJIB)
```python
# JAYA_CORE/src/observability/phase2_observability.py (BARU)
def setup_phase2_observability():
    """Setup observability lengkap untuk Phase 2."""
    return init_observability(
        service_name="jaya-core-phase2",
        log_level=logging.INFO,
        json_logs=True,
        log_file="/var/log/jaya/phase2.json",
        metrics_port=9091,
        jaeger_endpoint="http://jaeger:14268/api/traces",
        zipkin_endpoint="http://zipkin:9411/api/v2/spans",
        console_tracing=False,
    )
```

---

## 6. Test Strategy (Real Tests, No Mocks)

### 6.1 Integration Tests (WAJIB)
```python
# JAYA_CORE/tests/test_phase2_integration.py (BARU)
class TestPhase2Integration:
    """Integration tests END-TO-END - NO MOCKS."""
    
    def test_nlu_to_executor_pipeline(self):
        """Test pipeline NLU → Symbolic → Executor end-to-end."""
        # Setup REAL components
        nlu = create_cognitive_adapter_from_env()
        reasoner = SymbolicReasoner(HTNPlanner(), LogicEngine(), ConstraintSolver())
        executor = RealExecutor(SandboxManager(), SkillRegistry(), JayaIRExecutor())
        bridge = NLUSymbolicBridge(nlu, reasoner)
        
        # Real input
        user_input = "Buatkan rencana belajar Python untuk pemula"
        context = {"user_id": "test_user", "session_id": "test_session"}
        
        # Execute pipeline
        plan = bridge.process(user_input, context)
        assert isinstance(plan, SymbolicPlan)
        
        result = asyncio.run(executor.execute(plan))
        assert result.success
        assert len(result.steps) > 0
    
    def test_neural_symbolic_interface(self):
        """Test neural-symbolic interface real."""
        net = TinyNeuralNet(TinyNetConfig(vocab_size=30000, d_model=256))
        reasoner = SymbolicReasoner(HTNPlanner(), LogicEngine(), ConstraintSolver())
        interface = NeuralSymbolicInterface(net, reasoner, Tokenizer())
        
        # Real embedding
        embeddings = interface.neural_embed(["test query", "another query"])
        assert embeddings.shape == (2, 128)
        
        # Real classification
        result = interface.neural_classify("buat rencana", ["CREATE_PLAN", "QUERY"])
        assert "CREATE_PLAN" in result
        assert result["CREATE_PLAN"] > 0.5
```

### 6.2 Failure Path Tests (WAJIB)
```python
# JAYA_CORE/tests/test_phase2_failure_paths.py (BARU)
class TestPhase2FailurePaths:
    """Test failure paths - NO MOCKS."""
    
    def test_nlu_low_confidence_fallback(self):
        """Test fallback ketika NLU confidence rendah."""
        # Setup dengan adapter yang return low confidence
        nlu = LowConfidenceMockAdapter()  # HANYA UNTUK TEST
        bridge = NLUSymbolicBridge(nlu, SymbolicReasoner(...))
        
        result = bridge.process("asdfghjkl", {})
        assert isinstance(result, ClarificationNeeded)
    
    def test_constraint_violation_handling(self):
        """Test handling constraint violation."""
        reasoner = SymbolicReasoner(...)
        ir = create_invalid_ir()  # IR yang melanggar constraint
        
        with pytest.raises(ConstraintViolation):
            reasoner.reason(ir, Context())
    
    def test_sandbox_execution_failure(self):
        """Test sandbox execution failure handling."""
        sandbox = SandboxManager()
        executor = RealExecutor(sandbox, SkillRegistry(), JayaIRExecutor())
        
        # Code yang error
        plan = ExecutionPlan(steps=[Step(type=ToolType.CODE, code="1/0")])
        result = asyncio.run(executor.execute(plan))
        assert not result.success
        assert "ZeroDivisionError" in result.error
```

---

## 7. Configuration Management (No Hardcode)

### 7.1 Environment Variables (WAJIB)
```bash
# JAYA_CORE/.env.phase2.example
# Neural Net Config
JAYA_TINY_NET_VOCAB_SIZE=30000
JAYA_TINY_NET_D_MODEL=256
JAYA_TINY_NET_N_LAYERS=4
JAYA_TINY_NET_N_HEADS=8
JAYA_TINY_NET_PATH=models/tiny_net.pt

# Evolution Config
JAYA_EVOLUTION_MUTATION_RATE=0.1
JAYA_EVOLUTION_MUTATION_STRENGTH=0.05
JAYA_EVOLUTION_POPULATION_SIZE=10
JAYA_EVOLUTION_FITNESS_THRESHOLD=0.8

# Morphic Kernel
JAYA_MORPHIC_PATCH_AUTO_APPLY=false
JAYA_MORPHIC_MAX_PATCHES_PER_CYCLE=5

# Verification
JAYA_VERIFICATION_TLA_ENABLED=true
JAYA_VERIFICATION_PROPERTY_TESTING=true
JAYA_VERIFICATION_CONTRACT_CHECKING=true

# Observability
JAYA_LOG_LEVEL=INFO
JAYA_METRICS_PORT=9091
JAYA_JAEGER_ENDPOINT=http://jaeger:14268/api/traces
```

### 7.2 Config Validation (WAJIB)
```python
# JAYA_CORE/src/config/phase2_config.py (BARU)
@dataclass(frozen=True)
class Phase2Config:
    tiny_net: TinyNetConfig
    evolution: EvolutionConfig
    morphic: MorphicConfig
    verification: VerificationConfig
    
    @classmethod
    def from_env(cls) -> "Phase2Config":
        # Validasi semua required env vars
        required = [
            "JAYA_TINY_NET_PATH",
            "JAYA_EVOLUTION_FITNESS_THRESHOLD",
        ]
        for var in required:
            if not os.getenv(var):
                raise ConfigurationError(f"Missing required env var: {var}")
        
        return cls(
            tiny_net=TinyNetConfig(
                vocab_size=int(os.getenv("JAYA_TINY_NET_VOCAB_SIZE", "30000")),
                d_model=int(os.getenv("JAYA_TINY_NET_D_MODEL", "256")),
                n_layers=int(os.getenv("JAYA_TINY_NET_N_LAYERS", "4")),
                n_heads=int(os.getenv("JAYA_TINY_NET_N_HEADS", "8")),
                model_path=Path(os.getenv("JAYA_TINY_NET_PATH")),
            ),
            evolution=EvolutionConfig(
                mutation_rate=float(os.getenv("JAYA_EVOLUTION_MUTATION_RATE", "0.1")),
                mutation_strength=float(os.getenv("JAYA_EVOLUTION_MUTATION_STRENGTH", "0.05")),
                population_size=int(os.getenv("JAYA_EVOLUTION_POPULATION_SIZE", "10")),
                fitness_threshold=float(os.getenv("JAYA_EVOLUTION_FITNESS_THRESHOLD", "0.8")),
            ),
            # ... dst
        )
```

---

## 8. Demo Nyata (Bukan Mock)

### 8.1 Demo Script (WAJIB)
```python
# JAYA_CORE/scripts/demo_phase2.py (BARU)
#!/usr/bin/env python3
"""Demo Phase 2 Level 2 - REAL EXECUTION."""

async def main():
    print("=" * 60)
    print("JAYA Phase 2 Level 2 Demo")
    print("=" * 60)
    
    # 1. Initialize REAL components
    config = Phase2Config.from_env()
    nlu = create_cognitive_adapter_from_env()
    neural_net = TinyNeuralNet(config.tiny_net)
    neural_net.load_state_dict(torch.load(config.tiny_net.model_path))
    
    reasoner = SymbolicReasoner(HTNPlanner(), LogicEngine(), ConstraintSolver())
    executor = RealExecutor(SandboxManager(), SkillRegistry(), JayaIRExecutor())
    bridge = NLUSymbolicBridge(nlu, reasoner)
    interface = NeuralSymbolicInterface(neural_net, reasoner, Tokenizer())
    
    # 2. Demo queries
    queries = [
        "Buatkan rencana belajar Python untuk pemula 30 hari",
        "Cari tahu tentang machine learning basics",
        "Eksekusi kode: print('Hello JAYA')",
    ]
    
    for query in queries:
        print(f"\n📝 Query: {query}")
        
        # Pipeline real
        plan = bridge.process(query, {"user_id": "demo_user"})
        print(f"   Plan: {plan.ir.goal}")
        
        result = await executor.execute(plan)
        print(f"   Result: {'✅ Success' if result.success else '❌ Failed'}")
        
        if result.steps:
            for step in result.steps:
                print(f"   - {step.type}: {step.output[:100]}...")
    
    # 3. Demo Neural-Symbolic
    print("\n🧠 Neural-Symbolic Demo:")
    embeddings = interface.neural_embed(["machine learning", "deep learning"])
    print(f"   Embeddings shape: {embeddings.shape}")
    
    scores = interface.neural_rerank("machine learning", 
                                     ["ML basics", "DL advanced", "Python tutorial"])
    print(f"   Rerank scores: {scores}")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 9. Feature Status Tracking (Sesuai AGENTS.md)

| Fitur | Status | Bukti |
|-------|--------|-------|
| NLU Module (LLM only) | PLANNED | - |
| Symbolic Reasoner (HTN) | PLANNED | - |
| Tiny Neural Net | PLANNED | - |
| Neural-Symbolic Interface | PLANNED | - |
| LiveEvolver Real Fitness | PLANNED | - |
| MorphicKernel Real Patching | PLANNED | - |
| NLU→Symbolic Bridge | PLANNED | - |
| Symbolic→Executor Pipeline | PLANNED | - |
| Phase2 Verification Gates | PLANNED | - |
| Integration Tests | PLANNED | - |
| Failure Path Tests | PLANNED | - |
| Demo Script | PLANNED | - |

**Catatan**: Sesuai AGENTS.md, status tidak boleh dinaikkan ke `IMPLEMENTED` atau `VERIFIED` sebelum ada bukti eksekusi nyata (test lulus, demo jalan, artifact terealisasi).

---

## 10. Definition of Done Phase 2 Level 2

Sesuai AGENTS.md Section 26, Phase 2 Level 2 dianggap **DONE** hanya jika:

- [ ] Semua komponen Level 2 terimplementasikan (bukan mock)
- [ ] Pipeline NLU → Symbolic → Executor berjalan end-to-end
- [ ] Neural-Symbolic interface berfungsi (embedding, classify, rerank real)
- [ ] LiveEvolver menjalankan evolusi real dengan fitness function nyata
- [ ] MorphicKernel menerapkan patch real ke sistem
- [ ] Semua Phase 2 Verification Gates LULUS (contract, property, TLA+, integration, security, performance)
- [ ] Integration tests end-to-end LULUS (no mocks)
- [ ] Failure path tests LULUS (constraint violation, sandbox error, low confidence)
- [ ] Demo script berjalan dan menghasilkan output real
- [ ] Zero hardcode, zero mock di production path
- [ ] Konfigurasi via env vars, divalidasi startup
- [ ] Observability lengkap (logging, metrics, tracing)
- [ ] Security hardening (rate limit, audit log, capability gating)
- [ ] Benchmark real dijalankan dan tercatat

---

## 11. Next Steps (Immediate)

1. **Minggu 1-2**: Implement `NLUSymbolicBridge` + `SymbolicReasoner` completion
2. **Minggu 3-4**: Implement `TinyNeuralNet` + `NeuralSymbolicInterface`
3. **Minggu 5-6**: Complete `LiveEvolver` real fitness + `MorphicKernel` real patching
3. **Minggu 7-8**: Phase 2 Verification Gates + Integration Tests
4. **Minggu 9-10**: Demo script + Documentation update

---

**Catatan**: Dokumentasi ini adalah **rencana**, bukan implementasi. Sesuai AGENTS.md, status fitur tetap `PLANNED` sampai ada bukti eksekusi nyata (test lulus, demo jalan, artifact terealisasi).