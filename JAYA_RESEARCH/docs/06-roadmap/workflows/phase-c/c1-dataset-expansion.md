# Workflow C.1 — Perluasan Dataset Distilasi

> **Fase:** [C — Distillation & Edge](../../phase-c-distillation-edge.md)  
> **Estimasi:** 1–2 minggu  
> **Tujuan:** Memperbesar dataset distilasi dari 44 sampel menjadi ≥500 sampel berkualitas dari berbagai sumber.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `JAYA_RESEARCH/scripts/prepare_distillation_data.py` | Generator dataset |
| `JAYA_RESEARCH/training/nim_distillation/distill_via_nim.py` | Teacher Nemotron |
| `JAYA_RESEARCH/src/training/build_qlora_dataset_from_ollama.py` | Teacher Ollama |
| `distilled_nemotron.json`, `test_nemotron.jsonl` | Data existing |

---

## Sumber Data Target

| Sumber | Target jumlah | Catatan |
|--------|---------------|---------|
| Nemotron NIM (teacher) | 300+ | Instruction-response akademik |
| Ollama qwen3:4b | 100+ | Gaya bahasa Indonesia |
| Thesis anonymized chunks | 50+ | Q&A dari PDF TA (dengan izin) |
| Research reports JAYA | 50+ | Output autonomous research |

---

## Checklist Implementasi

### 1. Schema Dataset Standar
- [ ] Format JSONL: `{instruction, input, output, source, metadata}`
- [ ] Validasi schema di `prepare_distillation_data.py`
- [ ] Dedup berdasarkan hash `(instruction + input)`

### 2. Generator Nemotron
- [ ] Template prompt untuk kategori: ringkasan paper, metodologi, novelty, gap, defense Q&A
- [ ] Batch generation dengan rate limit & resume (checkpoint file)
- [ ] Log biaya/token per batch
- [ ] Output: `data/distillation/nemotron_v2.jsonl`

### 3. Generator Ollama
- [ ] Jalankan `build_qlora_dataset_from_ollama.py` dengan `--variants-per-key 12`
- [ ] Merge ke dataset utama dengan tag `source: ollama`

### 4. Generator dari Thesis (opsional, sensitif)
- [ ] Ekstrak chunk + generate Q&A via teacher
- [ ] Anonimisasi nama/NIM/institusi
- [ ] Dokumentasi lisensi/persetujuan di `data/distillation/README.md`

### 5. Quality Filter
- [ ] Hapus sample dengan output < 50 karakter
- [ ] Hapus sample duplikat semantik (cosine > 0.95)
- [ ] Manual review 5% random sample

### 6. Split Train/Holdout
- [ ] 90% train / 10% holdout — stratified by source
- [ ] File: `train.jsonl`, `holdout.jsonl`
- [ ] Holdout **tidak** dipakai saat training

---

## Checklist Dokumentasi

- [ ] `data/distillation/README.md` — sumber, tanggal, jumlah, lisensi
- [ ] Update `docs/05-research-notes/qlora-pipeline.md` dengan langkah dataset v2

---

## Kriteria Selesai Workflow C.1

- [ ] `train.jsonl` ≥ 500 baris valid
- [ ] `holdout.jsonl` ≥ 50 baris
- [ ] Dedup rate dan filter stats terdokumentasi
- [ ] Reproducible: script satu perintah dari raw → train/holdout

---

## Verifikasi

```bash
wc -l JAYA_RESEARCH/data/distillation/train.jsonl
python JAYA_RESEARCH/scripts/prepare_distillation_data.py --validate-only
```

---

**Fase induk:** [phase-c-distillation-edge.md](../../phase-c-distillation-edge.md) · **Berikutnya:** [C.2 Student Evaluation](c2-student-evaluation.md)
