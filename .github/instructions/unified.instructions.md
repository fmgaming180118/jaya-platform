---
description: "Unified instructions for JAYA repository. Covers AI foundation principles, strict project separation (JAYA_CORE vs JAYA_RESEARCH), repository layout discipline, and domain-specific rules for each project."
applyTo: "**"
---

# JAYA Unified Instructions

This file consolidates all repository instructions. It applies to the entire workspace (`**`) with domain-specific sections for `JAYA_CORE/**` and `JAYA_RESEARCH/**`.

---

## 1. AI Foundation Principles (Repo-Wide)

### Purpose
- Provide minimal rules, constraints, and conventions for developing AI systems in this repository.
- Serve as the foundation for domain-specific instructions (`JAYA_CORE`, `JAYA_RESEARCH`).

### Core Principles
- **Domain Isolation**: No direct code dependencies between `JAYA_CORE` and `JAYA_RESEARCH`.
- **Security & Privacy**: Identify sensitive data, restrict access, never commit secrets. Use secret managers / environment variables.
- **Deterministic Experiments**: Experiments must be reproducible — save seeds, dataset versions, and parameters.
- **Minimal Dependencies**: Add dependencies only with clear, measurable benefit; prefer lightweight, stable libraries.
- **No Autonomous Loops Without Consent**: Scripts with `--forever`, worker daemons, or continuous self-mutation require explicit operator approval and gated tests.

### Architecture & Boundary Rules
- `JAYA_CORE` is the sovereign runtime (core brain). Avoid reverse imports from `JAYA_RESEARCH` → `JAYA_CORE`.
- JayaIR schema is **frozen for Phase 1 (v0.1)** — schema changes require handoff docs and gate tests.
- Research utilities, experiments, sandboxes → `JAYA_RESEARCH/`; production runtime code → `JAYA_CORE/`.
- Public interface `JAYA_RESEARCH` → `JAYA_CORE` must be explicit, one-way: research produces artifacts; direct imports from research to core require review and gating.

### Development, Build & Test
- **Baseline Python**: Version from `pyrightconfig.json` (Python 3.12).
- **Targeted Tests**: Run domain-specific tests when making changes:
  - Core: `python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v`
  - Research: `python -m pytest JAYA_RESEARCH/tests/test_crucible.py -v`
- **Performance Changes**: Run relevant benchmark gates and save JSON snapshots.

### Code Conventions
- Follow existing local style; don't reformat unrelated files.
- Avoid single-letter variables; use descriptive names.
- For ambiguous types in tests, annotate as `Dict[str, Any]` or cast before passing to strictly-typed APIs.

### Experiments & Evolution
- All Phase 2 design evolution must pass gates: manifest verification, rollback test, signed candidate evaluation.
- Automated evolution scripts must have an operator-triggerable kill-switch.

### Operational Security
- **Never commit API keys, secrets, or credentials**. Use secret managers / env vars.
- Secret scanning via CI tools; exceptions only with audit.

### Governance & Review
- Core design changes require review from `JAYA_CORE` maintainers; research changes from `JAYA_RESEARCH` leads.
- PRs must include: change description, backward-compatibility impact, rollback steps.

### Example Instruction Prompts
- "Always use dependency version X.Y.Z for library `foo` unless a written reason exists."
- "Never run `--forever` loops without `--dry-run` and operator approval flag."

### Template for New Rules
- Create `.github/instructions/<name>.instructions.md` with appropriate `applyTo`.

### Iteration & Clarification
- This is a foundation; identify ambiguities and add "Questions" blocks in PRs for discussion.

### Final Note
- Keep strict rules for boundaries and safety; prefer explicitness over implicit behavior.

---

## 2. Project Separation: JAYA_CORE vs JAYA_RESEARCH

### Core Principle
**JAYA_CORE and JAYA_RESEARCH are completely separate, independent projects.** Different purposes, architectures, tech stacks — **never directly coupled** via imports, shared modules, or runtime dependencies.

---

### JAYA_CORE — Lightweight AI Brain (JARVIS-like)

| Aspect | Details |
|--------|---------|
| **Purpose** | Lightweight, offline-first AI brain/runtime for local inference — "JARVIS but lightweight and local-first." |
| **Goal** | Sovereign, low-resource AI runtime running locally on modest hardware (offline-first, privacy-first). |
| **Key Characteristics** | • Sovereign runtime, JayaIR (IR), executor, intent → lingua logica → JayaIR → execution pipeline<br>• Offline-first / privacy-first: local LLM, compressed KB, zero-latency private responses<br>• Tiered connectivity: Local (offline) → LAN (personal network sync) → Public Internet (fallback, vetted services only)<br>• Phase 1: JayaIR schema, translator, executor, benchmark gates (frozen contract v0.1)<br>• Phase 2: Evolution gates, signed candidate evaluation, manifest verification, deterministic rollback<br>• Architecture boundary: `src/brain_v2` (resident) must NOT directly import `src/os_kernel` (home) — guarded by architecture boundary test<br>• Tech stack: Python 3.12, minimal deps, low-resource focus |
| **Tests** | `JAYA_CORE/tests/` — Phase 1 IR, benchmark, architecture boundary, Phase 2 evolution/rollback/manifest gates |
| **Docs** | `JAYA_CORE/docs/` — Phase 1 decision log, Phase 1→2 handoff, architecture, benchmark reports |

**Key Files**:
- `JAYA_CORE/README.md` — Quickstart, benchmark gates, CLI chat
- `JAYA_CORE/docs/PHASE1_DECISION_LOG.md` — Frozen Phase 1 decisions
- `JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md` — Phase transition contract
- `JAYA_CORE/docs/architecture.md` — Architecture specification
- `JAYA_CORE/scripts/benchmark_phase1_ir.py` — Benchmark gate script
- `JAYA_CORE/scripts/jaya_chat_cli.py` — Interactive CLI chat

---

### JAYA_RESEARCH — Academic Research Assistant

| Aspect | Details |
|--------|---------|
| **Purpose** | AI-powered academic research assistant for students/researchers — thesis analysis, journal discovery, defense prep, RAG chat, recursive research. |
| **Goal** | Cloud-powered (NVIDIA NIM) research assistant with FastAPI backend + React frontend. |
| **Key Characteristics** | • Cloud-first: NVIDIA NIM (cloud inference) — requires NVIDIA API key, internet required<br>• Full-stack: FastAPI backend + React 18 frontend<br>• Features: Thesis analyzer (novelty check, gap ID), academic editor, journal discovery (ArXiv + Semantic Scholar), defense simulator, RAG chat, autonomous recursive research, knowledge graph, report export<br>• Tech stack: Python 3.10+, FastAPI, React 18, Node.js 18+, PyMuPDF, NVIDIA NIM API |
| **Tests** | `JAYA_RESEARCH/tests/` — e.g., `test_crucible.py` |
| **Docs** | `JAYA_RESEARCH/docs/` — RESEARCH_ASSISTANT.md, architecture.md |
| **Requirements** | `JAYA_RESEARCH/requirements.txt`, `JAYA_RESEARCH/ui/package.json` |

**Key Files**:
- `JAYA_RESEARCH/README.md` — Full setup, features, requirements
- `JAYA_RESEARCH/requirements.txt` — Python deps
- `JAYA_RESEARCH/ui/` — React frontend
- `JAYA_RESEARCH/src/` — FastAPI backend source

---

### Strict Isolation Rules

| Rule | Enforcement |
|------|-------------|
| **No direct imports** between `JAYA_CORE/**` and `JAYA_RESEARCH/**` | Architecture boundary test (`test_phase1_architecture_boundary.py`) |
| **No shared internal modules** | Repository layout discipline |
| **No shared internal data structures** | Each domain owns its schemas |
| **No cross-domain runtime calls** | Separate processes, separate deployments |
| **Cross-domain contracts require explicit architecture decision** | Document in root `docs/`, update both `PHASE1_DECISION_LOG.md` and `JAYA_RESEARCH/docs/architecture.md` |

---

### When Working in This Repository

1. **Identify the target domain first** — Are you working on `JAYA_CORE/**` or `JAYA_RESEARCH/**`?
2. **Stay in your lane** — Do not import, reference, or couple to the other domain.
3. **Run domain-specific tests** — Use test commands from the respective README.
4. **Document in the right place** — Core docs in `JAYA_CORE/docs/`, Research docs in `JAYA_RESEARCH/docs/`, cross-cutting only in root `docs/`.
5. **If cross-domain interaction is needed** — Stop. Document the contract in root `docs/`. Get explicit approval before implementing.

---

### Quick Reference: Which Project Am I In?

| File Path | Project | Purpose |
|-----------|---------|---------|
| `JAYA_CORE/**` | **JAYA_CORE** | Lightweight local AI brain (JARVIS-like) |
| `JAYA_RESEARCH/**` | **JAYA_RESEARCH** | Cloud academic research assistant |
| `docs/**` (root) | **Cross-cutting** | Architecture decisions affecting both |
| `.github/instructions/**` | **Workspace** | Agent instructions for this repo |

---

## 3. Repository Layout Discipline

### Placement Rules
- **Root** = workspace-level assets only (`.github/`, `.vscode/`, `docs/`, launcher `.bat`, existing identity/data files).
- **No ad-hoc root files** (`*.py`, `*.txt`, temp logs, throwaway scripts).
- **Core work** → `JAYA_CORE/**`
- **Research work** → `JAYA_RESEARCH/**`

### Documentation Rules
- Cross-cutting docs → `docs/` at root
- Core-only docs → `JAYA_CORE/docs/`
- Research-only docs → `JAYA_RESEARCH/docs/`

### Testing Rules
- Keep tests with their domain:
  - `JAYA_CORE/tests/**`
  - `JAYA_RESEARCH/tests/**`
- Avoid creating `tests/` at root unless explicitly requested for a cross-cutting suite.

### Isolation Rules
- `JAYA_CORE` and `JAYA_RESEARCH` are separate domains.
- No direct imports from one domain to the other.
- If a cross-domain contract is needed → stop and ask for explicit architecture direction first.

---

## 4. JAYA_CORE Domain-Specific Rules (applyTo: JAYA_CORE/**)

### Summary
Rules for editing the JAYA_CORE runtime, JayaIR, and core tests. Maintains sovereign runtime integrity, determinism, security, and auditable performance.

### Core Principles
- **Boundary-first**: Avoid imports/dependencies from `JAYA_RESEARCH` → `JAYA_CORE`. All research integration via exported, reviewed artifacts.
- **Minimal dependency**: Add deps only after risk/benefit evaluation; justify in PR.
- **Determinism & Reproducibility**: Experiments affecting runtime must include seed, dataset version, and reproduction config.

### Gates & Tests
Changes touching JayaIR, opcodes, or schema require:
- Unit tests showing backward-compatibility or migration.
- Handoff documentation (`JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md` or related).
- Benchmark evaluation if performance-impacting.

**Run before merge**:
```bash
python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v
# Benchmark gate (if perf-related):
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95
```

### Security & Operations
- **Never commit secrets, API keys, credentials**. Use secret manager + env vars.
- New runtime capabilities must document failure modes and rollback plan.

### Performance Budgets
- Set p50/p95 budgets for critical ops in benchmark gates. Perf regressions require mitigation or revert plan.

### Review & Ownership
- All PRs touching `JAYA_CORE` require core maintainer review.
- Include: short changelog, compatibility notes, rollback steps.

### Packaging & Release
- Finished runtime artifacts packaged consistently: semantic version, changelog, checksum.

### Promoting Artifacts from JAYA_RESEARCH
To promote a research artifact to core, provide:
- Public API contract + input/output spec.
- Minimal integration test running artifact in container/sandbox.
- Dependency & license audit.
- Core maintainer approval.

### PR Checklist Example
- [ ] Unit tests added
- [ ] `JAYA_CORE/docs/` updated if needed
- [ ] Benchmark gate run if perf change
- [ ] Core maintainers tagged for review

### Validation Defaults (Guardrails)
- Prefer VS Code tasks from `.vscode/tasks.json`.
- For JAYA_CORE code changes, run targeted gates:
  1. `python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v`
  2. `python -m pytest JAYA_CORE/tests/test_phase1_ir_benchmark.py JAYA_CORE/tests/test_phase1_benchmark_gate.py JAYA_CORE/tests/test_phase1_architecture_boundary.py -v`
  3. `python -m pytest JAYA_CORE/tests/test_phase2_evolution_gate.py JAYA_CORE/tests/test_phase2_rollback.py JAYA_CORE/tests/test_phase2_manifest.py -v`
  4. `python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95`

### Source of Truth
- `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`
- `JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md`
- `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`
- `JAYA_CORE/tests/test_phase1_architecture_boundary.py`

---

## 5. JAYA_RESEARCH Domain-Specific Rules (applyTo: JAYA_RESEARCH/**)

### Summary
Rules for editing JAYA_RESEARCH experiments, research workflows, evolution scripts, or research tests. Enforces safe experimentation defaults, focused tests, environment checks, and no autonomous loops unless explicitly requested.

### Core Principles
- **Isolated Experimentation**: Experiments may use extra dependencies but must be isolated to `JAYA_RESEARCH` (separate virtualenv/requirements, container).
- **No Autonomous Forever Loops**: Scripts with `--forever` must be clearly labeled, have `--dry-run`, and require operator consent before running in production-like environments.
- **Reproducible Runs**: Save seeds, parameters, and dataset snapshots used.

### Data & Datasets
- Store experimental datasets in `JAYA_RESEARCH/data/`; record source, license, version.
- Avoid committing sensitive data. If needed, document external access and use placeholders.

### Recursive Experiments
- Prototype recursive/self-improving implementations must:
  - Be documented in `JAYA_RESEARCH/docs/` with failure modes, safety mitigations, resource bounds.
  - Run in isolated sandbox; never run directly on developer machine without safeguards.

### Promotion to JAYA_CORE
To promote a research artifact to core, provide:
- Public API contract + input/output spec.
- Minimal integration test + usage docs.
- Core team review + compliance checklist (security, license, performance).

### CI & Environment
- `JAYA_RESEARCH` may have its own `requirements.txt` / workflows; document setup in `JAYA_RESEARCH/README.md`.
- Use environment isolation (venv, conda, container) to avoid global dependency pollution.

### Governance
- High-risk experiments (internet-access agents, automated deployment) require written approval from maintainers and security.

### Experiment Checklist Example
- [ ] Experiment documented in `JAYA_RESEARCH/docs/`
- [ ] Parameters and seed saved
- [ ] Data provenance & license recorded
- [ ] Sandbox & resource bounds defined

### Safe Execution Policy
- **Do not run autonomous self-mutation loops unless explicitly asked**:
  - `python JAYA_RESEARCH/src/discovery.py --forever`
  - `python JAYA_RESEARCH/src/jit_discovery.py --forever`
- Prefer bounded, auditable commands in normal development flow.

### Validation Defaults
- Install deps only when needed: `pip install -r JAYA_RESEARCH/requirements.txt`
- Prefer focused tests for touched area:
  - `python -m pytest JAYA_RESEARCH/tests/test_crucible.py -v`
  - `python -m pytest JAYA_RESEARCH/tests/test_research_memory.py -v`

### Source of Truth
- `JAYA_RESEARCH/README.md`
- `JAYA_RESEARCH/docs/RESEARCH_ASSISTANT.md`
- `JAYA_RESEARCH/docs/architecture.md`

---

## 6. Quick Command Reference

### JAYA_CORE
```bash
# Phase 1 IR tests
python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v

# Phase 1 benchmark + architecture gates
python -m pytest JAYA_CORE/tests/test_phase1_ir_benchmark.py JAYA_CORE/tests/test_phase1_benchmark_gate.py JAYA_CORE/tests/test_phase1_architecture_boundary.py -v

# Phase 2 evolution gates
python -m pytest JAYA_CORE/tests/test_phase2_evolution_gate.py JAYA_CORE/tests/test_phase2_rollback.py JAYA_CORE/tests/test_phase2_manifest.py -v

# Strict benchmark gate
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95

# Benchmark snapshot
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 80 --gate --json-out JAYA_CORE/docs/phase1_benchmark_latest.json

# Interactive CLI chat
python JAYA_CORE/scripts/jaya_chat_cli.py
```

### JAYA_RESEARCH
```bash
# Setup
python -m venv .venv && .venv\Scripts\activate  # Windows
pip install -r JAYA_RESEARCH/requirements.txt
cd JAYA_RESEARCH/ui && npm install

# Focused tests
python -m pytest JAYA_RESEARCH/tests/test_crucible.py -v
python -m pytest JAYA_RESEARCH/tests/test_research_memory.py -v
```

---

## 7. Related Files (Source of Truth)

| File | Purpose |
|------|---------|
| `JAYA_CORE/README.md` | Core quickstart, gates, CLI |
| `JAYA_CORE/docs/PHASE1_DECISION_LOG.md` | Frozen Phase 1 decisions |
| `JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md` | Phase transition contract |
| `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md` | Phase 1 completion criteria |
| `JAYA_CORE/docs/architecture.md` | Core architecture spec |
| `JAYA_RESEARCH/README.md` | Research setup, features, requirements |
| `JAYA_RESEARCH/docs/RESEARCH_ASSISTANT.md` | Research assistant detailed spec |
| `JAYA_RESEARCH/docs/architecture.md` | Research architecture |
| `docs/arsitektur_jaya_core.md` | Cross-cutting core architecture (Indonesian) |
| `docs/arsitektur_jaya_research.md` | Cross-cutting research architecture (Indonesian) |
| `docs/matematika_jaya_agi.md` | Mathematical foundations |