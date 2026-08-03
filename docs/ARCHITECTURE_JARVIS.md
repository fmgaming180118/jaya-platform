# JAYA JARVIS Architecture Document

## Overview

JAYA (Just Another Your Assistant) is a production-ready, privacy-first, locally-running AI assistant architecture inspired by JARVIS from Iron Man. It implements a 40-pillar cognitive architecture with real LLM integration, multi-modal capabilities, agent orchestration, and formal verification.

## Architecture Pillars (40 Pillars)

### Core Cognitive Pillars (1-10)
1. **Sovereign Identity** - Cryptographic identity with encrypted soul files
2. **Intent Engine** - Natural language to structured intent classification
3. **Planning Engine** - Hierarchical task planning with dependencies
4. **Execution Engine** - Tool use, code execution, API integration
5. **Memory System** - Working, episodic, semantic, procedural memory
6. **Narrative Continuity** - Autobiographical memory across sessions
7. **Twin Protocol** - P2P agent synchronization
8. **Collective Pulse** - Multi-agent trust/cohesion signals
9. **Agentic RAG** - Hybrid search (BM25 + vector) with reranking
10. **Dynamic Sparsity MoE** - Sparse expert routing under resource constraints

### Advanced Cognitive Pillars (11-20)
11. **Activation Sparsity** - Adaptive neuron budget per turn
12. **Meta-Cognitive Planner** - Reflection every 600s on weak tasks
13. **Self-Bootstrap** - Idle self-study curriculum injection
14. **Live Evolver** - (1+1)-ES micro-evolution on weights
15. **Cognitive Model Adapter** - Real LLM integration (local + cloud)
16. **Multi-Modal Fusion** - Vision, audio, text unified processing
17. **Code Execution Sandbox** - Secure Python/JS execution
18. **Agent Orchestration** - Multi-agent task delegation
19. **A2A Protocol** - Agent-to-agent communication
20. **Workflow Orchestration** - Multi-step workflow execution

### Infrastructure Pillars (21-30)
21. **Structured Observability** - JSON logging, Prometheus metrics, OpenTelemetry tracing
22. **Security Hardening** - Rate limiting, audit logging, capability gating
23. **Model Distribution** - Cosign/sigstore signed model verification
24. **Performance Optimization** - llama.cpp profiling, KV cache, speculative decoding
25. **Advanced Memory** - Semantic, procedural, CRDT sync, hierarchical compression
26. **Formal Verification** - Property-based testing, TLA+ model checking
27. **CLI/REPL Interface** - Interactive JAYA shell
28. **Configuration Management** - Environment-based config with validation
29. **Health Monitoring** - Component health, resource profiling
30. **Cross-Device Sync** - CRDT-based conflict-free replication

### Research & Innovation Pillars (31-40)
31. **Narrative Continuity** - Bounded autobiographical trace
32. **Twin Protocol** - Deterministic P2P handshake
33. **Collective Pulse** - Trust/cohesion aggregation
34. **Agentic RAG** - Procedural retrieval + feedback loop
35. **Dynamic Sparsity MoE** - Resource-aware expert routing
36. **Activation Sparsity** - Complexity-adaptive neuron budget
37. **Meta-Cognitive Planner** - Periodic reflection on weak tasks
38. **Self-Bootstrap** - Idle curriculum injection
39. **Live Evolver** - Micro-evolution on live weights
40. **Morphic Kernel** - Runtime patch generation from feedback

## System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        JAYA CORE                                 │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ IronEngine   │  │ Cognitive    │  │ Memory       │          │
│  │ (Runtime)    │◄─┤ Adapter      │◄─┤ Systems      │          │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘          │
│         │                 │                 │                    │
│         ▼                 ▼                 ▼                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Advanced Cognitive Layer                    │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐   │   │
│  │  │Function │ │  ReAct  │ │  CoT    │ │  Planner    │   │   │
│  │  │ Calling │ │ Engine  │ │ Engine  │ │             │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│         │                 │                 │                    │
│         ▼                 ▼                 ▼                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Multi-Modal & Agent Layer                   │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐   │   │
│  │  │ Vision  │ │ Audio   │ │ Agent   │ │  Workflow   │   │   │
│  │  │ Processor│ │Processor│ │Orchestr.│ │ Orchestr.   │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│         │                 │                 │                    │
│         ▼                 ▼                 ▼                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              Infrastructure Layer                        │   │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐   │   │
│  │  │Observab.│ │Security │ │ Sandbox │ │  CRDT Sync  │   │   │
│  │  │ility    │ │Hardening│ │         │ │             │   │   │
│  │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. IronEngine (Runtime Core)
- **Location**: `JAYA_CORE/src/brain_v2/engine/runtime.py`
- **Responsibilities**: Model loading, twin lifecycle, Magnum cycle, narrative continuity, agentic RAG
- **Key Features**: 
  - Lazy loading of heavy components
  - Graceful degradation (stub mode when model missing)
  - Narrative continuity integration (Pillar 31)
  - Twin protocol support (Pillar 30)

### 2. Cognitive Model Adapter
- **Location**: `JAYA_CORE/src/ai_connectors/cognitive_model_adapter.py`
- **Integrates**: LocalLLMAdapter, CloudLLMAdapter, PublicAPIClient, HybridModelRouter
- **Routing Logic**: Privacy-aware (sensitive → local), factual → public API, complex → cloud
- **Providers**: OpenAI, Anthropic, Ollama, Custom OpenAI-compatible

### 3. Local LLM Adapter
- **Location**: `JAYA_CORE/src/ai_connectors/local_llm_adapter.py`
- **Supports**: Llama-3, Nemotron, Phi-3, Gemma, Qwen, Mistral, DeepSeek-Coder
- **Features**: Model-specific chat templates, auto-config detection, KV cache, speculative decoding

### 4. Cloud LLM Adapter
- **Location**: `JAYA_CORE/src/ai_connectors/cloud_llm_adapter.py`
- **Providers**: OpenAI, Anthropic, Ollama, Custom
- **Features**: Async execution, streaming, usage tracking, privacy filtering

### 5. Memory Systems
| System | Location | Purpose |
|--------|----------|---------|
| Narrative Continuity | `brain_v2/engine/narrative_continuity.py` | Autobiographical trace (Pillar 31) |
| Episodic Memory | `memory/episodic.py` | SQLite event store with WAL |
| Working Memory | `memory/working.py` | TTL-based short-term memory |
| Semantic Memory | `memory/advanced.py` | Knowledge graph with entities/relations |
| Procedural Memory | `memory/advanced.py` | Skill acquisition from demonstration |
| Hierarchical Memory | `memory/advanced.py` | Multi-level compression |
| CRDT Sync | `memory/advanced.py` | Cross-device conflict-free replication |

### 6. Advanced Cognitive
- **Function Calling**: `cognitive/advanced.py` - Schema-based tool calling
- **ReAct Engine**: Reasoning + Acting loop
- **Chain-of-Thought**: Structured reasoning
- **Multi-Step Planner**: Dependency-aware task planning

### 7. Multi-Modal Foundation
- **Vision**: LLaVA (Ollama/local), GPT-4V (OpenAI)
- **Audio**: Whisper (local), OpenAI Whisper/TTS
- **Fusion**: Unified multi-modal context

### 8. Code Execution Sandbox
- **Backends**: Subprocess (basic), Docker (strong isolation)
- **Languages**: Python, JavaScript, TypeScript, Bash
- **Security**: Pattern blocking, capability gating, resource limits

### 8. Agent Orchestration
- **Registry**: Agent discovery and capability indexing
- **Task Orchestrator**: Delegation, scheduling, load balancing
- **A2A Protocol**: Request/response, broadcast, correlation IDs
- **Workflow Orchestrator**: DAG-based multi-step execution

### 9. Observability
- **Structured Logging**: JSON format, context enrichment, privacy redaction
- **Prometheus Metrics**: Request latency, model inference, memory, errors
- **Distributed Tracing**: OpenTelemetry, Jaeger/Zipkin/OTLP export

### 10. Security Hardening
- **Rate Limiting**: Token bucket + sliding window
- **Audit Logging**: Structured security events
- **Input Validation**: Pattern blocking, path traversal prevention
- **Capability Gating**: Fine-grained permission system

### 11. Model Distribution
- **Cosign/Sigstore**: Signed model verification
- **Registry**: Predefined models (Llama-3, Nemotron, etc.)
- **Downloader**: Resume support, SHA256 verification, attestation

### 12. Performance Optimization
- **llama.cpp Config**: Auto-detection per model architecture
- **KV Cache Manager**: LRU eviction, session isolation
- **Speculative Decoding**: Draft model verification
- **Benchmarking**: Latency, throughput, memory profiling

### 13. Advanced Memory
- **Semantic**: Entity/relation knowledge graph
- **Procedural**: Skill learning from demonstration
- **CRDT Sync**: LWW Register/Map, OR-Set for cross-device
- **Hierarchical**: Multi-level compression (raw → summary → abstract)

### 14. Self-Improvement Loop
- **LiveEvolver**: (1+1)-ES micro-evolution on parameters
- **MetaCognitivePlanner**: Periodic reflection, improvement plans
- **MorphicKernel**: Runtime patch generation from feedback
- **Orchestrator**: Coordinates evolution, reflection, patching

### 15. Formal Verification
- **Property-Based Testing**: Invariant, contract, safety, liveness
- **TLA+ Model Checking**: TLC integration for critical protocols
- **Contract Verification**: Pre/post conditions, invariants
- **Runtime Monitors**: Continuous system health checks

### 16. CLI/REPL
- **Interactive Shell**: Chat, cognitive, intent, memory, RAG, sandbox commands
- **Multimodal**: Vision, audio processing from CLI
- **Agent Management**: Create, delegate, list agents

## Data Flow

```
User Input
    │
    ▼
┌─────────────────┐
│  Perception     │  ──► Intent Classification
│  Pipeline       │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Context        │  ──► Build Context Snapshot
│  Manager        │      (Working + Episodic + Semantic)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Cognitive      │  ──► Route to Best Backend
│  Adapter        │      (Local/Cloud/Public API)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Execution      │  ──► Tools, Code, APIs, Agents
│  Engine         │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Memory         │  ──► Store in Narrative + Episodic
│  Systems        │      Update Working Memory
└────────┬────────┘
         │
         ▼
    Response
```

## Configuration

### Environment Variables (`.env`)
```bash
# Core
JAYA_SOUL_PASSWORD=              # Required: AES-256-GCM password
JAYA_MODEL_PATH=                 # Path to .jay model file
JAYA_NARRATIVE_PATH=             # Narrative persistence file
JAYA_EPISODIC_PATH=              # Episodic SQLite database

# Cloud LLM
JAYA_ENABLE_CLOUD=true
JAYA_PRIVACY_LEVEL=HYBRID_ALLOWED
JAYA_OPENAI_API_KEY=
JAYA_ANTHROPIC_API_KEY=
JAYA_OLLAMA_BASE_URL=http://localhost:11434

# Observability
JAYA_LOG_LEVEL=INFO
JAYA_METRICS_PORT=9090
JAYA_JAEGER_ENDPOINT=http://localhost:14268/api/traces

# Security
JAYA_RATE_LIMIT_DEFAULT=100/min
JAYA_AUDIT_LOG_PATH=/var/log/jaya/audit.log
```

## Deployment

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Download model (example)
wget -O models/llama-3-8b-instruct.Q4_K_M.gguf \
  https://huggingface.co/bartowski/Meta-Llama-3-8B-Instruct-GGUF/resolve/main/Meta-Llama-3-8B-Instruct-Q4_K_M.gguf

# Register model
python -c "
from JAYA_CORE.src.models.registry import EdgeModelRegistry
reg = EdgeModelRegistry(max_allowed_size_mb=50000)
reg.register_from_predefined('llama-3-8b-instruct', 'v1.0', 'models/llama-3-8b-instruct.Q4_K_M.gguf')
"

# Run REPL
python -m JAYA_CORE.src.cli.repl
```

### Production Deployment
```bash
# Set production environment
export JAYA_ENVIRONMENT=production
export JAYA_EVOLUTION_SIGNING_KEY=<32-byte-key>
export JAYA_EVOLUTION_EVIDENCE_SIGNING_KEY=<32-byte-key>

# Start with observability
python -m JAYA_CORE.src.cli.repl --no-repl --command "status"
```

## Testing

```bash
# Run core tests
python -m pytest JAYA_CORE/tests/test_phase1_narrative_continuity_gate.py -v
python -m pytest JAYA_CORE/tests/test_cognitive_kernel.py::TestMemory -v
python -m pytest JAYA_CORE/tests/test_fase3_episodic_memory.py -v
python -m pytest JAYA_CORE/tests/test_multi_turn_memory_restart.py -v

# Run agent tests
python -m pytest JAYA_AGENT/tests/test_phase4_memory.py -v

# Run all
python -m pytest JAYA_CORE/tests/ JAYA_AGENT/tests/ -v
```

## Next Steps (Roadmap)

### Immediate (P0)
- [ ] **Model Server**: Dedicated inference server with batching
- [ ] **Web UI**: React-based dashboard for monitoring and interaction
- [ ] **Android App**: JAYA_ANDROID integration with offline sync
- [ ] **Plugin System**: Dynamic skill loading/unloading

### Short-term (P1)
- [ ] **Distributed Tracing**: Full OpenTelemetry integration
- [ ] **Advanced RAG**: Graph-based retrieval, query decomposition
- [ ] **Multi-Agent Benchmarks**: Standardized evaluation suite
- [ ] **Formal Specs**: Complete TLA+ specs for critical protocols

### Medium-term (P2)
- [ ] **Neuromorphic Hardware**: SpiNNaker/Loihi integration
- [ ] **Federated Learning**: Cross-device model improvement
- [ ] **Quantum-Ready**: Post-quantum cryptography for soul files
- [ ] **AR/VR Interface**: Spatial computing integration

### Research (P3)
- [ ] **Consciousness Metrics**: IIT/PHI implementation
- [ ] **Causal Reasoning**: Pearl's do-calculus integration
- [ ] **Meta-Learning**: MAML/Reptile for fast adaptation
- [ ] **AGI Safety**: Corrigibility, interpretability, alignment

## File Structure

```
JAYA_CORE/
├── src/
│   ├── ai_connectors/          # LLM adapters (local, cloud, public API)
│   ├── agents/                 # Agent orchestration, A2A, workflows
│   ├── brain_v2/               # Core runtime (IronEngine, narrative)
│   ├── cli/                    # REPL and CLI interface
│   ├── cognitive/              # Advanced cognitive (ReAct, CoT, planning)
│   ├── memory/                 # Memory systems (episodic, semantic, procedural)
│   ├── multimodal/             # Vision, audio, fusion
│   ├── observability/          # Logging, metrics, tracing
│   ├── performance/            # Optimization, profiling, benchmarking
│   ├── rag/                    # Enhanced RAG (hybrid search, reranking)
│   ├── sandbox/                # Code execution (subprocess, Docker)
│   ├── security/               # Rate limiting, audit, capabilities
│   ├── self_improvement/       # Evolution, reflection, morphic kernel
│   ├── verification/           # Formal verification, contracts
│   └── ...                     # Other core modules
├── tests/                      # Comprehensive test suite
├── docs/                       # Documentation
└── scripts/                    # Utility scripts
```

## Contributing

See `CONTRIBUTING.md` for guidelines on:
- Code style and architecture compliance
- Testing requirements
- Security review process
- Documentation standards

## License

See `LICENSE` file.

---

*JAYA - Your Local AI Assistant | Inspired by JARVIS | Built for Privacy, Performance, and Extensibility*