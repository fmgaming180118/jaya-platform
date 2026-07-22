# JAYA_CORE Ultra-Intelligence Upgrade Checklist (< 200 MB Constraint)

> **CRITICAL HARD CONSTRAINT**: Model size MUST strictly remain **< 200 MB** (Disk & RAM footprint). 
> **Goal**: Transform `JAYA_CORE` into an ultra-intelligent, sovereign, semi-AGI central brain using extreme quantization, Small Language Models (SLMs), and Micro-MoE architectures capable of competing with large models while running 100% offline under 200 MB footprint.

---

## ⛔ Strictly Enforced Size & Memory Envelope

| Component | Strict Allocation Ceiling | Technology Used |
| :--- | :--- | :--- |
| **Physical Model Weights (`.jay` / GGUF)** | **< 150 MB** | 2-bit Packed Weights / SmolLM-135M / Qwen-0.5B (2-bit `.jay`) |
| **Vector RAG Embeddings & DB** | **< 30 MB** | MiniLM-L6-v2 (23MB) / BGE-Micro Vector Vault |
| **KV-Cache & Context Window Memory** | **< 20 MB** | H2O KV-Cache Eviction & Token Sliding Window |
| **TOTAL SYSTEM FOOTPRINT** | **< 200 MB** | 100% Sovereign Edge Execution |

---

## 🏛️ Master Architecture & Intelligence Phasing

```
                                  ┌─────────────────────────────────────────┐
                                  │   JAYA_CORE ULTRA-INTELLIGENCE (<200MB) │
                                  └────────────────────┬────────────────────┘
                                                       │
         ┌──────────────────────┬──────────────────────┼──────────────────────┬──────────────────────┐
         ▼                      ▼                      ▼                      ▼                      ▼
  [FASE 1: SUB-200MB SLM] [FASE 2: MICRO-RAG]    [FASE 3: SLIDING CONTEXT] [FASE 4: MICRO-MOE]    [FASE 5: CONTINUOUS]
  2-bit Packed `.jay`     MiniLM (23MB) +        16K Sliding Window      4x Micro-Experts        ArXiv Micro-Delta
  SmolLM-135M / Qwen0.5B  GraphRAG SQLite        H2O KV-Cache (<20MB)    (Total < 150MB)         Patches (<5MB)
```

---

## 📋 Checklist Upgrade Kepintaran JAYA_CORE (< 200 MB)

### 🧠 Fase 1: Sub-200MB Small Language Model (SLM) & 2-Bit Quantization Engine
- [ ] **Physical `.jay` Model Weight Quantization (< 150 MB)**
  - [ ] Support SmolLM-135M Instruct (Q4/Q8 ~80MB-130MB).
  - [ ] Support Qwen2.5-0.5B with 2-bit Packed Weight `.jay` format (~140MB).
  - [ ] Support BitNet 1.58-bit Ternary Weight Models (100M-200M parameters under 100MB).
- [ ] **Indonesian Academic & Coding LoRA Micro-Adapters (< 15 MB)**
  - [ ] Fine-tune micro-LoRA adapters on Indonesian thesis structure (BAB I - BAB V, ABSTRAK).
  - [ ] Fine-tune micro-adapters on Kotlin, Python, and System Engineering instructions.
- [ ] **Structured Tool Calling & JSON Spec Emission**
  - [ ] Emit structured JSON function calls for local tools (RAG search, File editing, Smart Home).

### 🔍 Fase 2: Micro-GraphRAG & Compact Vector Retrieval (< 30 MB)
- [ ] **Ultra-Lightweight Vector Embeddings**
  - [ ] Upgrade vector vault to use **all-MiniLM-L6-v2 (23 MB)** or **BGE-Micro (30 MB)**.
  - [ ] Combine BM25 keyword search + Dense Vector search using Reciprocal Rank Fusion (RRF).
- [ ] **SQLite Micro-GraphRAG Engine**
  - [ ] Construct entity-relation knowledge graphs inside lightweight SQLite tables without external dependencies.
  - [ ] Multi-hop graph reasoning over thesis documents.

### ⚡ Fase 3: Dynamic Sliding Context Window & KV-Cache Compression (< 20 MB RAM)
- [ ] **16K-32K Token Sliding Context Window (RoPE Scaling)**
  - [ ] Implement YaRN / RoPE position interpolation for 16,000+ token context window.
- [ ] **Heavy-Hitter Oracle (H2O) KV-Cache Eviction**
  - [ ] Dynamic KV-cache pruning to keep RAM overhead under 20 MB during long conversations.
  - [ ] Enable smooth processing of PDF thesis drafts and long context turns.

### 🎭 Fase 4: Micro Mixture-of-Experts (Micro-MoE < 150 MB Total)
- [ ] **Sparse Micro-MoE Expert Routing**
  - [ ] **Expert 1 - Thesis & Scientific Writing**: Micro-expert (~35MB).
  - [ ] **Expert 2 - Code & Logic Engineering**: Micro-expert (~35MB).
  - [ ] **Expert 3 - Mathematics & Reasoning**: Micro-expert (~35MB).
  - [ ] **Expert 4 - Natural Conversational Dialogue**: Micro-expert (~35MB).
  - [ ] Total active memory for all 4 micro-experts combined strictly under 150 MB.
- [ ] **Micro-Reflexion Self-Correction Loop**
  - [ ] Candidate verification and self-consistency check before returning answer.

### 🔄 Fase 5: Continuous Micro-Evolution & ArXiv Auto-Patching
- [ ] **ArXiv Auto-Research Micro-Delta Patches (< 5 MB)**
  - [ ] Automatically scan daily ArXiv papers and deploy micro-LoRA / delta patches to `JAYA_CORE`.
- [ ] **Idle Hour Micro-Evolution (Pillar 28 & LiveEvolver)**
  - [ ] Run micro-evolutionary weight updates during idle PC hours within the sub-200MB boundary.

---

## 📊 Benchmarking & Success Metrics (< 200 MB Boundary)

| Metric | Target Baseline | Ultra-Intelligence Goal (<200MB) |
| :--- | :--- | :--- |
| **Model Size Footprint** | 53 KB Stub / 12 MB | **< 150 MB (Physical `.jay` Model)** |
| **Vector DB + Embeddings** | SQLite String Search | **all-MiniLM-L6-v2 (23 MB) + GraphRAG** |
| **Context Window Memory** | 4,096 Tokens | **16,000+ Tokens (H2O KV-Cache < 20MB)** |
| **Inference Speed (Host PC)** | > 50 tokens/sec | **> 120 tokens/sec (Pure CPU / NPU)** |
| **Indonesian Thesis Reasoning** | Template Matching | **Dynamic Neural Generation (<200MB)** |

---

*Document version: 2.1.0 — JAYA_CORE Sub-200MB Sovereign AI Architecture*
