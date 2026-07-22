# Fase C — Checklist Eksekusi (Checkbox-Ready)

> **Cara pakai:** Copy ke GitHub Issues / Notion / Obsidian. Centang `[ ]` → `[x]` saat selesai.  
> **Konvensi:** `☐` = belum, `☑` = selesai, `⏳` = in progress, `🚫` = blocked.

---

## C.1 — Dataset Distillation v2 (500–1000 samples)

| ID | Task | Assignee | Est. | Status | Notes / Blocker |
|----|------|----------|------|--------|-----------------|
| C.1.1 | Design dataset v2 schema (`schema.json`) | | 0.5d | ☐ | `data/distill/v2/schema.json` |
| C.1.2 | `generate_distill_data.py` — NIM prompts (QA, reasoning, coding, academic) | | 1.5d | ☐ | Target 200 sampel/jam |
| C.1.3 | `generate_local_distill.py` — Ollama fallback | | 1d | ☐ | Same output format |
| C.1.4 | `thesis_to_qa.py` — anonymize thesis PDF → QA pairs | | 1.5d | ☐ | 50+ thesis → 200+ QA |
| C.1.5 | `filter_distill_data.py` — LLM-as-judge ≥7/10, dedup sim<0.9 | | 1d | ☐ | Clean 500–1000 |
| C.1.6 | Split train/val/test 80/10/10 stratified | | 0.5d | ☐ | `train/val/test.jsonl` |
| C.1.7 | DVC/Git LFS versioning + SHA256 manifest | | 0.5d | ☐ | `dvc push` / `git lfs` |

---

## C.2 — Training Pipeline (QLoRA + KD)

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| C.2.1 | Refactor `train_distill.py` — multi-stage SFT → KD → DPO | | 2d | ☐ | Config-driven |
| C.2.2 | Config models: student Qwen2.5-0.5B, teacher Qwen3-4B adapter | | 0.5d | ☐ | `configs/train_distill.yaml` |
| C.2.3 | QLoRA config: 4-bit NF4, r=64, alpha=16, all-linear | | 0.5d | ☐ | VRAM < 6GB |
| C.2.4 | KD loss: α*CE + (1-α)*KL(logits_t || logits_s) | | 1d | ☐ | `src/training/distill_loss.py` |
| C.2.5 | Training loop: grad accum, checkpointing, wandb | | 1.5d | ☐ | 3 epoch, log step 10 |
| C.2.6 | Checkpoint callback: best val loss + last | | 0.5d | ☐ | `adapter_best/`, `adapter_last/` |
| C.2.7 | Merge adapter → FP16 `merged_model/` | | 0.5d | ☐ | `merge_adapter.py` |

---

## C.3 — GGUF Conversion & Quantization (q4_k_m < 300 MB)

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| C.3.1 | Setup llama.cpp Windows (WSL2/CMake) or pre-built | | 1d | ☐ | `llama-quantize` works |
| C.3.2 | Convert FP16 → GGUF f16 (`convert_gguf.py`) | | 0.5d | ☐ | ~950 MB |
| C.3.3 | Quantize all: q8_0, q6_k, q5_k_m, q4_k_m, q3_k_m | | 1d | ☐ | `quantize_all.sh` |
| C.3.4 | Benchmark perplexity + latency each quant | | 1d | ☐ | CSV + plot |
| C.3.5 | Select q4_k_m default (size<300MB, ppl delta<5%) | | 0.5d | ☐ | Document decision |
| C.3.6 | Copy to `JAYA_CORE/models/student-q4_k_m.gguf` + update `registry.json` | | 0.25d | ☐ | Entry `distilled-student-qwen-0.5b-v2` |

---

## C.4 — Holdout Evaluation & Regression Gate

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| C.4.1 | Holdout eval: MT-Bench, MMLU, Custom Academic QA (1000 samples) | | 1.5d | ☐ | `eval_holdout.py` |
| C.4.2 | Compare v2 vs v1 vs baseline Qwen2.5-0.5B | | 1d | ☐ | `eval_comparison_v1_v2.md` |
| C.4.3 | Regression gate: v2 ≥ v1 all academic metrics | | 0.5d | ☐ | `test_phase2_distill_gate.py` |
| C.4.4 | Latency/memory bench on target laptop (16GB, no GPU) | | 1d | ☐ | `bench_edge.py` |
| C.4.5 | Manifest HMAC-SHA256 for v2 | | 0.5d | ☐ | `build_manifest.py` |

---

## C.5 — Hybrid Router (Local ↔ Cloud)

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| C.5.1 | Design router policy doc (`router_policy.md`) | | 0.5d | ☐ | Heuristic + learned |
| C.5.2 | Implement `HybridRouter` in `brain_v2/router.py` | | 1d | ☐ | Unit test |
| C.5.3 | Local backend: `llama-cpp-python` load GGUF | | 1d | ☐ | `local_backend.py` |
| C.5.4 | Cloud backend: reuse `teacher.py` NIM API | | 0.5d | ☐ | `cloud_backend.py` |
| C.5.5 | Fallback chain: local → cloud → cached | | 0.5d | ☐ | Resilience test |
| C.5.6 | Expose via JayaIR `ROUTE` opcode + CLI `--auto` | | 0.5d | ☐ | `jaya_chat_cli.py` |

---

## C.6 — Integration JAYA_RESEARCH ↔ JAYA_CORE

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| C.6.1 | Chat endpoint `model=local|cloud|auto` param | | 0.5d | ☐ | `research_api.py` |
| C.6.2 | LAN sync script `sync_model.sh` (rsync/HTTP) | | 0.5d | ☐ | |
| C.6.3 | React UI "Local Mode" toggle + offline indicator | | 1d | ☐ | `ChatToggle.tsx` |

---

## C.7 — Documentation & Changelog

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| C.7.1 | Update this CHECKLIST.md final | | 0.25d | ☐ | All ☑ |
| C.7.2 | Update root `CHANGELOG.md` Phase C | | 0.25d | ☐ | |
| C.7.3 | Update `JAYA_CORE/README.md` — student specs, router | | 0.25d | ☐ | |
| C.7.4 | Update `JAYA_RESEARCH/README.md` — hybrid mode | | 0.25d | ☐ | |

---

## Exit Criteria Verification (Final Gate)

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| EC1 | All C.1–C.7 tasks ☑ | | | ☐ |
| EC2 | `pytest JAYA_CORE/tests/test_phase2_distill_gate.py -v` PASS | | | ☐ |
| EC3 | Student q4_k_m < 300 MB, load < 2s on 16GB RAM laptop | | | ☐ |
| EC4 | Hybrid router: local works offline (WiFi off), cloud fallback online | | | ☐ |
| EC5 | Holdout eval: v2 ≥ v1 on academic QA, MT-Bench, MMLU subset | | | ☐ |
| EC6 | JAYA_RESEARCH chat `model=auto` routes to local when offline | | | ☐ |
| EC7 | Manifest v2 signed, registry.json updated, GGUF in `JAYA_CORE/models/` | | | ☐ |
| EC8 | Docs complete: train, quantize, run local, router policy | | | ☐ |

---

## Blocker / Risk Log

| Date | Risk | Likelihood | Impact | Mitigation |
|------|------|------------|--------|------------|
| | llama.cpp build Windows fails | High | High | WSL2 / pre-built / GitHub Actions CI |
| | Dataset quality low → overfit | Medium | High | LLM-as-judge strict, human review 10% |
| | KD loss not converging | Medium | Medium | Tune α, temp, check teacher logits |
| | q4_k_m degrades too much | Low | High | Fallback q5_k_m (~350 MB) |

---

## Daily Standup Notes (Append-only)

```
YYYY-MM-DD: 
- Done: 
- Doing: 
- Blockers: 
```

---

> **Next Phase:** Setelah semua EC ☑ → [Fase D Checklist](../phase-D/CHECKLIST.md)