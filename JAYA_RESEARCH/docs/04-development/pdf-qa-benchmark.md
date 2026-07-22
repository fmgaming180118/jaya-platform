# Benchmark PDF QA — Evolusi Akurasi v1 ke v6

Dokumen ini mencatat hasil pengujian sistem Question-Answering (QA) JAYA Research terhadap dokumen akademik (Tugas Akhir/Skripsi).

---

## Ringkasan Hasil

| Versi | Metode | Akurasi Estimasi | Keterangan |
|---|---|---|---|
| **v1** | BM25 + Nano-8b | ~35% | Baseline, keyword search murni |
| **v2** | BM25 + 70b | ~45% | Model lebih besar, retrieval sama |
| **v3** | FAISS + 70b | ~55% | Semantic search, lebih relevan |
| **v4** | Page-FAISS | ~85% | Index per halaman, presisi meningkat |
| **v5** | Clean-Embed | ~90% | Text cleaning sebelum embed |
| **v6** | Enhanced RAG (Workspace) | ~60% | ⚠️ Regresi karena workspace isolation baru |

> [!WARNING]
> v6 mengalami regresi karena perubahan arsitektur workspace isolation yang memecah index. Perlu investigasi lebih lanjut.

---

## Detail Setiap Versi

### v1 — BM25 + Nano-8b (Baseline)
- **Retrieval:** BM25 (keyword matching)
- **LLM:** Model kecil 8B parameter
- **Masalah:** BM25 tidak paham semantik, sering miss dokumen relevan
- **Skor:** ~35%

### v2 — BM25 + 70b
- **Perubahan:** Upgrade LLM ke 70B
- **Retrieval:** Masih BM25
- **Temuan:** LLM lebih besar tidak kompensasi retrieval yang buruk
- **Skor:** ~45%

### v3 — FAISS + 70b
- **Perubahan:** Ganti BM25 dengan FAISS + NVIDIA embedding
- **Temuan:** Lompatan besar — semantic search jauh lebih relevan
- **Skor:** ~55%

### v4 — Page-FAISS
- **Perubahan:** Index dibuat per halaman PDF (bukan per chunk acak)
- **Temuan:** Presisi meningkat drastis karena preserves page boundary
- **Skor:** ~85%

### v5 — Clean-Embed
- **Perubahan:** Pipeline cleaning teks sebelum embedding
  - Hapus header/footer berulang
  - Normalize whitespace
  - Hapus noise OCR
- **Temuan:** Embedding lebih bersih → similarity lebih akurat
- **Skor:** ~90%

### v6 — Enhanced RAG (Workspace Isolation)
- **Perubahan:** Arsitektur workspace isolation (multi-user)
- **Masalah:** Vector store terpecah per workspace, query tidak bisa cross-workspace
- **Skor:** ~60% (regresi)
- **Status:** 🔧 Perlu perbaikan — pertimbangkan shared index + workspace filter

---

## Rekomendasi ke Depan

1. **Fix v6 regresi** — gunakan single index dengan metadata filter per workspace
2. **Tambah reranker** — NVIDIA llama-nemotron-rerank untuk re-sort results
3. **Multimodal** — embed tabel dan gambar dari PDF (via nv-ingest)
4. **Evaluasi formal** — buat test set dengan ground truth dari dokumen TA asli

---

## Cara Reproduksi Test

```bash
# Test QA v5
python test_qa_v5_jaya.py

# Test QA terbaru
python test_qa_v6_jaya.py

# Test ingest PDF
python test_pdf_ingest_ta.py
```

File test tersedia di root direktori `JAYA_RESEARCH/`.
