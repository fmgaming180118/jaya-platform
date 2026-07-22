# Workflow A.2 — Pipeline Ingest Dokumen

> **Fase:** [A — RAG Foundation](../../phase-a-rag-foundation.md)  
> **Estimasi:** 2–3 hari  
> **Prasyarat:** [A.1 Enhanced RAG Restore](a1-enhanced-rag-restore.md)  
> **Tujuan:** Menyatukan semua jalur ingest (thesis, chat, documents) ke `EnhancedRAGClient.ingest_text()` / `ingest_file()`.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `src/network/research_api.py` | `POST /thesis/upload`, `POST /documents/ingest-pdf` |
| `src/research/enhanced_rag.py` | `ingest_text`, `ingest_file` |
| `src/research/graph_rag.py` | `ingest_document` (paralel, tetap) |
| `src/research/academic/journal_processor.py` | Ingest jurnal |

---

## Jalur Ingest Saat Ini (Perlu Disatukan)

| Jalur | Status | Target |
|-------|--------|--------|
| `POST /thesis/upload` | Memanggil `ingest_text()` — **method tidak ada** | Fixed |
| `POST /documents/ingest-pdf` | Perlu diverifikasi | Pakai EnhancedRAG |
| Research report selesai | RAG ingest dikomentari | Aktifkan kembali |
| Chat tool generate file | Tidak di-index | Opsional index |

---

## Checklist Implementasi

### 1. Method Ingest di EnhancedRAGClient
- [ ] `ingest_text(raw_text, metadata)` — utama untuk thesis
- [ ] `ingest_file(file_path, metadata)` — PDF via PyMuPDF chain
- [ ] Return dict: `{status, chunks_added, source, workspace_id}`
- [ ] Dedup: skip jika `source` + hash konten sudah ada (opsional)

### 2. Perbaikan Thesis Upload
- [ ] Fix `research_api.py` baris `rag_client.ingest_text(...)` — tidak lagi exception
- [ ] Metadata wajib: `source=thesis`, `file_name`, `session_id`
- [ ] Log sukses: `[ThesisAPI] Ingested N chunks to workspace=...`
- [ ] Graph ingest tetap: `graph_engine.ingest_document(raw_text[:4000], ...)`

### 3. Perbaikan Documents Ingest
- [ ] `POST /documents/ingest-pdf` memanggil `EnhancedRAGClient.ingest_file`
- [ ] Response menyertakan `chunks_added`
- [ ] Error PDF extraction → pesan jelas ke client

### 4. Research Report Ingest
- [ ] Uncomment/aktifkan ingest laporan riset ke RAG setelah autonomous research selesai
- [ ] Metadata: `source=research_report`, `topic`

### 5. Konsistensi Workspace
- [ ] Semua ingest menerima `workspace_id` dan meneruskannya ke vector store
- [ ] Default workspace: `"default"` jika tidak disediakan

---

## Checklist Testing

- [ ] Upload thesis PDF → log menunjukkan N chunks (bukan warning)
- [ ] `POST /chat` setelah upload → jawaban merujuk isi thesis
- [ ] Ingest PDF kedua di workspace sama → chunk count bertambah
- [ ] Ingest file sama di workspace berbeda → terisolasi
- [ ] File corrupt PDF → HTTP 422 dengan pesan jelas

---

## Kriteria Selesai Workflow A.2

- [ ] Tidak ada log `[ThesisAPI] RAG ingest warning (non-fatal)`
- [ ] Semua jalur ingest di tabel atas menggunakan `EnhancedRAGClient`
- [ ] Dokumen `thesis-analyzer.md` menjelaskan bahwa chat thesis memakai RAG vector

---

## Verifikasi

```bash
# 1. Upload thesis
curl -X POST "http://localhost:8000/thesis/upload" \
  -F "file=@tests/sample_ta.pdf" -F "workspace_id=test-ws"

# 2. Chat
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "Apa judul penelitian?", "workspace_id": "test-ws"}'
# Expect: jawaban grounded + sources
```

---

**Sebelumnya:** [A.1](a1-enhanced-rag-restore.md) · **Berikutnya:** [A.3 Missing Endpoints](a3-missing-endpoints.md)
