# JAYA_CORE

[![Phase1 Benchmark Gate](https://github.com/fmgaming180118/jaya-research/actions/workflows/phase1-benchmark-gate.yml/badge.svg)](https://github.com/fmgaming180118/jaya-research/actions/workflows/phase1-benchmark-gate.yml)

**JAYA** — The **cognitive core (brain)** of a JARVIS-inspired AI assistant.  
Not an OS, not an agent framework — a **sovereign, offline-first reasoning engine** that thinks, plans, and learns. The "brain" that lives inside the house (os_kernel).

## Vision: Building the Brain, Not the Encyclopedia

> **"The goal is to build a *smart brain*, not a brain stuffed with knowledge."**

JAYA_CORE focuses on **cognitive capabilities** — reasoning, planning, intent understanding, self-improvement — not on storing facts or acting as an OS. Knowledge is external (retrieved on demand); intelligence is internal (the core competency).

| What JAYA_CORE **IS** | What JAYA_CORE **IS NOT** |
|----------------------|---------------------------|
| ✅ Reasoning & planning engine | ❌ Knowledge base / encyclopedia |
| ✅ Intent → Action pipeline | ❌ Operating system / shell |
| ✅ Self-improving cognitive core | ❌ Agent framework / tool caller |
| ✅ Sovereign, offline-first brain | ❌ Cloud-dependent service |
| ✅ Lightweight (runs on CPU) | ❌ Heavy model server |

**Analogy**: `os_kernel` = the house (body, sensors, actuators). `brain_v2` = JAYA (the mind living inside). JAYA_CORE = **just the brain**.

## Phase 1 Status
- JayaIR schema, translator, and executor are implemented.
- Runtime path `Intent -> Lingua Logica -> JayaIR -> Execution` is active.
- Benchmark gate is available for local runs and CI.

## Quickstart

Run core Phase 1 tests (validates the reasoning pipeline):

```bash
python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v
```

Run strict benchmark gate (measures cognitive throughput):

```bash
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

Generate latest benchmark snapshot:

```bash
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 80 --gate --json-out JAYA_CORE/docs/phase1_benchmark_latest.json
```

Run interactive JAYA chat (talk to the brain directly):

```bash
python JAYA_CORE/scripts/jaya_chat_cli.py
```

## Architecture: Brain vs House (Home/Resident Split)

```
┌─────────────────────────────────────────────────────────────────┐
│                        JAYA OS (The House)                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  os_kernel (Home Layer) — Body, Sensors, Actuators        │  │
│  │  • Device runtime, windowing, feature mounting            │  │
│  │  • Hardware abstraction, resource monitoring              │  │
│  │  • Policy enforcement, sandbox execution                  │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  brain_v2 (Resident Layer) — JAYA'S MIND (THIS IS CORE)   │  │
│  │  • COGNITION: Intent understanding, planning, reasoning   │  │
│  │  • MEMORY: Strategy, consolidation, temporal weighting    │  │
│  │  • LEARNING: Self-improvement, morphic evolution          │  │
│  │  • LANGUAGE: Lingua Logica → JayaIR → Execution           │  │
│  └───────────────────────────────────────────────────────────┘  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Language Layer (Shared Utility)                          │  │
│  │  • Translation contracts, IR definitions used by both brain and house                             │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

**Key Principle**: The brain (`brain_v2`) reasons; the house (`os_kernel`) executes. The brain never directly controls hardware — it emits intent specifications that the house validates and runs.

## Hierarchy of Connectivity and Privacy
Jaya's brain employs a layered connection strategy:
1. **Local (Offline-First)**: Tiny on-device LLM + compressed KB for zero-latency, private reasoning.
2. **LAN (Personal Network)**: Trusted personal device sync for knowledge deltas (no public internet).
3. **Public Internet (Fallback)**: Only when local+LAN insufficient; vetted services only, encrypted.

The brain stays functional and private offline; knowledge retrieval is a *tool*, not the brain itself.

## Cognitive Capabilities (Implemented in JAYA_CORE)

| Cognitive Capability | Phase/Pillar | Status | Description |
|---------------------|--------------|--------|-------------|
| **Intent Understanding** | Phase 1 | ✅ | Natural language → structured intent (Lingua Logica) |
| **Reasoning Pipeline** | Phase 1 | ✅ | Intent → JayaIR → Cached execution plans |
| **Benchmark-Gated Thinking** | Phase 1 | ✅ | p50/p95 latency gates, hit-rate thresholds |
| **Safe Self-Improvement** | Phase 2 | ✅ | Signed candidates, manifest verification, deterministic rollback |
| **Dynamic Spec Generation** | Phase 3C | ✅ | Intent → UI/Feature specs (for house to execute) |
| **Resource-Aware Cognition** | Pillar 2 | ✅ | CPU/RAM/battery → adaptive sparsity (top-k) |
| **Ethical Reasoning Guardrails** | Pillar 3 | ✅ | Zero-trust, ethical heart, DNA anchor sovereignty |
| **Proactive Intelligence** | Pillars 4-5 | ✅ | Spontaneity, temporal memory, collective pulse |

## Docs
- [Roadmap Kognitif](docs/roadmap_ai_native_os.md) — Phase 1-4: JayaIR, Evolution, Spec Gen, Proactive
- [Phase 1 Benchmark Report](docs/phase1_benchmark_report.md)
- [Phase 1 Decision Log](docs/PHASE1_DECISION_LOG.md)
- [Phase 1 Exit Checklist](docs/PHASE1_EXIT_CHECKLIST.md)
- [Phase 1 Sign-Off](docs/PHASE1_SIGNOFF_TEMPLATE.md)
- [Phase 1→2 Handoff](docs/PHASE1_TO_PHASE2_HANDOFF.md)
- [Latest Benchmark JSON](docs/phase1_benchmark_latest.json)
- [Hierarchy of Connectivity and Privacy](docs/connection_hierarchy.md)
- [Rollback Plan](docs/ROLLBACK_PLAN.md)
- [Production Release Checklist](docs/PRODUCTION_RELEASE_CHECKLIST.md)

*Archived docs (old drafts, superseded): [docs/archive/](docs/archive/)*

## CI Workflow
- Workflow: `.github/workflows/phase1-benchmark-gate.yml`
- Trigger: `push` and `pull_request` for changes under `JAYA_CORE/**`
