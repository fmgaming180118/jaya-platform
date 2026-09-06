---
name: canonical-model-architecture
description: Manage canonical model architecture to prevent duplicate/conflicting architectures and establish single source of truth for training pipelines
category: mlops
---

# Canonical Model Architecture Management

**Trigger**: When a project has duplicate/conflicting model architectures (e.g., `JayaModel` vs `JayaLibrarianNativeV0`) and needs to establish a single canonical architecture with unified training pipeline.

## ⚠️ GOVERNANCE PRECONDITION (MANDATORY)

**This skill is SUBORDINATE to the JAYA repository's canonical governance:**

1. **Root `AGENTS.md` wins** — This skill cannot override any rule in `AGENTS.md`
2. **Canonical JAYA docs win** — `docs/ARCHITECTURE.md`, `docs/arsitektur_40_pilar_jaya.md`, `JAYA_CORE/contracts/40_pillars.yaml` are authoritative
3. **No autonomous redesign** — This skill cannot delete/replace model architecture from generic heuristics
4. **Explicit activation only** — This skill activates ONLY for explicit model-architecture reconciliation tasks requested by the user
5. **No repository-wide redesign** — This skill cannot create a repository-wide redesign

**If a skill instruction conflicts with JAYA repository governance, IGNORE THE SKILL and report the conflict.**

---

## Principles

1. **Single Canonical Architecture**: Only ONE model class should exist for a given model family. All training/inference scripts must use this canonical class.
2. **Strict Loading**: Always use `load_state_dict(state_dict, strict=True)` to catch architecture mismatches immediately.
3. **Config Identity Consistency**: `model_type`, `architectures`, and `architecture` fields must match the canonical class name across all config files.
4. **Single Source of Truth**: `model_config.json` (or equivalent) is the authoritative config; all other configs derive from it.
5. **Artifact Verification**: SHA-256 hash in manifest must match actual weights file.

## Phase A: Architecture Unification

### Step 1: Identify & Remove Duplicate Architecture
```bash
# Find duplicate model classes
grep -rn "class.*Model" src/model/
# Remove the non-canonical one
rm src/model/jaya_model.py  # or whichever is non-canonical
```

### Step 2: Update All Training Scripts
- Update `pretrain.py`, `instruction_tune.py`, `merge_and_gguf*.py` to import and use the canonical class
- Change `load_state_dict(state_dict, strict=False)` → `strict=True`
- Update imports: `from model.jaya_model import JayaModel` → `from model.native_architecture import JayaLibrarianNativeV0`

### Step 3: Fix Config Identity
```json
// config.json (HF-compatible)
{
  "architecture": "canonical_architecture_name",
  "model_type": "canonical_type",
  "architectures": ["CanonicalClassName"]
}

// model_config.json (Single Source of Truth)
{
  "architecture": "canonical_architecture_name",
  "vocab_size": 49152,
  "d_model": 128,
  "n_layers": 4,
  "n_heads": 4
}
```

### Step 4: Verify Checkpoint Compatibility
```python
# Test strict loading
model = CanonicalModel(config)
state_dict = load_file("model.safetensors")
model.load_state_dict(state_dict, strict=True)  # Must succeed
```

## Phase B: Pipeline Verification

1. **Pretrain from scratch** → valid checkpoint
2. **Continued pretrain** with `strict=True` → weight continuity verified
3. **Instruction tuning** (LoRA) on same base architecture
5. **Merge → GGUF → runtime test** end-to-end

## Phase C: Documentation Canonical

| File | Role |
|------|------|
| `model_config.json` | Single source of truth for architecture config |
| `config.json` | HF-compatible identity (model_type, architectures) |
| `training_manifest.json` | Artifact SHA-256, training metadata |
| `README.md` | Canonical architecture section with pipeline docs |

## Common Pitfalls

| Pitfall | Prevention |
|---------|------------|
| `strict=False` masks weight mismatches | Always use `strict=True`; fix architecture if it fails |
| Duplicate model classes (`JayaModel` + `JayaLibrarianNativeV0`) | Enforce single canonical class; delete duplicates |
| Config identity drift (`GPT2LMHeadModel` vs `JayaLibrarianNativeV0`) | Automate config generation from `model_config.json` |
| LoRA target modules mismatch (`c_attn` vs `q_proj`) | Update `target_modules` for canonical architecture |
| Tokenizer-model vocab mismatch | Ensure `vocab_size` matches tokenizer in `model_config.json` |

## LoRA Target Modules by Architecture

| Architecture | Target Modules |
|--------------|----------------|
| `JayaLibrarianNativeV0` | `["c_attn", "c_proj", "w1", "w2", "w3"]` |
| `GPT2` | `["c_attn", "c_proj", "c_fc", "c_proj"]` |
| `Llama` | `["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]` |

## Verification Checklist

- [ ] Only ONE model class file exists in `src/model/`
- [ ] All scripts import canonical class
- [ ] All `load_state_dict(..., strict=True)` succeed
- [ ] `config.json` has correct `model_type` and `architectures`
- [ ] `model_config.json` matches actual model params
- [ ] `training_manifest.json` SHA-256 matches `model.safetensors`
- [ ] LoRA `target_modules` match canonical architecture
- [ ] `README.md` documents canonical architecture and pipeline

## Support Files

- `references/architecture-comparison.md` — Side-by-side comparison of old vs new architecture
- `templates/model_config.json.template` — Template for new model configs
- `scripts/verify_canonical_architecture.py` — Verification script for CI

## Related Skills

- `huggingface-hub` — For model/config upload/download
- `llama-cpp` — For GGUF conversion
- `training-small-transformers` — For training patterns