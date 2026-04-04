---
name: "JAYA Repo Layout Cleanup"
description: "Audit and auto-tidy misplaced files based on repository structure policy, then report before and after status."
argument-hint: "Mode: audit-only or audit-and-fix"
agent: "agent"
---
Run repository cleanup based on policy in `docs/structure_policy.md` and `.github/instructions/repository-layout.instructions.md`.

Execution flow:
1. Run audit checker:
   - `python .github/tools/repo_layout_audit.py --json-out docs/repo_layout_audit_latest.json`
2. If mode is `audit-only`, stop after reporting findings.
3. If mode is `audit-and-fix`, apply safe auto-fixes in one pass:
   - Move misplaced root tests to domain tests/diagnostics when ownership is clear.
   - Move misplaced markdown docs to `docs/`, `JAYA_CORE/docs/`, or `JAYA_RESEARCH/docs/` according to scope.
   - Move ad-hoc root logs and temporary artifacts into domain docs/verification or delete if disposable and already captured.
4. Do not modify `blueprint/` snapshots.
5. Do not introduce direct imports between `JAYA_CORE` and `JAYA_RESEARCH`.
6. Re-run audit checker:
   - `python .github/tools/repo_layout_audit.py --json-out docs/repo_layout_audit_latest_after_fix.json`

Output format:

## Cleanup Report
- Mode:
- Policy files used:
- Files moved:
- Files deleted:

## Audit Before
- Status:
- Violation count:
- Top rules:

## Audit After
- Status:
- Violation count:
- Remaining blockers:

## Next Actions
1. ...
2. ...
