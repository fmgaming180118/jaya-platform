# Phase 1 Exit Checklist

## Objective
This checklist is the mandatory sign-off gate before promoting JAYA_CORE from Phase 1 to Phase 2.

## A. Scope Integrity (Home vs Resident)
- [x] `brain_v2` remains the owner of Phase 1 JayaIR logic.
- [x] `os_kernel` remains the owner of home/OS policy and device authority.
- [x] No direct `brain_v2 -> os_kernel` import dependency exists.
- [x] Scope does not include Phase 2/3 features.

## B. Contract Freeze (JayaIR v0.1)
- [x] JayaIR contract version is `0.1`.
- [x] Phase state is `phase1_frozen`.
- [x] Opcode taxonomy is frozen for Phase 1.
- [x] Validator behavior is stable (strict and lenient semantics unchanged).
- [x] Signature generation remains deterministic.

## C. Functional Readiness
- [x] Core tests pass: `JAYA_CORE/tests/test_phase1_jaya_ir.py`.
- [x] Runtime intent path works: `text -> Lingua Logica -> JayaIR -> result`.
- [x] Executor unavailable path returns structured error (no silent failure).

## D. Security and Safety
- [x] Lenient mode marks unknown opcodes as non-executable.
- [x] Unknown opcode path cannot execute side effects.
- [x] Twin feedback can invalidate cache only (no schema mutation path).

## E. Performance Gate
- [x] Strict benchmark gate passes.
- [x] Warm p50 is within threshold.
- [x] Warm p95 is within threshold.
- [x] Cache hit-rate is within threshold.
- [x] Warm path is not worse than cold path.

Reference command:

```bash
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

## F. Automation Readiness
- [x] Local task entry exists in `.vscode/tasks.json`.
- [x] CI workflow exists in `.github/workflows/phase1-benchmark-gate.yml`.
- [x] CI workflow includes benchmark guard tests.
- [x] CI workflow includes strict benchmark gate execution.

## G. Documentation and Governance
- [x] Roadmap reflects Home vs Resident boundary.
- [ ] Decision log is current and approved.
- [x] Benchmark report is current.
- [x] Latest benchmark JSON snapshot exists.

## H. Final Sign-Off
- [ ] Technical lead sign-off
- [ ] Architecture sign-off
- [ ] Performance sign-off
- [ ] Security sign-off

Reviewer form:
- `JAYA_CORE/docs/PHASE1_SIGNOFF_TEMPLATE.md`

Sign-off metadata:
- Date: 2026-03-27
- Reviewer(s): Draft populated by Copilot; human reviewer approval pending
- Commit SHA: 5d3d8a3
- Notes:
	- Latest local verification: `13 passed` for Phase 1 test suite.
	- Latest strict benchmark gate: PASS with thresholds p50<=0.05, p95<=0.10, hit_rate>=0.95.
	- Decision log approval and final human sign-offs remain required.
