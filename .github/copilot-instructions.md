# Project Guidelines

## Scope
- Main product folders are `JAYA_CORE` and `JAYA_RESEARCH`.
- `JAYA_CORE` is the sovereign runtime/core brain; `JAYA_RESEARCH` is the research and experimentation layer.
- `JAYA_CORE` and `JAYA_RESEARCH` are isolated domains. Do not couple them through direct imports or shared internal modules.
- Keep changes scoped to the requested area. Do not modify `blueprint/` snapshots unless explicitly asked.

## Repository Layout
- Root directory is for workspace-level assets only (`.github/`, `.vscode/`, `docs/`, launcher `.bat`, and top-level identity/data files already present).
- Do not create ad-hoc root files like scratch `.py`, `.txt`, or temporary logs.
- Keep domain files in their own folder:
  - `JAYA_CORE/**` for core runtime, core tests, and core diagnostics
  - `JAYA_RESEARCH/**` for research runtime, research tests, and research artifacts
- Documentation placement:
  - `docs/` at root for cross-cutting documentation only
  - `JAYA_CORE/docs/` for core-only documentation
  - `JAYA_RESEARCH/docs/` for research-only documentation
- Avoid creating `tests/` at root. Put tests under `JAYA_CORE/tests/` or `JAYA_RESEARCH/tests/`.

## Architecture
- Respect the resident/home boundary: `src/brain_v2` (resident) must not directly import `src/os_kernel` (home).
  - Guarded by `JAYA_CORE/tests/test_phase1_architecture_boundary.py`.
- Do not add direct code-level dependencies between `JAYA_CORE` and `JAYA_RESEARCH`.
- Treat JayaIR as frozen contract for Phase 1 (`v0.1`): avoid opcode/schema drift unless architecture docs and tests are updated together.
  - See `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`.
- For Phase 2 evolution work, preserve signed candidate evaluation, manifest verification, and deterministic rollback behavior.
  - See `JAYA_CORE/tests/test_phase2_evolution_gate.py`, `JAYA_CORE/tests/test_phase2_manifest.py`, and `JAYA_CORE/tests/test_phase2_rollback.py`.

## Build And Test
- Baseline Python version is `3.12` (see `JAYA_CORE/pyrightconfig.json` and CI workflow).
- Prefer existing VS Code tasks in `.vscode/tasks.json` when available.

For `JAYA_CORE` changes, run targeted gates:
- `python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v`
- `python -m pytest JAYA_CORE/tests/test_phase1_ir_benchmark.py JAYA_CORE/tests/test_phase1_benchmark_gate.py JAYA_CORE/tests/test_phase1_architecture_boundary.py -v`
- `python -m pytest JAYA_CORE/tests/test_phase2_evolution_gate.py JAYA_CORE/tests/test_phase2_rollback.py JAYA_CORE/tests/test_phase2_manifest.py -v`
- `python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95`

For `JAYA_RESEARCH` changes:
- Install deps with `pip install -r JAYA_RESEARCH/requirements.txt` when needed.
- Prefer focused test runs, for example: `python -m pytest JAYA_RESEARCH/tests/test_crucible.py -v`.

Do not run self-mutation loops unless explicitly requested by the user:
- `python JAYA_RESEARCH/src/discovery.py --forever`
- `python JAYA_RESEARCH/src/jit_discovery.py --forever`

## Conventions
- Keep docs in the correct location:
  - `JAYA_CORE/docs/` for core-specific documentation
  - `JAYA_RESEARCH/docs/` for research-specific documentation
  - `docs/` at repo root for cross-cutting architecture notes
- Follow existing cross-platform test style using `pathlib.Path` and explicit `sys.path` insertion as seen in `JAYA_CORE/tests/`.
- Avoid heavy dependencies unless there is clear and measurable benefit for low-resource goals.

## References
- `JAYA_CORE/README.md`
- `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`
- `JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md`
- `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`
- `JAYA_CORE/docs/architecture.md`
- `JAYA_RESEARCH/README.md`
- `JAYA_RESEARCH/docs/RESEARCH_ASSISTANT.md`
- `JAYA_RESEARCH/docs/architecture.md`
- `docs/arsitektur_jaya_core.md`
- `docs/arsitektur_jaya_research.md`
- `docs/matematika_jaya_agi.md`