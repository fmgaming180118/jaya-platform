# Phase 1 to Phase 2 Handoff

## Purpose
This handoff is the transition package after Phase 1 rebaseline and sign-off preparation.

## Required Inputs (must exist)
- `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`
- `JAYA_CORE/docs/PHASE1_SIGNOFF_DRAFT_2026-03-27.md`
- `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`
- `JAYA_CORE/docs/phase1_benchmark_report.md`
- `JAYA_CORE/docs/phase1_benchmark_latest.json`

## Final Pre-Transition Verification
Run all commands before Phase 2 branch kickoff:

```bash
python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py JAYA_CORE/tests/test_phase1_architecture_boundary.py JAYA_CORE/tests/test_phase1_ir_benchmark.py JAYA_CORE/tests/test_phase1_benchmark_gate.py -q
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95 --json-out JAYA_CORE/docs/phase1_benchmark_latest.json
```

## Freeze Commit Rule
Before Phase 2 starts:
1. Confirm all mandatory sign-offs are complete.
2. Create one freeze commit containing only:
   - updated sign-off document,
   - latest benchmark JSON,
   - any doc-only governance updates.
3. Tag release candidate (example): `phase1-closed-v0.1`.

## Boundary Rules Carried into Phase 2
- `os_kernel` remains home/policy owner.
- `brain_v2` remains resident/intelligence owner.
- No direct `brain_v2 -> os_kernel` imports without explicit architecture approval.

## Phase 2 Allowed Scope (high level)
- Evolution and promotion gate internals.
- Signed candidate metadata + deterministic rollback policy.
- Expanded validation around safe self-improvement flow.

## Current Implementation Status
- Phase 2 baseline implementation has started in `brain_v2` with:
   - `src/brain_v2/engine/evolution_gate.py`,
   - `tests/test_phase2_evolution_gate.py`,
   - `tests/test_phase2_rollback.py`,
   - runtime hooks for candidate evaluation and rollback.

## Phase 2 Explicitly Not Allowed (until approved)
- UI feature compiler and dynamic mount stack changes in `os_kernel` (Phase 3 scope).
- Breaking changes to JayaIR v0.1 contract unless approved by architecture review.

## Ownership
- Technical lead owns transition completion.
- Architecture reviewer owns boundary continuity.
- Performance reviewer owns benchmark threshold continuity.
- Security reviewer owns safety gate continuity.
