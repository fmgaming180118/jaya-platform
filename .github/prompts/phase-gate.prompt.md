---
name: "JAYA Phase Gate Runner"
description: "Run the exact JAYA_CORE phase gate sequence and produce a standardized PASS/FAIL report with key errors and next actions."
argument-hint: "Describe scope: phase1-only, phase2-only, or full"
agent: "agent"
---
Run JAYA_CORE verification gates in this exact order, preferring existing VS Code tasks when available:

1. `JAYA Phase1: Test Core`
2. `JAYA Phase1: Benchmark Guard`
3. `JAYA Phase2: Evolution Gate Tests`
4. `JAYA Phase1: Benchmark Gate (strict)`

Rules:
- Use the workspace tasks first; only use direct terminal commands if a task is unavailable.
- Do not run autonomous self-mutation loops.
- Continue collecting results even if one gate fails, unless the environment is completely blocked.
- If the change is docs-only, ask whether full gates should still be executed.

Return results with this exact structure:

## Phase Gate Report
- Date:
- Scope:
- Runner: tasks or terminal

## Gate Status
1. Phase1 Core: PASS or FAIL
2. Phase1 Benchmark Guard: PASS or FAIL
3. Phase2 Evolution Gate Tests: PASS or FAIL
4. Phase1 Strict Benchmark Gate: PASS or FAIL

## Failure Details
- Gate:
- Key error:
- Suspected source:

## Final Verdict
- Overall: PASS or FAIL
- Merge readiness: READY or NOT READY

## Suggested Next Actions
1. ...
2. ...
