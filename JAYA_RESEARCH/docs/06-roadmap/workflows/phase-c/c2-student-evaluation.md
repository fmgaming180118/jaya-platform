# Workflow C.2 — Evaluasi & Validasi Student Model

> **Fase:** [C — Distillation & Edge](../../phase-c-distillation-edge.md)  
> **Estimasi:** 1 minggu  
> **Prasyarat:** [C.1 Dataset Expansion](c1-dataset-expansion.md)  
> **Tujuan:** Melatih ulang student model, mengevaluasi pada holdout, dan mempromosikan hanya jika lolos gate JAYA_CORE.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `JAYA_RESEARCH/scripts/train_distilled_student.py` | Training |
| `JAYA_CORE/scripts/promote_student.py` | Evolution gate |
| `JAYA_CORE/scripts/build_student_manifest.py` | Signed manifest |
| `JAYA_CORE/evolution/candidates/` | Candidate & decision JSON |
| `JAYA_CORE/evolution_gate.py` | ACCEPT/REJECT logic |

---

## Checklist Training

### 1. Training Run
- [ ] Train dengan `train.jsonl` dari C.1
- [ ] Base model: `Qwen/Qwen2.5-0.5B-Instruct` (atau versi terbaru terdokumentasi)
- [ ] LoRA r=8, alpha=16 (konsisten dengan registry existing)
- [ ] Checkpoint setiap N steps; simpan best by eval loss
- [ ] Log: `training_report.json` dengan hyperparameters & loss curve

### 2. Holdout Evaluation
- [ ] Script eval: generate pada `holdout.jsonl` tanpa teacher
- [ ] Metrik: BLEU/ROUGE (opsional), exact match partial, LLM-as-judge (Nemotron)
- [ ] Bandingkan vs base model tanpa adapter
- [ ] Target: gain ≥50% vs base pada metrik utama
- [ ] Simpan: `evolution/candidates/{id}_eval.json`

### 3. Resource Check
- [ ] RAM delta ≤ threshold gate (cek `evolution_gate.py`)
- [ ] CPU delta ≤ threshold
- [ ] Inference smoke test <3s untuk prompt 128 token (CPU)

---

## Checklist Promotion (JAYA_CORE)

### 1. Candidate Package
- [ ] Generate `evolution/candidates/distilled-student-qwen-0.5b-v2.json` (atau versi baru)
- [ ] Jalankan `promote_student.py` → decision file
- [ ] Decision harus `ACCEPT` — jika `REJECT`, dokumentasikan alasan & iterasi

### 2. Manifest & Deploy
- [ ] `build_student_manifest.py` → signed manifest HMAC
- [ ] `deploy_student.py` → copy ke `data/policies/`
- [ ] Update `registry.json` dengan entry baru
- [ ] `merge_student_adapter.py` → merged safetensors

### 3. GGUF Conversion
- [ ] `phase4_gguf_convert.py` → f16, q8_0
- [ ] Quantisasi q4_k_m: WSL atau pre-built `llama-quantize` di Windows
- [ ] Update `deploy_manifest.json` di `data/edge_deploy/`

---

## Checklist Dokumentasi

- [ ] Decision log: observed vs expected perf gain
- [ ] Catat perbedaan v1 (44 sample) vs v2 (500+ sample)
- [ ] Update manifest metadata: `distillation_samples`, `epochs`

---

## Kriteria Selesai Workflow C.2

- [ ] Holdout eval gain ≥50% vs base
- [ ] `ACCEPT` dari evolution gate
- [ ] GGUF q8_0 terdeploy dan bisa di-load Ollama/llama.cpp
- [ ] Registry memuat policy student versi baru (atau v1 di-update dengan dokumentasi)

---

## Verifikasi

```bash
python JAYA_CORE/scripts/promote_student.py --candidate evolution/candidates/distilled-student-qwen-0.5b-v2.json
python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate
# Manual: ollama run <gguf-model> "Jelaskan apa itu RAG"
```

---

**Sebelumnya:** [C.1](c1-dataset-expansion.md) · **Berikutnya:** [C.3 Local Integration](c3-local-student-integration.md)
