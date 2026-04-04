---
description: "Use when editing JAYA_RESEARCH experiments, research workflows, evolution scripts, or research tests. Enforces safe experimentation defaults, focused tests, environment checks, and no autonomous loops unless explicitly requested."
name: "JAYA Research Safety Defaults"
applyTo: "JAYA_RESEARCH/**"
---
# JAYA Research Safety Defaults

- Keep experiments isolated and reversible.
- Do not import from `JAYA_CORE` in `JAYA_RESEARCH` code.
- Prefer focused test runs over full-suite execution during iteration.
- Check environment dependencies before network workflows (for example `.env` values and API keys).
- Require graceful fallback behavior when external services are unavailable.
- Put research documentation in `JAYA_RESEARCH/docs/` (except `JAYA_RESEARCH/README.md`).

## Safe Execution Policy
- Do not run autonomous self-mutation loops unless the user explicitly asks:
  - `python JAYA_RESEARCH/src/discovery.py --forever`
  - `python JAYA_RESEARCH/src/jit_discovery.py --forever`
- Prefer bounded and auditable commands in normal development flow.

## Validation Defaults
- Install dependencies only when needed: `pip install -r JAYA_RESEARCH/requirements.txt`
- Prefer focused tests for touched area, for example:
  - `python -m pytest JAYA_RESEARCH/tests/test_crucible.py -v`
  - `python -m pytest JAYA_RESEARCH/tests/test_research_memory.py -v`

## Source Of Truth
- `JAYA_RESEARCH/README.md`
- `JAYA_RESEARCH/docs/RESEARCH_ASSISTANT.md`
- `JAYA_RESEARCH/docs/architecture.md`
