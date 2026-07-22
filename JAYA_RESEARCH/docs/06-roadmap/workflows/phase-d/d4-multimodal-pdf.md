# Workflow D.4 — Multimodal PDF Ingest

> **Fase:** [D — Ecosystem Bridge](../../phase-d-ecosystem-bridge.md)  
> **Estimasi:** 1–2 minggu  
> **Prasyarat:** [Fase A](../../phase-a-rag-foundation.md)  
> **Tujuan:** RAG dapat mengindeks dan menjawab pertanyaan tentang **tabel dan gambar** dalam PDF akademik.

---

## Komponen Terkait

| File | Peran |
|------|-------|
| `src/research/enhanced_rag.py` | Extend ingest |
| `src/research/rag_client.py` | `NVIDIARAGClient` stub |
| `docs/05-research-notes/nvidia-nim-integration.md` | nv-ingest reference |
| `docs/04-development/pdf-qa-benchmark.md` | Rekomendasi multimodal |

---

## Checklist Implementasi

### 1. PDF Element Extraction
- [ ] Deteksi tabel via pdfplumber `extract_tables()`
- [ ] Serialize tabel ke Markdown/CSV text untuk embedding
- [ ] Ekstrak gambar → simpan ke `workspaces/{id}/assets/`
- [ ] Caption gambar dari teks surrounding (jika ada)

### 2. Multimodal Embedding (pilih satu)
- [ ] **Opsi A:** NVIDIA multimodal embedding API untuk image+text
- [ ] **Opsi B:** OCR gambar (Tesseract/easyocr) → text embedding
- [ ] **Opsi C:** nv-ingest pipeline (jika infrastruktur tersedia)

### 3. Index Metadata
- [ ] Chunk type: `text` | `table` | `figure`
- [ ] `figure`: path gambar + caption text
- [ ] `table`: row/col count + serialized content

### 4. Retrieval & Chat
- [ ] Query "apa isi Tabel 3.2" → retrieve chunk type=table
- [ ] Response menyertakan source type di citations
- [ ] UI: tampilkan thumbnail gambar jika relevan (opsional)

---

## Checklist Benchmark

- [ ] Tambah 5 pertanyaan ground truth tentang tabel di `ground_truth.json`
- [ ] Akurasi tabel-specific ≥70% (baseline baru)

---

## Kriteria Selesai Workflow D.4

- [ ] Minimal **tabel** ter-index dan ter-query dengan benar
- [ ] `rag-chat.md` menjelaskan dukungan multimodal
- [ ] Tidak regresi akurasi teks dari Fase B

---

**Sebelumnya:** [D.3](d3-evolution-ui.md) · **Berikutnya:** [D.5 Voice Integration](d5-voice-integration.md)
