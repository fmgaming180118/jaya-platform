# Workflow A.1 — Restore Enhanced RAG

> **Fase:** [A — RAG Foundation](../../phase-a-rag-foundation.md)  
> **Estimasi:** 4–6 hari  
> **Tujuan:** Mengimplementasikan `EnhancedRAGClient` dan `VectorStore` di `enhanced_rag.py` dengan pola single index + filter workspace (memperbaiki regresi v6).

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `src/research/enhanced_rag.py` | Implementasi utama |
| `src/research/rag_client.py` | Fallback keyword (tetap ada) |
| `src/network/research_api.py` | `get_engines()`, import EnhancedRAG |
| `src/research/workspace_manager.py` | Path vector store per workspace |
| `.env` | `NVIDIA_EMBED_MODEL`, chunk size |

---

## Desain Target

```
PDF/Text → Clean text → Chunk (page-aware) → Embed (NIM) → FAISS index
                                                              │
Query → Embed → FAISS search + workspace_id filter → Top-K → (optional rerank) → context
```

**Prinsip v6 fix:** Satu index FAISS per workspace di `workspaces/{id}/vector_store/`, dengan metadata `workspace_id`, `page`, `source` pada setiap chunk.

---

## Checklist Implementasi

### 1. VectorStore
- [x] Buat class `VectorStore` dengan persistensi disk (`index.faiss` + `metadata.json`)
- [x] Method `add_chunks(chunks, embeddings, metadata_list)`
- [x] Method `search(query_embedding, top_k, filters)` — filter `workspace_id` wajib
- [x] Method `delete_by_source(source_id)` untuk re-ingest
- [x] Method `count()` dan `stats()` untuk debugging

### 2. Text Processing (pipeline v5)
- [x] Implementasi `clean_text()` — hapus header/footer berulang
- [x] Normalisasi whitespace dan karakter OCR noise
- [x] Chunking **page-aware** (preserve `page_number` di metadata)
- [x] Parameter chunk size/overlap dari `config` atau `.env`

### 3. Embedding Client
- [x] Wrapper NVIDIA embedding API (reuse pola dari `teacher.py`)
- [x] Batch embedding untuk ingest (batch size configurable)
- [x] Cache embedding per hash chunk (opsional, file `.cache/embeddings/`)
- [x] Error handling + retry 3x dengan backoff

### 4. EnhancedRAGClient
- [x] Class `EnhancedRAGClient` dengan constructor `(vector_store_path, workspace_id)`
- [x] Method `ingest_text(text, metadata)` — chunk → embed → index
- [x] Method `ingest_file(file_path, metadata)` — PDF/TXT/MD
- [x] Method `search(query, top_k=5)` — return `[{content, score, metadata}]`
- [x] Method `get_context_for_query(query, top_k=5)` — string gabungan untuk LLM
- [x] Kompatibel dengan interface yang dipanggil `research_api.py`

### 5. Integrasi API
- [x] Update `get_engines()` agar selalu memuat `EnhancedRAGClient` (bukan fallback)
- [x] Path vector store: `workspace_manager.get_paths(id)["vector_store"]`
- [x] Hapus atau persempit try/except fallback ke keyword `RAGClient`

### 6. Reranker (opsional Fase A, wajib jika target akurasi tinggi)
- [ ] Integrasi NVIDIA rerank model setelah FAISS top-20 → final top-5
- [ ] Flag `.env`: `RAG_RERANK_ENABLED=true`

---

## Checklist Testing

- [x] Unit test: `clean_text()` menghapus header berulang
- [x] Unit test: chunking menghasilkan metadata `page_number`
- [x] Unit test: `VectorStore.search()` menghormati filter workspace
- [ ] Integration test: ingest 10 halaman PDF → search query relevan → top-1 benar
- [x] Regression: workspace A tidak melihat dokumen workspace B
- [ ] Memory: ingest PDF 200 halaman tidak melebihi threshold `memory_guard`

---

## Kriteria Selesai Workflow A.1

- [x] `python -c "from research.enhanced_rag import EnhancedRAGClient, VectorStore"` sukses
- [x] Import di `research_api.py` tidak jatuh ke keyword fallback
- [ ] Manual smoke test: 5 pertanyaan dari PDF TA → ≥4 jawaban grounded

---

## Verifikasi

```bash
cd JAYA_RESEARCH
python -m pytest tests/test_enhanced_rag.py -v   # setelah test dibuat
# Manual:
# 1. Start API
# 2. Upload PDF via thesis atau ingest
# 3. POST /chat dengan pertanyaan spesifik dari isi PDF
```

---

**Fase induk:** [phase-a-rag-foundation.md](../../phase-a-rag-foundation.md) · **Berikutnya:** [A.2 Ingest Pipeline](a2-ingest-pipeline.md)
