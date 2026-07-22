# Phase 1 Decision Log (Rebaseline)

## Purpose
This log freezes architectural decisions for Phase 1 to prevent scope drift and boundary confusion.

## D-001 Home vs Resident Boundary
- Decision: `os_kernel` is the home layer (OS ownership, resource/policy authority).
- Decision: `brain_v2` is the resident layer (intent, cognition, planning, JayaIR execution).
- Consequence: Phase 1 implementation remains in `brain_v2`; no direct `brain_v2 -> os_kernel` imports.

## D-002 JayaIR Contract Freeze
- Decision: JayaIR contract is frozen at version `0.1` with state `phase1_frozen`.
- Decision: No new opcode additions in Phase 1 unless explicit rebaseline approval.
- Consequence: Prevents translator/executor churn and keeps benchmark comparability stable.

## D-003 Validator Safety Model
- Decision: Lenient mode is allowed, but unknown opcodes are marked non-executable.
- Decision: Unknown opcodes may carry fallback metadata; they cannot execute side effects.
- Consequence: Maintains safety while preserving tolerance for imperfect intent mappings.

## D-004 Runtime Integration Rule
- Decision: Runtime uses a single JayaIR executor factory path for initialization and lazy load.
- Consequence: Avoids drift across duplicate init paths and keeps cache policy centralized.

## D-005 Benchmark Gate Policy
- Decision: Benchmark gate remains mandatory for Phase 1 promotion checks.
- Default thresholds:
  - warm p50 <= 0.05 ms
  - warm p95 <= 0.10 ms
  - hit-rate >= 0.95
- Consequence: Functional success without performance stability is not accepted.

## D-006 Automation Topology
- Decision: VS Code tasks live in workspace root `.vscode/tasks.json`.
- Decision: CI workflow lives in root `.github/workflows/phase1-benchmark-gate.yml`.
- Consequence: Tooling remains discoverable by default editor and GitHub Actions behavior.

## Out of Scope (Phase 1)
- Self-upgrade promotion gate internals (Phase 2).
- Dynamic UI compiler and feature mount stack in `os_kernel` (Phase 3).
- Any OS-home policy mutation through resident-layer patches.

## Change Control
Any Phase 1 contract/boundary change must:
1. update this decision log,
2. update architecture roadmap,
3. add/adjust test coverage,
4. rerun strict benchmark gate.

## Exit Gate
Phase completion and promotion readiness must follow:
- `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`
