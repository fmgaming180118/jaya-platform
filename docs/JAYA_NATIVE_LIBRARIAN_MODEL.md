# JAYA Native Librarian Model (V0)

**Architecture Name:** JAYA Librarian Transformer  
**Version:** 0.1  
**Purpose:** Compact retrieval-native reasoning model

The native JAYA model is designed around the Librarian Philosophy:
- **Model parameters (Weights)** = *How to think*
- **JAYA Library (SQLite + Index)** = *What is known*
- **Catalog** = *Where to find it*

## Neural Architecture to 40-Pillar Mapping

The native neural architecture does not implement every pillar through separate layers, but explicitly learns the competencies of these cognitive pillars through architecture choices and training targets:

**Primary Pillars (Learned natively in weights):**
- **P1 (Pure Logic):** General logical reasoning capability over context.
- **P3 (Active Dreaming):** Internal evaluation of evidence hypotheses before action.
- **P21 (Lingua Logica):** Decoding language queries into structured JSON (JayaIR).
- **P26 (Semantic Bridge):** Understanding relationships in the Code Symbol Graph (Callers, Callees, Tests).
- **P33 (Agentic RAG):** Decision to trigger retrieval (`retrieval_required`), query generation, and evidence synthesis.
- **P36 (Speculative Reasoning):** Exploring multi-hop candidates for missing information.
- **P38 (Meta Cognitive Planning):** Assessing `information_needs` and recognizing `INSUFFICIENT_EVIDENCE`.
- **P40 (Intent Extrapolation):** Determining the core intent of a knowledge query.

**Supporting Hybrid Pillars (Model + Runtime):**
- **P2 (Resource Aware):** Kept compact to allow local execution.
- **P8 (Holographic Memory):** Retaining contextual references across the retrieval loops.
- **P34 & P35 (Sparsity):** Future-proofed for MoE and sparse activations to reduce flops.

## The Native Generative Architecture (PyTorch)

Rather than wrapping `AutoModelForCausalLM` from a pre-trained external weights-set as the final architecture, JAYA Core V0 provides a native Transformer implementation:

```
Token Embedding
│
├── N × JayaLibrarianBlock
│   ├── RMSNorm
│   ├── Causal Multi-Head Attention
│   ├── Retrieval / Evidence Conditioning
│   └── Gated FFN (SwiGLU)
│
├── Final RMSNorm
│
└── Multi-Objective Heads:
    ├── Language Modeling Head (Answers / JSON keys)
    ├── Retrieval Decision Head (Optional dedicated classification)
    └── Evidence Sufficiency Head (Optional dedicated classification)
```

## Explicit Output Contract (JayaIR JSON)

The model is trained to output the following JSON schema explicitly (without relying purely on prompt engineering over a generic model):

```json
{
  "intent": "What the user actually wants to accomplish",
  "information_needs": ["List of missing facts required"],
  "retrieval_required": true,
  "retrieval_queries": ["query 1", "query 2"],
  "evidence_refs": ["canonical_id_1"],
  "answer": "Grounded answer, or INSUFFICIENT_EVIDENCE",
  "confidence": 0.95,
  "unknowns": ["Facts still missing after retrieval"],
  "jaya_ir": null
}
```

## Training Curriculum

The model learns from a robust curriculum mapped directly to its Librarian responsibilities:
- Retrieval need detection
- Query refinement & multi-hop retrieval
- Conflicting sources handling
- Irrelevant retrieval rejection
- Caller/callee graph reasoning

## Artifact Identity

The final artifact is identified strictly as:
`architecture = jaya_librarian_native_v0`

It is completely distinct from the `BootstrapLibrarianModel` (SmolLM/Qwen wrapper) used to synthesize its training curriculum or serve as a comparative baseline.
