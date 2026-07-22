# NVIDIA NIM Integration — RAG, IDP, dan Agent Architecture

Dokumen ini merangkum bagaimana JAYA Research menggunakan ekosistem NVIDIA NIM sebagai backend inferensi.

---

## Apa itu NVIDIA NIM?

**NVIDIA Inference Microservices (NIM)** adalah kumpulan microservices yang menyediakan model AI terbaik melalui API standar OpenAI-compatible. JAYA Research menggunakan NIM untuk:

| Layanan | Model | Digunakan di |
|---|---|---|
| LLM Reasoning | Nemotron Super 49B | Novelty check, gap analysis, critique |
| LLM Standard | Llama 3.3 70B | Chat, laporan, revisi teks |
| Embeddings | `nvidia/nv-embedqa-e5-v5` | RAG vector store |
| STT | NVIDIA Riva ASR | Voice agent (opsional) |
| TTS | NVIDIA Riva TTS | Voice agent (opsional) |

---

## Cara JAYA Memanggil NIM

Semua panggilan ke NIM melalui `src/teacher.py`:

```python
# Penggunaan dasar
brain = Teacher(model_type="reasoning")
answer = brain.ask("Analisis novelty topik ini: ...")

# Generate panjang (laporan, revisi)
response = brain.generate_completion(prompt)
```

NIM menggunakan API yang kompatibel dengan OpenAI — sehingga `Teacher` menggunakan `openai` library dengan base URL custom.

---

## RAG Pipeline dengan Nemotron

JAYA mengimplementasikan pipeline RAG 4-tahap (berdasarkan NVIDIA Document Processing Blueprint):

### 1. Extraction
```
PDF Input
    │
    ▼
PyMuPDF → Extract text, preserve structure
    │ (fallback)
    ▼
pdfplumber → Better for complex layouts
    │ (fallback)
    ▼
PyPDF2 → Last resort
```

### 2. Chunking & Embedding
```
Raw text
    │
    ▼
Chunker (size=512, overlap=128)
    │
    ▼
NVIDIA nv-embedqa-e5-v5
    │
    ▼
FAISS vector store
```

### 3. Retrieval
```
Query
    │
    ▼
Embed query (same model)
    │
    ▼
FAISS similarity search → Top-K chunks
    │ (opsional)
    ▼
Reranker (nvidia/llama-nemotron-rerank)
```

### 4. Generation
```
Query + Retrieved context
    │
    ▼
Nemotron Super 49B (reasoning)
    │
    ▼
Answer with citations
```

---

## Intelligent Document Processing (IDP)

Untuk dokumen kompleks (tabel, grafik, layout rumit), NVIDIA menyediakan **nv-ingest**:

```python
# Instalasi (opsional, butuh Docker)
# docker run -p 7671:7671 nvcr.io/nvidia/nemo/nv-ingest:latest

from nv_ingest_client import NvIngestClient
client = NvIngestClient(
    message_client_hostname="localhost",
    message_client_port=7671
)
```

JAYA menggunakan nv-ingest sebagai **opsional** — fallback ke PyMuPDF jika tidak tersedia.

**Keunggulan nv-ingest:**
- Ekstrak tabel sebagai Markdown (bukan teks acak)
- Crop grafik untuk multimodal RAG
- Preserves layout semantik dokumen

---

## Model Selection Guide

| Task | Model Rekomendasi | Alasan |
|---|---|---|
| Analisis novelty | Nemotron Super (reasoning) | Butuh thinking mendalam, bandingkan banyak paper |
| Revisi teks | Llama 3.3 70B | Fast, fluent writing |
| Chat RAG | Llama 3.3 70B | Conversational, tidak perlu reasoning berat |
| Metadata extraction | Llama 3.3 70B | JSON extraction tidak perlu reasoning |
| Defense questions | Nemotron Super | Butuh kreativitas + domain knowledge |

---

## Resource Efficiency

JAYA Research menggunakan NIM cloud — tidak ada GPU lokal yang dibutuhkan.

**Estimasi API call per analisis TA:**

| Step | Call ke NIM | Token (estimasi) |
|---|---|---|
| Meta extraction | 1x | ~2,000 |
| Novelty reasoning | 1x | ~4,000 |
| Gap analysis | 1x | ~5,000 |
| Critique | 1x | ~5,000 |
| Defense questions | 1x | ~3,000 |
| **Total** | **5x** | **~19,000 tokens** |

Biaya sangat kecil dengan free tier NVIDIA NIM (100K tokens/bulan gratis).

---

## Referensi

- [NVIDIA NIM Documentation](https://docs.nvidia.com/nim/)
- [NVIDIA Build Platform](https://build.nvidia.com)
- [nv-ingest GitHub](https://github.com/NVIDIA/nv-ingest)
- [NVIDIA AI Blueprints — Document Processing](https://build.nvidia.com/nvidia/build-a-document-processing-pipeline-for-rag)
