---
description: "Use when creating or moving files, scripts, tests, or docs. Enforces clean folder placement, root hygiene, and strict isolation between JAYA_CORE and JAYA_RESEARCH."
name: "Repository Layout Discipline"
---
# Repository Layout Discipline

## Placement Rules
- Root is only for workspace-level assets and existing identity files.
- Do not create ad-hoc root files (`*.py`, `*.txt`, temporary logs, throwaway scripts).
- Core work belongs in `JAYA_CORE/**`.
- Research work belongs in `JAYA_RESEARCH/**`.

## Documentation Rules
- Cross-cutting docs go to `docs/` at root.
- Core-only docs go to `JAYA_CORE/docs/`.
- Research-only docs go to `JAYA_RESEARCH/docs/`.

## Testing Rules
- Keep tests with their domain:
  - `JAYA_CORE/tests/**`
  - `JAYA_RESEARCH/tests/**`
- Avoid creating `tests/` at root unless the user explicitly requests a cross-cutting suite.

## Isolation Rules
- `JAYA_CORE` and `JAYA_RESEARCH` are separate domains.
- Do not add direct imports from one domain to the other.
- If a cross-domain contract is needed, stop and ask for explicit architecture direction first.
