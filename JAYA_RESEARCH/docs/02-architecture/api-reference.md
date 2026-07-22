# API Reference — JAYA Research Backend

Base URL: `http://localhost:8000`

Swagger UI interaktif: `http://localhost:8000/docs`

---

## Health Check

| Method | Path | Deskripsi |
|---|---|---|
| `GET` | `/` | Status server |

```json
// Response
{"status": "online", "service": "JAYA Research API"}
```

---

## Workspace Management

| Method | Path | Deskripsi |
|---|---|---|
| `GET` | `/workspaces` | List semua workspace |
| `POST` | `/workspaces/create?name=<name>` | Buat workspace baru |
| `DELETE` | `/workspaces/{workspace_id}` | Hapus workspace |

---

## Chat

| Method | Path | Body | Deskripsi |
|---|---|---|---|
| `POST` | `/chat` | `{message, context_files?, workspace_id?}` | Chat dengan RAG |

---

## Research

| Method | Path | Body | Deskripsi |
|---|---|---|---|
| `POST` | `/research/autonomous` | `{topic, focus_areas?, workspace_id?}` | Autonomous research |
| `POST` | `/research/recursive` | `{topic, workspace_id?, max_iterations?}` | Recursive deep research |
| `POST` | `/research/journals` | `{query, max_papers?}` | Cari jurnal (ArXiv + Scholar) |

---

## Documents & Knowledge

| Method | Path | Body | Deskripsi |
|---|---|---|---|
| `POST` | `/ingest` | `{file_path, workspace_id?}` | Ingest dokumen ke RAG |
| `POST` | `/ingest/video` | `{url}` | Ingest video (YouTube) |
| `GET` | `/documents?workspace_id=<id>` | — | List dokumen teringest |
| `GET` | `/graph?workspace_id=<id>` | — | Knowledge graph JSON |
| `GET` | `/history` | — | Riwayat penelitian |

---

## Model Configuration

| Method | Path | Body | Deskripsi |
|---|---|---|---|
| `GET` | `/config/models` | — | List model NVIDIA NIM yang tersedia & model aktif |
| `POST` | `/config/models` | `{model_name}` | Ubah model aktif secara dinamis |

---

## Thesis Analysis

Semua endpoint thesis membutuhkan `session_id` yang didapat dari `/thesis/upload`.

| Method | Path | Body | Deskripsi |
|---|---|---|---|
| `POST` | `/thesis/upload` | `file (multipart) + workspace_id` | Upload PDF → ekstrak teks → RAG ingest |
| `POST` | `/thesis/analyze/{session_id}` | `{}` | Mulai 5-step analisis (background task) |
| `GET` | `/thesis/status/{session_id}` | — | Poll progress analisis |
| `POST` | `/thesis/chat/{session_id}` | `{message, workspace_id?}` | Chat dengan dokumen TA |
| `POST` | `/thesis/revise/{session_id}` | `{section_text, instruction, revision_type?}` | Revisi bagian TA |
| `POST` | `/thesis/journals/{session_id}` | — | Cari jurnal relevan dari topik TA |
| `GET` | `/thesis/export/{session_id}` | — | Download laporan `.md` |

### Thesis Status Response

```json
{
  "status": "analyzing | done | error",
  "progress": 75,
  "steps": [
    {"step": "meta",    "status": "done"},
    {"step": "novelty", "status": "done"},
    {"step": "gap",     "status": "running"},
    {"step": "critique","status": "pending"},
    {"step": "defense", "status": "pending"}
  ],
  "analysis": { ... },
  "error": null
}
```

### Revision Types

| `revision_type` | Efek |
|---|---|
| `general` | Perbaiki kejelasan, alur, kualitas akademis umum |
| `formal` | Ubah bahasa menjadi lebih formal, hilangkan bahasa kasual |
| `citation` | Tandai klaim yang butuh sitasi dengan `[Citation Needed]` |
| `methodology` | Perkuat bagian metodologi agar lebih logis dan reproducible |

---

## Academic Modules (Direct)

| Method | Path | Deskripsi |
|---|---|---|
| `POST` | `/academic/gaps?topic=<topic>` | Langsung cari gap untuk topik tertentu |

---

## Error Format

Semua error dikembalikan dalam format:
```json
{
  "detail": "Pesan error yang deskriptif"
}
```

HTTP status codes: `400` Bad Request, `404` Not Found, `500` Internal Server Error.
