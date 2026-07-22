# Dokumentasi JAYA Research

> Satu-satunya pintu masuk untuk semua dokumentasi. Baca dari sini, ikuti link ke dokumen spesifik.

---

## 📖 Cara Membaca Dokumentasi Ini

| Tujuan | Mulai dari |
|---|---|
| Mau install & coba pertama kali | [01 → Installation](01-getting-started/installation.md) |
| Paham cara kerja sistem | [02 → Architecture Overview](02-architecture/overview.md) |
| Pakai fitur bedah Tugas Akhir | [03 → Thesis Analyzer](03-features/thesis-analyzer.md) |
| Jalankan autonomous research | [03 → Research Agent](03-features/research-agent.md) |
| Setup pengembangan / kontribusi | [04 → Development](04-development/testing.md) |
| Riset mendalam (QLoRA, NIM, dll.) | [05 → Research Notes](05-research-notes/nvidia-nim-integration.md) |
| Roadmap implementasi & checklist fase | [06 → Roadmap](06-roadmap/README.md) |

---

## 📁 Struktur Dokumentasi

```
docs/
├── README.md                        ← (file ini)
│
├── 01-getting-started/
│   ├── installation.md              ← Install Python, Node.js, setup .env
│   ├── quick-start.md               ← Jalankan dalam 5 menit
│   ├── configuration.md            ← Penjelasan config.yaml & semua env var
│   └── cli-commands.md             ← CLI Reference & Fitur Otomatisasi (Autonomous)
│
├── 02-architecture/
│   ├── overview.md                  ← High-level diagram & alur sistem
│   ├── api-reference.md             ← Semua endpoint FastAPI
│   └── components.md               ← Teacher, RAG, Graph, DigitalTwin, dll.
│
├── 03-features/
│   ├── thesis-analyzer.md           ← Bedah TA: upload, analisis, revisi, jurnal
│   ├── research-agent.md            ← Autonomous research & recursive loop
│   ├── rag-chat.md                  ← RAG chat & knowledge graph
│   └── voice-agent.md              ← Voice agent (Nimble Pipecat + NVIDIA Riva)
│
├── 04-development/
│   ├── testing.md                   ← Cara jalankan test suite
│   └── pdf-qa-benchmark.md         ← Hasil benchmark PDF QA v1–v6
│
├── 05-research-notes/
│   ├── digital-twin.md              ← Digital Twin & language evolution
│   ├── qlora-pipeline.md            ← QLoRA hybrid training pipeline
│   └── nvidia-nim-integration.md   ← NIM API, RAG Nemotron, IDP agents
│
└── 06-roadmap/
    ├── README.md                    ← Indeks fase A–D & cara pakai checklist
    ├── phase-a-rag-foundation.md    ← Fase A: RAG + endpoint
    ├── phase-b-production-readiness.md
    ├── phase-c-distillation-edge.md
    ├── phase-d-ecosystem-bridge.md
    └── workflows/
        ├── phase-a/                 ← A.1, A.2, A.3
        ├── phase-b/                 ← B.1, B.2, B.3
        ├── phase-c/                 ← C.1, C.2, C.3
        └── phase-d/                 ← D.1–D.5
```

---

## 🗺️ Gambaran Singkat Sistem

**JAYA Research** adalah AI research assistant berbasis NVIDIA NIM. Sistem ini memiliki dua mode utama:

1. **Research Mode** — agen melakukan riset otonom: cari paper, sintesis temuan, hasilkan laporan
2. **Thesis Mode** — analisis Tugas Akhir: cek novelty, gap analysis, revisi draft, simulasi sidang

Teknologi utama: FastAPI (backend) · React (UI) · NVIDIA NIM (LLM inference) · FAISS (vector store) · ArXiv + Semantic Scholar (journal search)

---

## ⚠️ Aturan Dokumentasi

1. **Satu dokumen = satu topik.** Jangan mencampur instalasi dengan arsitektur.
2. **Selalu update `README.md` ini** saat menambah dokumen baru.
3. **Nama file**: lowercase, pisah dengan `-`, bahasa Inggris. Contoh: `api-reference.md`.
4. Dokumen riset internal simpan di `05-research-notes/` — jangan campur dengan panduan pengguna.
5. Jika dokumen terlalu panjang (>300 baris), pecah menjadi sub-dokumen.

---

*Terakhir diperbarui: Juli 2025 — JAYA Research v2.0*
