# Arsitektur Sistem Jaya (v3.0)

Dokumen ini menjelaskan arsitektur teknis terbaru dari **Jaya Research Assistant**, yang telah berevolusi menjadi sistem berbasis **NVIDIA NIM** sepenuhnya.

## 1. High-Level Overview

Sistem Jaya terdiri dari tiga komponen utama yang saling terintegrasi:

1.  **Voice Agent (Nimble Pipecat)**: Antarmuka suara real-time.
2.  **RAG Engine (Enhanced)**: Memori dan pengetahuan berbasis dokumen lokal & web.
3.  **NVIDIA NIM**: Mesin inferensi untuk LLM, Embeddings, dan Speech.

```mermaid
graph TD
    User((User)) <-->|Voice/Audio| VoiceAgent[Voice Agent\n(Nimble Pipecat)]
    
    subgraph "Jaya Core"
        VoiceAgent <-->|Context Query| RAG[Enhanced RAG Client]
        RAG <-->|Vector Search| FAISS[(Vector Store)]
        RAG <-->|Fallback| WebSearch[Web Search\n(DuckDuckGo)]
    end
    
    subgraph "NVIDIA NIM Services"
        VoiceAgent -->|STT| RivaSTT[NVIDIA Riva STT]
        VoiceAgent -->|TTS| RivaTTS[NVIDIA Riva TTS]
        VoiceAgent -->|LLM| NimLLM[NVIDIA Llama 3]
        RAG -->|Embeddings| NimEmbed[nvidia/nv-embedqa]
    end
    
    subgraph "Data Ingestion"
        PDFs[PDF Documents] --> Nemotron[Nemotron Ingest\n(nv-ingest)]
        Nemotron -->|Text/Tables/Charts| RAG
    end
```

## 2. Komponen Detail

### A. Voice Agent (`src/voice_agent/`)
-   **Framework**: [Pipecat AI](https://github.com/pipecat-ai/pipecat) (Nimble).
-   **Fungsi**: Menangani streaming audio dua arah, VAD (Voice Activity Detection), dan manajemen state percakapan.
-   **Integrasi RAG**: Agent memiliki akses langsung ke `EnhancedRAGClient`. Setiap kali user bertanya, agent melakukan query ke RAG sebelum mengirim prompt ke LLM.
-   **NIM Integration**: Menggunakan `NVIDIA Riva` untuk Speech-to-Text (STT) dan Text-to-Speech (TTS) low-latency.

### B. Enhanced RAG (`src/research/enhanced_rag.py`)
Mesin pencari cerdas yang menggantikan RAG keyword-based lama.
-   **Embeddings**: Menggunakan model `nvidia/nv-embedqa-e5-v5` via NIM API untuk mengubah teks menjadi vektor.
-   **Vector Store**: Menggunakan `FAISS` (Facebook AI Similarity Search) untuk pencarian kemiripan super cepat.
-   **Hybrid Search**:
    1.  **Local Search**: Mencari di dokumen riset lokal.
    2.  **Web Fallback**: Jika skor relevansi lokal rendah (< 0.65), otomatis mencari di Web (DuckDuckGo).
    3.  **Synthesis**: Menggabungkan konteks lokal dan web untuk jawaban komprehensif.

### C. Nemotron Ingest (`src/research/nemotron_ingest.py`)
Modul pemrosesan dokumen tingkat lanjut ("Intelligent Document Processing").
-   **Library Mode**: Menggunakan library python `nv-ingest` secara lokal (tanpa Docker berat).
-   **Kapabilitas**:
    -   Mengekstrak teks dari PDF kompleks.
    -   **Table Extraction**: Mengubah tabel PDF menjadi format Markdown yang bisa dipahami LLM.
    -   **Chart Analysis**: Mendeteksi grafik dan diagram.

### D. Research Engine (`src/research/`)
"Otak" dari kemampuan riset otonom Jaya. Modul ini memungkinkan Jaya melakukan studi literatur mendalam tanpa intervensi manusia konstan.

**Komponen Utama:**
1.  **AGI Researcher (`agi_researcher.py`)**: Agen khusus yang fokus pada topik AGI, Self-Improvement, dan Neural Compilation.
2.  **Research Loop (`agent.py`)**:
    -   **Planning**: Membuat daftar pertanyaan riset berdasarkan topik.
    -   **Execution**: Menjalankan query paralel ke RAG dan Web Search.
    -   **Synthesis**: Menggabungkan temuan menjadi laporan komprehensif.
    -   **Review**: Mendeteksi celah informasi (research gaps) dan melakukan iterasi tambahan jika perlu.
3.  **Memory Integration**: Laporan riset otomatis disimpan ke `DiscoveryMemory` agar bisa diakses kembali oleh Voice Agent di masa depan.

## 3. Alur Data (Data Flow)

**Skenario 1: Tanya Jawab Cepat (Voice)**
1.  **Audio Input**: Suara user ditangkap oleh Mic -> Riva STT -> Teks.
2.  **RAG Lookup**: Voice Agent cek `EnhancedRAGClient`.
3.  **Answer**: Jika ada di memori, langsung dijawab via TTS.

**Skenario 2: Deep Research Task**
1.  **Command**: User meminta *"Jaya, tolong riset tentang arsitektur Transformer baru"*.
2.  **Trigger**: Voice Agent memanggil `AGIResearcher.run("Transformer Architecture")`.
3.  **Research Process**:
    -   Jaya membuat plan -> Cari di Web/Lokal -> Baca PDF -> Tulis Laporan.
4.  **Completion**: Laporan disimpan sebagai Markdown.
5.  **Notification**: Voice Agent memberitahu *"Riset selesai, laporan sudah saya simpan"*.

## 4. Konfigurasi (`.env`)
Semua endpoint dan kunci API diatur via environment variables untuk keamanan:

```ini
NVIDIA_BASE_URL=https://integrate.api.nvidia.com/v1
NVIDIA_EMBEDDING_MODEL=nvidia/nv-embedqa-e5-v5
RAG_CHUNK_SIZE=512
NV_INGEST_HOST=localhost
NVIDIA_RIVA_URI=wss://riva.api.nvidia.com
```

---

## 5. Analogi Fitur (vs Google NotebookLM)

Untuk memudahkan pemahaman, berikut adalah perbandingan fitur Jaya dengan **NotebookLM**:

| Fitur NotebookLM | Komponen Jaya | Deskripsi |
| :--- | :--- | :--- |
| **Upload PDF** | **Nemotron Ingest** | `nv-ingest` memproses PDF, tabel, dan grafik menjadi teks yang dipahami AI. |
| **Q&A with Sources** | **Enhanced RAG** | Menjawab pertanyaan *hanya* berdasarkan dokumen lokal (+ sitasi), dengan fallback ke Web jika perlu. |
| **Audio Overview** | **Voice Agent** | **Nimble Pipecat (Riva)** membuat dialog/podcast interaktif dari materi riset secara real-time. |
| **Deep Research** | **Research Engine** | Lebih canggih dari NotebookLM; Jaya bisa *mencari sendiri* materi baru di Web, bukan hanya membaca yang di-upload. |

*Dokumen ini diperbarui terakhir pada: Februari 2026*
