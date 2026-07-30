<div align="center">

# ⚡ JAYA Sovereign Superintelligence Ecosystem ⚡
### *JARVIS-Level Sovereign Edge AI Engine in < 200 MB*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-2.5.1%2Bcu121-orange.svg)](https://pytorch.org/)
[![Android Native](https://img.shields.io/badge/Android-Kotlin%2FJetpack-green.svg)](JAYA_ANDROID/)
[![Architecture](https://img.shields.io/badge/Architecture-Sparse%20Micro--MoE-purple.svg)](docs/ARCHITECTURE.md)
[![Status](https://img.shields.io/badge/Build-Passing%20(78%2F78%20Tests)-brightgreen.svg)](docs/STATUS.md)

**JAYA** adalah ekosistem kecerdasan buatan berdaulat (*Sovereign Edge AI*) yang dirancang untuk menghadirkan kemampuan setara **JARVIS** — bernalar mendalam, memori episodik lintas sesi, pemetaan profil pengguna dinamis, dan retrieval RAG hibrida — **100% offline di perangkat lokal tanpa bergantung pada cloud** dan tetap berada di dalam **footprint memori & disk < 200 MB**.

[Dokumentasi Utama](docs/README.md) • [Roadmap Canonic](docs/ROADMAP.md) • [Checklist Intelijen](JAYA_CORE/docs/06-roadmap/ULTRA_INTELLIGENCE_CHECKLIST.md) • [Status Terverifikasi](docs/STATUS.md)

</div>

---

## 💡 Mengapa JAYA Beda? (JARVIS vs Chatbot Biasa)

| Fitur Utama | Chatbot Cloud Biasa | **JAYA Sovereign Engine (< 200 MB)** |
| :--- | :--- | :--- |
| **Privasi & Kedaulatan** | Data terkirim ke server cloud | **100% Offline / Edge-Sovereign (Lokal)** |
| **Ukuran Footprint** | 40 GB – 140 GB (Awang-awang Cloud) | **< 200 MB Disk & RAM (SLM Ultra-Compact)** |
| **Memori Episodik** | Lupa percakapan setelah sesi ditutup | **✅ SQLite Episodic Memory (Ingat lintas hari/sesi)** |
| **Profil Pengguna** | Generik / Tidak mengenal pengguna | **✅ Dynamic User Profile Engine (Ingat topik skripsi, deadline)** |
| **Routing Spesialis** | Model Monolitik Kaku | **✅ Sparse Micro-MoE (4 Pakar: Thesis, Code, Logic, Dialogue)** |
| **Refleksi & Koreksi** | Sering Halusinasi Tanpa Peringatan | **✅ Reflexion Self-Correction Loop & Safety Gate** |
| **Retrieval Pengetahuan** | Keyword RAG Sederhana | **✅ Micro-GraphRAG + BM25 + Dense Vector RRF Fusion** |

---

## 🏛️ Arsitektur Ekosistem Monorepo

```
                     ┌───────────────────────────────────────────┐
                     │          JAYA_ANDROID (Client)            │
                     │  - Jetpack Compose UI                     │
                     │  - On-Device JayaNanoEngine Fallback      │
                     └─────────────────────┬─────────────────────┘
                                           │ (LAN REST / JSON Payload)
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│                          JAYA_CORE Server (REST API)                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│  ┌────────────────────────┐  ┌────────────────────────┐  ┌───────────────────┐  │
│  │   SLMEngine (Fase 1)   │  │ HybridRetriever (F2)   │  │ MemoryManager(F3) │  │
│  │ SmolLM2-135M / Qwen0.5B│  │ BM25 + Dense + Graph   │  │ Episodic + Profile│  │
│  └───────────┬────────────┘  └───────────┬────────────┘  └─────────┬─────────┘  │
│              │                           │                         │            │
│              ▼                           ▼                         ▼            │
│  ┌────────────────────────┐  ┌───────────────────────────────────────────────┐  │
│  │   MicroMoE (Fase 4)    │  │        JarvisAgentFacade (Fase 5)             │  │
│  │ 4 Pakar + Reflexion    │  │ Task Planner + Proactive Nudge + Safety Gate  │  │
│  └────────────────────────┘  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## ⚡ 5 Pilar Utama Superintelijen JAYA

### 🧠 1. Core Neural Engine (`SLMEngine`)
* Menggunakan model *Small Language Model* (SLM) ultra-compact (`SmolLM2-135M` / `Qwen2.5-0.5B`).
* Akselerasi inferensi GPU via PyTorch 2.5.1 + CUDA dengan fallback otomatis ke dynamic INT8 quantization pada CPU.
* Context window dinamis dengan *H2O KV-Cache Pruning*.

### 🔍 2. Knowledge Core (`HybridRetriever`)
* Menggabungkan **BM25 Sparse Search** (SQLite FTS5) + **Dense Vector Embeddings** (`all-MiniLM-L6-v2` 23 MB) menggunakan *Reciprocal Rank Fusion (RRF)*.
* **Micro-GraphRAG**: Knowledge graph relasi entitas SQLite dengan multi-hop BFS traversal untuk penalaran terdistribusi.

### 📜 3. Memori Episodik & Profil Dinamis (`MemoryManager`)
* **Episodic Long-Term Memory (Pillar 31)**: Menyimpan dan mengambil konteks percakapan lintas hari.
* **Dynamic User Profile (Pillar 32)**: Otomatis mendeteksi nama, topik skripsi/riset, bab aktif, dan deadline pengguna secara inkremental.
* **Narrative Compression**: Merangkum sesi panjang menjadi capsule naratif padat (< 400 karakter).

### 🎭 4. Sparse Micro-MoE & Reflexion (`MicroMoEEngine`)
* **Sparse 1-of-4 Routing**: Mengaktifkan 1 pakar terbaik per prompt (*Expert Thesis*, *Expert Code*, *Expert Logic*, *Expert Dialogue*).
* **Reflexion Loop**: Memeriksa skor kualitas respons, mendeteksi halusinasi, dan melakukan re-generation otomatis dengan parameter ketat jika skor di bawah ambang batas.

### 🤖 5. Agentic Intelligence (`JarvisAgentFacade`)
* **Hierarchical Task Planner**: Memecah tujuan besar (contoh: "Selesaikan BAB III Skripsi") menjadi sub-task konkret terlacak.
* **Proactive Intelligence Engine (Pillar 29)**: Memberikan pesan pengingat proaktif (deadline, bab skripsi, tugas tertunda).
* **Agentic Safety Gate**: Mengintersept instruksi ambigu atau berisiko tinggi (*delete/overwrite*) untuk meminta konfirmasi sebelum eksekusi.

---

## 🛠️ Modul Utama Repositori

| Modul | Tanggung Jawab | Status |
| :--- | :--- | :--- |
| [`JAYA_CORE`](JAYA_CORE/) | Engine neural SLM, MoE, RAG, memori episodik, dan pelaksana JayaIR | **Aktif & Teruji (78/78 Unit Tests Pass)** |
| [`JAYA_RESEARCH`](JAYA_RESEARCH/) | Modul riset, ekstraksi literatur, dan pipeline analisis ilmiah | Prototipe Terintegrasi |
| [`JAYA_AGENT`](JAYA_AGENT/) | Orkestrasi tugas agen dan eksekusi tool calling | Prototipe |
| [`JAYA_ANDROID`](JAYA_ANDROID/) | Aplikasi Klien Android (Kotlin, Jetpack Compose, Room DB) | Prototipe Aktif |
| [`JAYA_OS`](JAYA_OS/) | Runtime sistem, sandbox kebijakan, dan manajemen perangkat | Prototipe Awal |

---

## 🚀 Mulai Cepat (Quick Start)

### Prasyarat:
* Python 3.10+
* PyTorch 2.5.1+ (dengan CUDA opsional untuk GPU)
* Node.js 18+ (untuk UI `JAYA_RESEARCH`)

### 1. Setup Environment & Dependencies
```powershell
# Clone repositori ini
git clone https://github.com/fmgaming180118/jaya-research.git
cd jaya-research

# Buat virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# Install dependensi
pip install -r JAYA_CORE/requirements.txt
```

### 2. Jalankan Test Suite (78/78 Tests)
```powershell
python -m pytest JAYA_CORE/tests -v
```

### 3. Jalankan Server JAYA_CORE REST API
```powershell
python scripts/run_jaya_core_server.py
```
Server akan aktif di `http://localhost:8000/chat` dan siap melayani permintaan dari aplikasi Android maupun antarmuka riset.

---

## 🔒 Tata Kelola & Proteksi Ketinggian Kode

- **Izin Akses**: Repositori ini bersifat **Public (Dapat Dilihat Publik)**, tetapi **seluruh izin Write/Push dibatasi 100% hanya untuk Pemilik Repositori (`fmgaming180118`)**.
- **Kontribusi Luar**: Pengguna lain hanya dapat berkontribusi melalui mekanisme *Fork* & *Pull Request (PR)* yang wajib ditinjau dan disetujui secara manual.
- **Aturan Kerahasiaan**: Data pribadi, API keys, credentials, file database runtime (`*.db`), dan model besar dilarang di-commit ke repositori (dikelola oleh `.gitignore`).

---

## 📜 Lisensi & Atribusi

Proyek ini dirilis di bawah [MIT License](LICENSE). Hak cipta milik **fmgaming180118** & Tim Pengembang JAYA Sovereign AI (2026).

---

<div align="center">
  <sub>Dibuat dengan dedikasi tinggi oleh <b>fmgaming180118</b> untuk mewujudkan AI Berdaulat Berbahasa Indonesia.</sub>
</div>
