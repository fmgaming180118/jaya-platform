# Phase 2 Kickoff Plan

## Goal
Implement safe self-upgrade/promotion gate while preserving Phase 1 boundary guarantees.

## Week 1 Execution Plan
1. Define evolution candidate contract:
   - candidate metadata schema,
   - source hash,
   - expected performance target,
   - rollback pointer.
2. Implement promotion gate skeleton:
   - functional test check,
   - security regression check,
   - performance threshold check,
   - resource delta check.
3. Add deterministic rollback path and simulation test.
4. Add CI checks for promotion gate pass/fail scenarios.

## Proposed New Files
- `JAYA_CORE/src/brain_v2/engine/evolution_gate.py`
- `JAYA_CORE/tests/test_phase2_evolution_gate.py`
- `JAYA_CORE/tests/test_phase2_rollback.py`

## Implemented Baseline (Current)
- Added `evolution_gate.py` with:
   - candidate contract (`EvolutionCandidate`),
   - evidence contract (`CandidateEvidence`),
   - deterministic decision model (`GateDecisionCode`),
   - rollback snapshot manager (idempotent rollback).
- Added runtime integration hooks in `brain_v2/engine/runtime.py`:
   - `register_stable_state(...)`,
   - `evaluate_evolution_candidate(...)`,
   - `rollback_stable_state(...)`,
   - `evolution_gate` status surface.
- Added test coverage:
   - pass/fail gate decisions,
   - security reject path,
   - resource/performance reject paths,
   - rollback idempotency and runtime smoke.

## Dependencies
- Uses frozen Phase 1 JayaIR/runtime baseline.
- Uses existing benchmark gate outputs as performance baseline reference.

## Entry Criteria
- Phase 1 sign-off complete.
- `PHASE1_EXIT_CHECKLIST.md` fully approved.
- Latest strict benchmark gate PASS.

## Exit Criteria (Phase 2 draft)
- Promotion gate rejects unsafe candidates deterministically.
- Rollback always restores previous stable state.
- No regression in Phase 1 benchmark gate.
- Security reviewer confirms no bypass path from candidate execution.
