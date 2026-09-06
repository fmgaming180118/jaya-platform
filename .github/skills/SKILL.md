---
name: jaya-canonical-pillar-implementation
description: Implement JAYA's 40 canonical pillars and validated dynamic extensions in construction order. Covers import paths, contract/doc sync, persistence, and runtime integration.
trigger: "Implement next canonical pillar" or "elevate pillar maturity" in JAYA project
category: software-development
---

# JAYA Canonical Pillar Implementation

## Trigger Conditions
- User says "Next canonical item per construction order: Pillar X"
- User says "lanjutkan" (continue) during pillar implementation
- Working in JAYA monorepo with Recovery Mode active

## Core Principles (RECOVERY MODE - Active since 19 Aug 2026)
- **NO new roadmap, NO architecture rewrite, NO pillar renaming, NO mass refactor, NO force push**
- **40 Pilar Contract**: ID dan nama baseline P001-P040 tetap stabil; extension P041+ masuk melalui manifest tervalidasi dan dynamic registry.
- **Construction Order**: Strict per `docs/pillars/README.md` — must follow canonical sequence
- **Authority Order**: User → AGENTS.md → Arsitektur kanonis (ARCHITECTURE.md, 40_pilar.md, 40_pillars.yaml) → Implementation truth (STATUS.md, matrix) → Construction order → Module docs → Source code
- **Module Ownership**: JAYA_CORE owns model, reasoning, planning, memory, JayaIR, pillar runtime, capability registry

## Workflow: Per-Pillar Implementation

### 1. READ CANONICAL DOCS
```bash
read_file(path="docs/pillars/README.md")           # Construction order
read_file(path="packages/jaya-core/src/jaya_core/contracts/40_pillars.yaml")  # Contract status
read_file(path="docs/40_PILLARS_IMPLEMENTATION_MATRIX.md")  # Implementation evidence
read_file(path="docs/pillars/{NN}-p{ID}-{name}.md")  # Pillar-specific doc
```

### 2. RECONSTRUCT STATE
- Check current status in 40_pillars.yaml (NOT_IMPLEMENTED, PROTOTYPE, IMPLEMENTED_LOCAL, INTEGRATED, VERIFIED, PRODUCTION)
- Search for existing implementation: `search_files(pattern="pillar_name|ClassName", target="content")`
- Most pillars already have production code — only need validation + doc updates

### 3. LOCATE UNFINISHED → INSPECT CODE
```bash
# Find implementation files
search_files(pattern="pillar_keyword", path="packages/jaya-core/src/jaya_core", target="files")
read_file(path="packages/jaya-core/src/jaya_core/.../implementation.py")
read_file(path="packages/jaya-core/tests/test_*.py")  # Check existing tests
```

### 4. MINIMAL CHANGE — Update Contracts & Docs
**Key files to patch (in order):**
1. `packages/jaya-core/src/jaya_core/contracts/40_pillars.yaml` — baseline status and ownership
2. `docs/40_PILLARS_IMPLEMENTATION_MATRIX.md` — Update pillar entry with file paths, status, evidence
3. `docs/pillars/{NN}-p{ID}-{name}.md` — Update status line
4. `docs/pillars/README.md` — Update construction index table (both `||` and `|` pipe formats)

**Matrix status summary line** (always update):
```text
Ringkasan audit: {V} VERIFIED, {I} INTEGRATED, {L} IMPLEMENTED_LOCAL, {P} PROTOTYPE, {N} NOT_IMPLEMENTED, {PR} PRODUCTION
```

### 5. REAL VALIDATION
```bash
python scripts/validate_docs.py
python .github/tools/repo_layout_audit.py --fail-on-violations
```
**Must PASS both** before continuing.

### 6. UPDATE STATUS → CONTINUE
- Commit changes (no force push, no hard reset)
- Move to next pillar in construction order

## Common Patterns & Pitfalls

### Import Path Fixing (Monorepo)
**Problem**: Legacy modules may import `src.*` or uppercase folder namespaces.
**Fix**: Batch replace across all Python files:
```python
# In runtime.py, nano_artifact.py, nano_inference.py, etc.
# from src.brain_v2. → from jaya_core.brain_v2.
# from brain_v2. → from jaya_core.brain_v2.
```
**Affected files typically**: `runtime.py`, `nano_artifact.py`, `nano_inference.py`, and any file importing from sibling modules.

### Matrix File Corruption Recovery
**Problem**: `40_PILLARS_IMPLEMENTATION_MATRIX.md` gets truncated during patch operations
**Fix**: 
```bash
git checkout docs/40_PILLARS_IMPLEMENTATION_MATRIX.md
# Then apply patches carefully with exact context
```

### Layer Corrections
**Common**: Pillars marked `layer: TRANSCENDENTAL` in contracts but should be `IRON_ENGINE` (or vice versa per ARCHITECTURE.md)
**Fix**: Update both contract entries (some pillars appear twice in 40_pillars.yaml)

### Validation Debugging
```bash
# Debug validate_docs.py failures
python -c "
import yaml
with open('packages/jaya-core/src/jaya_core/contracts/40_pillars.yaml') as f:
    data = yaml.safe_load(f)
for p in data:
    print(f'{p[\"id\"]:2d} | {p[\"name\"]:30s} | {p[\"status\"]}')
"
```

## Phase Gates

### Phase 1: PROTOTYPE → IMPLEMENTED_LOCAL
- Pillars with production code but marked PROTOTYPE
- Update contracts/docs only — no new code needed
- Run validators

### Phase 2: IMPLEMENTED_LOCAL → INTEGRATED
- Wire all IMPLEMENTED_LOCAL pillars into `IronEngine.runtime`
- Fix import paths (`src.brain_v2` → `jaya_core.brain_v2`)
- Create integration test under `packages/jaya-core/tests/integration/`
- Test each pillar's runtime attribute: `engine._pillar_name`

### Phase 3: INTEGRATED → VERIFIED
- Add failure-path tests, persistence tests, contract tests
- Deterministic test suites

### Phase 4: NOT_IMPLEMENTED → IMPLEMENTED_LOCAL
- Implement missing pillars (6, 7, 10, 17, 31)
- Full implementation + tests + docs

## Key Files Reference
| File | Purpose |
|------|---------|
| `docs/pillars/README.md` | Construction order (40 rows, `||` and `|` tables) |
| `packages/jaya-core/src/jaya_core/contracts/40_pillars.yaml` | Canonical baseline for P001-P040 |
| `docs/40_PILLARS_IMPLEMENTATION_MATRIX.md` | Human-readable audit with evidence |
| `docs/pillars/{NN}-p{ID}-{name}.md` | Per-pillar detail |
| `scripts/validate_docs.py` | Validator — checks sync between matrix and contracts |
| `.github/tools/repo_layout_audit.py` | Layout auditor — checks module boundaries |

## Testing Commands
```bash
# Run integration test (requires venv)
PYTHONPATH=packages/jaya-core/src .venv-research/Scripts/python.exe -c "
from jaya_core.brain_v2.engine.runtime import IronEngine
# ... test each pillar attribute
"

# Run validators
python scripts/validate_docs.py
python .github/tools/repo_layout_audit.py --fail-on-violations
```

## Gotchas from This Session
1. **Runtime import fix**: gunakan namespace package `jaya_core`; lazy imports tetap memakai path package penuh.
2. **AgenticRAG seed method**: `_seed_default_local_knowledge()` exists but called before definition — comment out or move method up
3. **Matrix dual-table format**: README.md has BOTH `||` (markdown) and `|` (pipe) tables — update both
4. **Dynamic extension**: jangan mengubah ID P001-P040; daftarkan P041+ melalui manifest extension dan audit registry.
5. **Source layout**: gunakan editable install atau `packages/jaya-core/src` pada PYTHONPATH.
