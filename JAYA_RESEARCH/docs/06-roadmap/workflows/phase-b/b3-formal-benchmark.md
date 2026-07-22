# Workflow B.3 — Benchmark & Evaluasi Formal PDF QA

> **Fase:** [B — Production Readiness](../../phase-b-production-readiness.md)  
> **Estimasi:** 4–5 hari  
> **Prasyarat:** [Fase A selesai](../../phase-a-rag-foundation.md) (dapat paralel dengan B.1)  
> **Tujuan:** Test suite otomatis dengan ground truth untuk mengukur akurasi RAG dan mencegah regresi (target ≥85%).

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `tests/benchmark_pdf_qa/` | Test suite baru |
| `tests/Tugas Akhir - FACHRI FAHIRA PRANAJAYA.pdf` | Dokumen evaluasi |
| `docs/04-development/pdf-qa-benchmark.md` | Dokumentasi hasil |
| `docs/04-development/testing.md` | Cara menjalankan |

---

## Desain Test Set

### Format ground truth (`tests/benchmark_pdf_qa/ground_truth.json`)

```json
[
  {
    "id": "q01",
    "question": "Siapa nama penulis tugas akhir?",
    "expected_contains": ["Fachri", "Fahira"],
    "page_hint": 1
  }
]
```

- [ ] Minimal **20 pertanyaan** dari PDF TA asli
- [ ] Campuran: factual (nama, judul), metodologi, hasil, kesimpulan
- [ ] Field `expected_contains` — substring yang wajib ada di jawaban LLM
- [ ] Field opsional `expected_not_contains` — halusinasi umum

---

## Checklist Implementasi

### 1. Harness Evaluasi
- [ ] Script `tests/benchmark_pdf_qa/run_benchmark.py`
- [ ] Flow: ingest PDF → untuk setiap Q: RAG retrieve + LLM answer → score
- [ ] Metrik: `accuracy_strict` (all contains match), `accuracy_loose` (any match)
- [ ] Output JSON: `results/benchmark_YYYYMMDD.json`
- [ ] Exit code non-zero jika accuracy < threshold

### 2. Restore Test Files
- [ ] Port logic dari `test_qa_v5_jaya.py` / `test_qa_v6_jaya.py` (dihapus di git) ke harness baru
- [ ] Atau tulis ulang berdasarkan `pdf-qa-benchmark.md`

### 3. CI Integration (lokal)
- [ ] Tambah ke `docs/04-development/testing.md`
- [ ] Script `scripts/run_qa_benchmark.sh` / `.cmd`
- [ ] Threshold default: 85% strict (configurable `--min-accuracy`)

### 4. Resilience External APIs (bonus dalam workflow ini)
- [ ] `literature.py`: retry 3x + exponential backoff untuk ArXiv/Scholar
- [ ] Circuit breaker sederhana setelah 5 failure berturut-turut
- [ ] **Perbaiki SSL:** ganti `CERT_NONE` dengan verify proper atau certifi bundle

### 5. Dokumentasi Hasil
- [ ] Update `pdf-qa-benchmark.md` dengan entri **v7 — Post Fase A/B**
- [ ] Catat metode, akurasi, tanggal, commit hash

---

## Checklist Testing

- [ ] Benchmark berjalan headless tanpa UI
- [ ] Reproducible: 2 run berturut-turut variance <5%
- [ ] Fail jelas jika `NVIDIA_API_KEY` tidak ada
- [ ] Ground truth tidak commit data sensitif (anonimisasi jika perlu)

---

## Kriteria Selesai Workflow B.3

- [ ] `accuracy_strict ≥ 85%` pada test set 20 pertanyaan
- [ ] Harness bisa dijalankan satu perintah
- [ ] `pdf-qa-benchmark.md` terupdate dengan hasil v7

---

## Verifikasi

```bash
cd JAYA_RESEARCH
python tests/benchmark_pdf_qa/run_benchmark.py \
  --pdf "tests/Tugas Akhir - FACHRI FAHIRA PRANAJAYA.pdf" \
  --ground-truth tests/benchmark_pdf_qa/ground_truth.json \
  --min-accuracy 0.85
```

---

**Fase induk:** [phase-b-production-readiness.md](../../phase-b-production-readiness.md)
