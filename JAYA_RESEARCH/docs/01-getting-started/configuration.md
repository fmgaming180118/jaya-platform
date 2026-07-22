# Konfigurasi — `config.yaml` & `.env`

JAYA Research menggunakan dua file konfigurasi:
- **`.env`** — API keys dan secrets (JANGAN commit ke git)
- **`config.yaml`** — konfigurasi runtime yang aman untuk dicommit

---

## File `.env`

Template tersedia di [`.env.example`](../../.env.example).

### Variabel Wajib

| Variabel | Contoh | Keterangan |
|---|---|---|
| `NVIDIA_API_KEY` | `nvapi-xxxx` | Dari [build.nvidia.com](https://build.nvidia.com) |

### Variabel Opsional — Model

| Variabel | Default | Keterangan |
|---|---|---|
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | Base URL NIM API |
| `NVIDIA_LLAMA31_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b` | Model untuk reasoning |
| `NVIDIA_LLAMA31_MAX_TOKENS` | `1000000` | Max token per request |
| `NVIDIA_EMBEDDING_MODEL` | `nvidia/nv-embedqa-e5-v5` | Model embedding RAG |

### Variabel Opsional — RAG

| Variabel | Default | Keterangan |
|---|---|---|
| `RAG_CHUNK_SIZE` | `512` | Ukuran chunk saat ingest dokumen |
| `RAG_CHUNK_OVERLAP` | `128` | Overlap antar chunk |

### Variabel Opsional — Path Data

> Biarkan kosong untuk menggunakan path default (`JAYA_RESEARCH/data/...`)

| Variabel | Keterangan |
|---|---|
| `JAYA_DATA_DIR` | Override direktori data utama |
| `VECTOR_STORE_PATH` | Override path FAISS vector store |
| `EVOLUTION_MEMORY_PATH` | Override path memori Digital Twin |
| `DISCOVERY_MEMORY_PATH` | Override path memori discovery loop |
| `KNOWLEDGE_GRAPH_PATH` | Override path knowledge graph |

### Variabel Opsional — QLoRA Training

| Variabel | Default | Keterangan |
|---|---|---|
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Ollama server untuk teacher |
| `QLORA_OLLAMA_MODEL` | `qwen3:4b` | Model teacher lokal |
| `QLORA_BASE_MODEL` | `Qwen/Qwen3-4B-Instruct-2507` | Base model untuk fine-tuning |

### Variabel Opsional — Voice Agent

| Variabel | Keterangan |
|---|---|
| `NVIDIA_RIVA_URI` | WebSocket URI untuk NVIDIA Riva STT/TTS |

---

## File `config.yaml`

Konfigurasi runtime di `JAYA_RESEARCH/config.yaml`:

```yaml
# Contoh config.yaml
model:
  type: reasoning          # reasoning | standard | chat
  temperature: 0.6
  max_tokens: 4096

rag:
  chunk_size: 512
  top_k: 5
  rerank: true

research:
  max_iterations: 3
  timeout_seconds: 300
```

> [!NOTE]
> `config.yaml` aman untuk dicommit ke git — tidak mengandung secret apapun.

---

## Workspace

Setiap workspace menyimpan data terpisah (vector store, graph, history):

```
workspaces/
├── default/
│   ├── vector_store/    ← FAISS index
│   └── knowledge_graph/ ← NetworkX graph
├── tugas-akhir-saya/
│   ├── vector_store/
│   └── knowledge_graph/
```

Workspace baru dibuat otomatis lewat UI atau API:
```bash
curl -X POST "http://localhost:8000/workspaces/create?name=my-workspace"
```

---

**Selanjutnya:** [Arsitektur Sistem →](../02-architecture/overview.md)
