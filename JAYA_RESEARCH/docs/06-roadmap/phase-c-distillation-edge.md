# Fase C — Distillation & Edge

> **Estimasi:** ~1 bulan  
> **Prasyarat:** [Fase B selesai](phase-b-production-readiness.md), akses GPU untuk training (min. 8GB VRAM)  
> **Tujuan:** Memperkuat pipeline teacher→student, memvalidasi model edge, dan mengintegrasikan student model lokal sebagai fallback di JAYA_RESEARCH.

---

## Konteks Masalah

| Area | Kondisi saat ini | Target Fase C |
|------|------------------|---------------|
| Dataset distilasi | 44 sampel, 3 epoch | ≥500 sampel, eval holdout |
| Student model | ACCEPT +132% (mungkin overfit) | Validasi independen |
| GGUF edge | q8_0 & f16 ada; q4_k_m pending | Quantisasi lengkap |
| JAYA_RESEARCH runtime | 100% cloud NIM | Router: query ringan → student lokal |
| Registry | 2 policy aktif di JAYA_CORE | Terdokumentasi & teruji end-to-end |

---

## Workflow Anak

| ID | Nama | Dokumen | Bergantung pada |
|----|------|---------|-----------------|
| **C.1** | Dataset Expansion | [c1-dataset-expansion.md](workflows/phase-c/c1-dataset-expansion.md) | — |
| **C.2** | Student Evaluation | [c2-student-evaluation.md](workflows/phase-c/c2-student-evaluation.md) | C.1 |
| **C.3** | Local Student Integration | [c3-local-student-integration.md](workflows/phase-c/c3-local-student-integration.md) | C.2 |

**Urutan:** C.1 → C.2 → C.3 (sequential).

---

## Master Checklist Fase C

### C.1 — Dataset Expansion
- [ ] Semua item di [c1-dataset-expansion.md](workflows/phase-c/c1-dataset-expansion.md) selesai
- [ ] Dataset JSONL ≥500 pasangan instruction-response

### C.2 — Student Evaluation
- [ ] Semua item di [c2-student-evaluation.md](workflows/phase-c/c2-student-evaluation.md) selesai
- [ ] Holdout eval menunjukkan gain ≥50% vs baseline (bukan hanya train set)

### C.3 — Local Student Integration
- [ ] Semua item di [c3-local-student-integration.md](workflows/phase-c/c3-local-student-integration.md) selesai
- [ ] Chat sederhana bisa dijawab student GGUF tanpa NIM

### Verifikasi Integrasi Fase
- [ ] Pipeline penuh: distill → promote → manifest → deploy → GGUF → inference lokal
- [ ] `registry.json` memuat policy student versi baru (jika di-promote)
- [ ] Fallback lokal aktif saat `NVIDIA_API_KEY` tidak tersedia (mode degraded)
- [ ] Dokumen `qlora-pipeline.md` dan research notes diperbarui

---

## Kriteria Selesai Fase C

Fase C **selesai** jika:

1. **Dataset** distilasi ≥500 sampel dengan dokumentasi sumber & lisensi.
2. **Evaluasi holdout** terdokumentasi di `JAYA_CORE/evolution/candidates/`.
3. **Student GGUF** bisa dijalankan via Ollama/llama.cpp di mesin tanpa GPU cloud.
4. **JAYA_RESEARCH** memiliki config `LOCAL_STUDENT_ENABLED=true` yang berfungsi.

---

## File Utama yang Terdampak

```
JAYA_RESEARCH/training/nim_distillation/distill_via_nim.py
JAYA_RESEARCH/scripts/train_distilled_student.py
JAYA_RESEARCH/scripts/prepare_distillation_data.py
JAYA_CORE/scripts/promote_student.py
JAYA_CORE/scripts/deploy_student.py
JAYA_CORE/scripts/phase4_gguf_convert.py
JAYA_CORE/data/policies/registry.json
JAYA_RESEARCH/src/teacher.py                         ← router / fallback
```

---

## Metrik Keberhasilan

| Metrik | Target |
|--------|--------|
| Dataset size | ≥500 sampel |
| Holdout accuracy gain | ≥50% vs Qwen2.5-0.5B base |
| Edge model size (q4) | <350 MB |
| Local inference latency (p50) | <3 detik (prompt pendek, CPU) |

---

**Sebelumnya:** [Fase B](phase-b-production-readiness.md) · **Selanjutnya:** [Fase D →](phase-d-ecosystem-bridge.md)
