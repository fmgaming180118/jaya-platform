# RAG Chat & Knowledge Graph

## RAG Chat

JAYA menjawab pertanyaan berdasarkan dokumen yang sudah kamu upload ke workspace — bukan hanya dari pengetahuan LLM umum.

### Cara Kerja

```
User Question
      │
      ▼
Embed question (NVIDIA embedding model)
      │
      ▼
FAISS search → Top 5 most similar chunks
      │
      ▼
Re-rank results (optional)
      │
      ▼
LLM generates answer grounded in retrieved context
      │
      ▼
Response + source citations
```

### Ingest Dokumen

Sebelum bisa chat dengan dokumen, dokumen harus diingest:

**Via UI:** Upload langsung di halaman Chat atau Documents.

**Via API:**
```bash
# Ingest file PDF/TXT/MD dari path lokal
curl -X POST "http://localhost:8000/ingest" \
  -H "Content-Type: application/json" \
  -d '{"file_path": "/path/to/paper.pdf", "workspace_id": "default"}'

# Ingest video YouTube
curl -X POST "http://localhost:8000/ingest/video" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://youtube.com/watch?v=xxx"}'
```

**Format yang didukung:**
- PDF (teks, bukan scan/gambar murni)
- Markdown (`.md`)
- Plain text (`.txt`)
- Video YouTube (transcript diekstrak otomatis)

### Chat Via API

```bash
curl -X POST "http://localhost:8000/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Apa perbedaan BERT dan GPT?",
    "workspace_id": "default"
  }'
```

---

## Knowledge Graph

JAYA membangun graph pengetahuan dari dokumen yang diingest — menghubungkan konsep, entitas, dan relasi.

### Visualisasi

```bash
# Ambil graph data
curl "http://localhost:8000/graph?workspace_id=default"
```

Response berisi nodes dan edges yang bisa divisualisasikan di UI (halaman **Graph**).

### Struktur Graph

```json
{
  "nodes": [
    {"id": "federated_learning", "type": "concept", "weight": 5},
    {"id": "privacy", "type": "concept", "weight": 3}
  ],
  "edges": [
    {"source": "federated_learning", "target": "privacy", "relation": "addresses"}
  ]
}
```

### Kegunaan Graph

- Lihat konsep apa yang paling sering muncul di literatur kamu
- Temukan hubungan tersembunyi antar topik
- Identifikasi area yang belum terhubung (potential research gap)

---

## Workspace Isolation

Setiap workspace menyimpan RAG index terpisah. Dokumen di workspace A tidak muncul di pencarian workspace B.

```bash
# List workspace
curl "http://localhost:8000/workspaces"

# List dokumen di workspace tertentu
curl "http://localhost:8000/documents?workspace_id=tugas-akhir"
```

---

**Lihat juga:** [Thesis Analyzer](thesis-analyzer.md) — Chat RAG khusus untuk dokumen TA
