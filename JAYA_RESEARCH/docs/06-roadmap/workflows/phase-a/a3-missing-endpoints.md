# Workflow A.3 — Implementasi Endpoint API yang Hilang

> **Fase:** [A — RAG Foundation](../../phase-a-rag-foundation.md)  
> **Estimasi:** 2–3 hari  
> **Prasyarat:** [A.1](a1-enhanced-rag-restore.md) (wajib), [A.2](a2-ingest-pipeline.md) (untuk `/ingest`)  
> **Tujuan:** Menambahkan endpoint yang sudah didokumentasikan dan dipanggil UI tetapi belum ada di `research_api.py`.

---

## Endpoint yang Hilang

| Method | Path | Referensi | Status |
|--------|------|-----------|--------|
| `POST` | `/ingest` | `api-reference.md`, `api.js`, `rag-chat.md` | ❌ Belum ada |
| `POST` | `/research/recursive` | `api-reference.md`, `api.js`, `research-agent.md` | ❌ Belum ada |
| `POST` | `/ingest` | Body: `{file_path, workspace_id?}` | Perlu implementasi |
| `POST` | `/ingest/video` | Sudah ada di API | ✅ Verifikasi saja |

---

## Checklist: POST /ingest

### Implementasi
- [ ] Tambah model Pydantic `IngestRequest` di `api_models.py`: `file_path`, `workspace_id?`
- [ ] Endpoint `POST /ingest` di `research_api.py`
- [ ] Validasi: file exists, ekstensi didukung (`.pdf`, `.txt`, `.md`)
- [ ] Panggil `get_engines(workspace_id)` → `rag_client.ingest_file(path, metadata)`
- [ ] Panggil `graph_engine.ingest_document` untuk cuplikan awal (opsional)
- [ ] Response: `{status, chunks_added, file_path, workspace_id}`

### Keamanan
- [ ] Path traversal protection — resolve path, tolak `..`
- [ ] Batasi path ke direktori workspace atau upload dir yang diizinkan
- [ ] Max file size configurable

### Testing
- [ ] `api.js` `ingestDocument()` berhasil tanpa 404
- [ ] curl dari `rag-chat.md` berfungsi
- [ ] File tidak ada → 404 dengan pesan jelas

---

## Checklist: POST /research/recursive

### Implementasi
- [ ] Tambah model `RecursiveResearchRequest`: `topic`, `workspace_id?`, `max_iterations?` (default 3)
- [ ] Endpoint `POST /research/recursive` — background task (pola `/research/autonomous`)
- [ ] Orchestrator: loop Plan → Query → Synthesize → sub-topic baru (bounded)
- [ ] Batas iterasi wajib (`max_iterations` ≤ 10)
- [ ] Timeout global per job (mis. 30 menit)
- [ ] Simpan laporan ke workspace files + ingest ke RAG
- [ ] Response awal: `{job_id, status: "started", topic}`

### Perbaikan ResearchAgent
- [ ] Ganti `input()` human-in-loop dengan flag `human_in_loop: false` default untuk API
- [ ] Jika `human_in_loop=true`, queue pertanyaan ke session (Fase B) — untuk A cukup nonaktifkan

### Status Endpoint (opsional tapi disarankan)
- [ ] `GET /research/recursive/status/{job_id}` — progress & hasil

### Testing
- [ ] UI Research page recursive tidak 404
- [ ] `max_iterations=1` selesai dalam waktu wajar
- [ ] Laporan tersimpan di `workspaces/{id}/files/`

---

## Checklist: Verifikasi Endpoint Existing

- [ ] `POST /ingest/video` — masih berfungsi setelah perubahan A.1/A.2
- [ ] `POST /research/autonomous` — tidak regresi
- [ ] `POST /chat` — `sources` field terisi setelah ingest

---

## Checklist Dokumentasi

- [ ] `api-reference.md` sesuai implementasi aktual
- [ ] `research-agent.md` — contoh curl recursive valid
- [ ] `cli-commands.md` — path endpoint benar

---

## Kriteria Selesai Workflow A.3

- [ ] `POST /ingest` → 200 untuk PDF valid
- [ ] `POST /research/recursive` → 200/202, job berjalan di background
- [ ] Tidak ada endpoint di `api.js` yang mengembalikan 404 (kecuali yang memang planned)

---

## Verifikasi

```bash
# Ingest
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "path/to/doc.pdf", "workspace_id": "default"}'

# Recursive research
curl -X POST "http://localhost:8000/research/recursive" \
  -H "Content-Type: application/json" \
  -d '{"topic": "transformer efficiency", "max_iterations": 2}'
```

---

**Sebelumnya:** [A.2](a2-ingest-pipeline.md) · **Fase induk:** [phase-a-rag-foundation.md](../../phase-a-rag-foundation.md)
