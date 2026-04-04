---
description: "Use when editing JAYA_CORE runtime, brain_v2 modules, JayaIR schema, evolution gate, or core tests. Enforces boundary checks, benchmark policy, and minimal dependency defaults."
name: "JAYA Core Guardrails"
applyTo: "JAYA_CORE/**"
---
# JAYA Core Guardrails

- Keep changes inside JAYA_CORE unless the user explicitly requests cross-folder work.
- Do not import from `JAYA_RESEARCH` in `JAYA_CORE` code.
- Preserve resident and home ownership boundaries:
  - Do not add direct `src/brain_v2` imports of `src/os_kernel`.
  - If boundary rules must change, update architecture docs and tests in the same change.
- Treat JayaIR Phase 1 as frozen (`v0.1`): avoid opcode/schema drift unless the change is explicitly requested and documented.
- Prefer low-resource implementations and avoid heavy new dependencies unless benefit is measurable.
- Put core documentation in `JAYA_CORE/docs/` (except `JAYA_CORE/README.md`).

## Validation Defaults
- Prefer VS Code tasks from `.vscode/tasks.json` when available.
- For JAYA_CORE code changes, run targeted gates:
  1. `python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v`
  2. `python -m pytest JAYA_CORE/tests/test_phase1_ir_benchmark.py JAYA_CORE/tests/test_phase1_benchmark_gate.py JAYA_CORE/tests/test_phase1_architecture_boundary.py -v`
  3. `python -m pytest JAYA_CORE/tests/test_phase2_evolution_gate.py JAYA_CORE/tests/test_phase2_rollback.py JAYA_CORE/tests/test_phase2_manifest.py -v`
  4. `python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95`

## Source Of Truth
- `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`
- `JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md`
- `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`
- `JAYA_CORE/tests/test_phase1_architecture_boundary.py`
