# Repository Structure Policy

This policy keeps JAYA workspace files in the correct domain and prevents root clutter.

## Domain Ownership
- `JAYA_CORE/` owns core runtime, engine, core tests, and core diagnostics.
- `JAYA_RESEARCH/` owns research runtime, experiments, research tests, and research artifacts.
- `JAYA_CORE` and `JAYA_RESEARCH` are separate domains. Direct cross-domain imports are not allowed.

## Root Usage
- Root is only for workspace-level assets, for example:
  - `.github/`, `.vscode/`, `docs/`, launcher `.bat`, and existing top-level identity/data files.
- Do not add ad-hoc root files such as temporary `.py`, `.txt`, and debug logs.

## Documentation Placement
- Cross-cutting documentation: `docs/`
- Core-only documentation: `JAYA_CORE/docs/`
- Research-only documentation: `JAYA_RESEARCH/docs/`

## Test Placement
- Core tests: `JAYA_CORE/tests/`
- Research tests: `JAYA_RESEARCH/tests/`
- Avoid creating `tests/` at root unless explicitly required for cross-cutting validation.

## Diagnostics Placement
- Core diagnostic scripts: `JAYA_CORE/tools/diagnostics/`
- Keep generated verification notes under the related domain docs folder.

## Enforcement
- Workspace instructions and file-specific instructions define placement rules.
- PreToolUse hook blocks common mistakes:
  - long-running self-mutation loop commands without explicit approval
  - writing new files directly to root
  - writing markdown docs to the wrong folder
  - adding direct `JAYA_CORE <-> JAYA_RESEARCH` imports

## Automated Audit
- Run full structure audit:
  - `python .github/tools/repo_layout_audit.py`
- Run audit with machine-readable output:
  - `python .github/tools/repo_layout_audit.py --json-out docs/repo_layout_audit_latest.json`
- Use `--fail-on-violations` in CI or strict checks.
