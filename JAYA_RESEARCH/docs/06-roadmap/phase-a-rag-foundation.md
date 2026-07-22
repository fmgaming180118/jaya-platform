# Fase A — RAG Foundation

> **Estimasi:** 1–2 minggu  
> **Prasyarat:** Instalasi dasar JAYA_RESEARCH, `NVIDIA_API_KEY` aktif  
> **Tujuan:** Menutup gap antara dokumentasi RAG (FAISS + embedding) dan implementasi aktual (keyword MVP), serta memperbaiki endpoint yang dipanggil UI tetapi belum ada di backend.

---

## Konteks Masalah

| Area | Kondisi saat ini | Target Fase A |
|------|------------------|---------------|
| `enhanced_rag.py` | Hanya utilitas memory profiling | `EnhancedRAGClient` + `VectorStore` penuh |
| `rag_client.py` | Keyword search dari JSON | Fallback saja, bukan jalur utama |
| Thesis upload | Memanggil `ingest_text()` yang tidak ada | Ingest ke vector store workspace |
| Endpoint API | `/ingest`, `/research/recursive` hilang | Sesuai `api-reference.md` & `api.js` |
| Akurasi QA | v6 ~60% (regresi) | ≥80% (menuju v5 ~90% di Fase B) |

---

## Workflow Anak

| ID | Nama | Dokumen | Bergantung pada |
|----|------|---------|-----------------|
| **A.1** | Restore Enhanced RAG | [a1-enhanced-rag-restore.md](workflows/phase-a/a1-enhanced-rag-restore.md) | — |
| **A.2** | Pipeline Ingest | [a2-ingest-pipeline.md](workflows/phase-a/a2-ingest-pipeline.md) | A.1 |
| **A.3** | Endpoint API Hilang | [a3-missing-endpoints.md](workflows/phase-a/a3-missing-endpoints.md) | A.1, A.2 (sebagian paralel) |

**Urutan disarankan:** A.1 → A.2 → A.3 (A.3 endpoint `/research/recursive` bisa paralel dengan A.2).

---

## Master Checklist Fase A

Centang setelah **seluruh** checklist di workflow anak selesai.

### A.1 — Enhanced RAG Restore
- [x] Semua item inti di [a1-enhanced-rag-restore.md](workflows/phase-a/a1-enhanced-rag-restore.md) selesai (reranker opsional tertunda)
- [x] `from research.enhanced_rag import EnhancedRAGClient` tidak lagi fallback ke keyword MVP

### A.2 — Ingest Pipeline
- [ ] Semua item di [a2-ingest-pipeline.md](workflows/phase-a/a2-ingest-pipeline.md) selesai
- [ ] Upload thesis → chat thesis mengembalikan jawaban grounded

### A.3 — Missing Endpoints
- [ ] Semua item di [a3-missing-endpoints.md](workflows/phase-a/a3-missing-endpoints.md) selesai
- [ ] UI `api.js` tidak error pada ingest & recursive research

### Verifikasi Integrasi Fase
- [ ] `POST /chat` dengan workspace berisi dokumen → respons menyertakan `sources`
- [ ] `POST /thesis/upload` → `POST /chat` (thesis) → jawaban merujuk isi PDF
- [ ] `POST /ingest` berhasil untuk PDF/TXT/MD
- [ ] Tidak ada regresi pada endpoint thesis/research yang sudah ada
- [ ] Dokumen `rag-chat.md` dan `components.md` diperbarui jika API berubah

---

## Kriteria Selesai Fase A

Fase A **selesai** jika:

1. **Enhanced RAG** menjadi jalur utama di `get_engines()` — bukan alias `RAGClient` keyword.
2. **Ingest thesis** tidak lagi menghasilkan warning `ingest_text` non-fatal.
3. **Endpoint `/ingest`** dan **`/research/recursive`** merespons sesuai kontrak API.
4. **Smoke test manual** 10 pertanyaan dari 1 PDF TA → minimal 8 jawaban relevan (grounded).

---

## File Utama yang Terdampak

```
JAYA_RESEARCH/src/research/enhanced_rag.py      ← implementasi utama
JAYA_RESEARCH/src/research/rag_client.py          ← fallback / compat layer
JAYA_RESEARCH/src/network/research_api.py         ← get_engines, endpoint baru
JAYA_RESEARCH/ui/src/services/api.js              ← sudah memanggil endpoint
JAYA_RESEARCH/docs/02-architecture/api-reference.md
```

---

## Risiko & Mitigasi

| Risiko | Mitigasi |
|--------|----------|
| Biaya embedding NIM tinggi | Cache embedding per chunk; batch ingest |
| FAISS index besar di disk | Index per workspace di `workspaces/{id}/vector_store/` |
| Breaking change API | Pertahankan field response yang dipakai UI |

---

**Selanjutnya:** [Fase B — Production Readiness →](phase-b-production-readiness.md)
