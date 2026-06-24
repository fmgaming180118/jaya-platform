# JAYA_CORE

[![Phase1 Benchmark Gate](https://github.com/fmgaming180118/jaya-research/actions/workflows/phase1-benchmark-gate.yml/badge.svg)](https://github.com/fmgaming180118/jaya-research/actions/workflows/phase1-benchmark-gate.yml)

Core runtime and sovereignty layer for JAYA OS.

## Phase 1 Status
- JayaIR schema, translator, and executor are implemented.
- Runtime path `Intent -> Lingua Logica -> JayaIR -> Execution` is active.
- Benchmark gate is available for local runs and CI.

## Quickstart

Run core Phase 1 tests:

```bash
python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v
```

Run strict benchmark gate:

```bash
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

Generate latest benchmark snapshot:

```bash
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 80 --gate --json-out JAYA_CORE/docs/phase1_benchmark_latest.json
```

Run interactive JAYA chat:

```bash
python JAYA_CORE/scripts/jaya_chat_cli.py
```

## Docs
- [Roadmap AI Native OS](docs/roadmap_ai_native_os.md)
- [Phase 1 Benchmark Report](docs/phase1_benchmark_report.md)
- [Phase 1 Decision Log](docs/PHASE1_DECISION_LOG.md)
- [Phase 1 Exit Checklist](docs/PHASE1_EXIT_CHECKLIST.md)
- [Phase 1 Sign-Off Template](docs/PHASE1_SIGNOFF_TEMPLATE.md)
- [Phase 1 Sign-Off Guide](docs/PHASE1_SIGNOFF_GUIDE.md)
- [Phase 1 Sign-Off Draft 2026-03-27](docs/PHASE1_SIGNOFF_DRAFT_2026-03-27.md)
- [Phase 1 to Phase 2 Handoff](docs/PHASE1_TO_PHASE2_HANDOFF.md)
- [Phase 2 Kickoff Plan](docs/PHASE2_KICKOFF_PLAN.md)
- [Latest Benchmark JSON](docs/phase1_benchmark_latest.json)
- [Hierarchy of Connectivity and Privacy](docs/connection_hierarchy.md)

## Hierarchy of Connectivity and Privacy
Jaya AI employs a layered connection strategy to balance capability, privacy, and resource usage:
1. **Local (Offline-First)**: Uses a tiny on-device LLM and compressed knowledge base for zero-latency, private responses.
2. **LAN (Personal Network)**: When a trusted personal device (e.g., laptop) is on the same network, Jaya can synchronize knowledge deltas and query the larger personal knowledge base without using public internet.
3. **Public Internet (Fallback)**: Only used when local and LAN are insufficient and the user's value model permits; access is restricted to vetted services (e.g., Wikipedia, DuckDuckGo) with strict input/output filtering and encryption.

This hierarchy ensures Jaya remains functional and private even offline, while still being able to leverage broader knowledge when appropriate and safe.

## CI Workflow
- Workflow: `.github/workflows/phase1-benchmark-gate.yml`
- Trigger: `push` and `pull_request` for changes under `JAYA_CORE/**`
