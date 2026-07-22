# Arsitektur Sistem JAYA Research

## High-Level Overview

JAYA Research adalah sistem modular berlapis. Setiap lapisan punya tanggung jawab tunggal.

```
┌─────────────────────────────────────────────────────┐
│                  UI Dashboard (React)                │
│        Port 5173 — Vite Dev Server                  │
└─────────────────────┬───────────────────────────────┘
                      │  HTTP (REST API)
┌─────────────────────▼───────────────────────────────┐
│              FastAPI Backend                        │
│        src/network/research_api.py : 8000           │
│  ┌─────────────┬──────────────┬──────────────────┐  │
│  │  Research   │    Thesis    │      Chat        │  │
│  │  Endpoints  │   Endpoints  │    Endpoints     │  │
│  └──────┬──────┴──────┬───────┴────────┬─────────┘  │
└─────────┼─────────────┼────────────────┼────────────┘
          │             │                │
┌─────────▼─────────────▼────────────────▼────────────┐
│              Core Modules (src/)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │   Teacher    │  │  RAG Client  │  │   Graph   │  │
│  │ (NIM Client) │  │ (FAISS+Embed)│  │(Knowledge)│  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
└─────────┼─────────────────┼────────────────┼────────┘
          │                 │                │
┌─────────▼─────────────────▼────────────────▼────────┐
│              External Services                      │
│  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │   NVIDIA NIM     │  │  Academic Sources        │  │
│  │  - LLM (NemoTron)│  │  - ArXiv API            │  │
│  │  - Embeddings    │  │  - Semantic Scholar API  │  │
│  │  - Riva STT/TTS  │  │  - DuckDuckGo Search    │  │
│  └──────────────────┘  └──────────────────────────┘  │
└──────────────────────────────────────────────────────┘
```

---

## Alur Data

### Alur: Research Request

```
User input topic
      │
      ▼
ResearchAgent.plan()        ← LLM generates sub-questions
      │
      ▼
ParallelQueryExecutor       ← ArXiv + Scholar + RAG (concurrent)
      │
      ▼
SynthesisWriter             ← LLM merges findings
      │
      ▼
Markdown Report             ← Saved to workspace
```

### Alur: Thesis Upload & Analysis

```
PDF Upload (multipart)
      │
      ▼
_extract_pdf_text()         ← PyMuPDF → pdfplumber → PyPDF2 (fallback)
      │
      ▼
RAG Ingest                  ← Chunked → Embedded → FAISS
      │
      ▼
Background Analysis Task:
  1. Meta extraction (LLM)
  2. NoveltyChecker (ArXiv + Scholar)
  3. GapFinder (citation network)
  4. ReviewerAgent (critique)
  5. DefenseQuestions (LLM)
      │
      ▼
Session Store (_thesis_sessions dict)
      │
      ▼
Frontend polls /thesis/status/{id}
```

---

## Batas Domain

| Domain | Tanggung Jawab | Dilarang |
|---|---|---|
| `src/network/` | HTTP routing, request validation | Business logic langsung |
| `src/research/` | Research orchestration | Import dari `src/network/` |
| `src/research/academic/` | Academic analysis modules | Akses database langsung |
| `src/teacher.py` | NVIDIA NIM interface | State persistence |

> [!IMPORTANT]
> Jangan buat import lintas domain. `src/research/` tidak boleh import dari `src/network/`.

---

## Prinsip Desain

1. **Bounded recursion** — Semua loop rekursif harus punya batas iterasi dan timeout
2. **Stateless endpoints** — Session state disimpan di `_thesis_sessions` dict (bukan database); acceptable untuk MVP
3. **Fallback chain** — Setiap external call punya fallback (PyMuPDF → pdfplumber → PyPDF2)
4. **Artifact-first** — Output utama adalah file Markdown/JSON yang reproducible, bukan side effects

---

**Selanjutnya:** [API Reference →](api-reference.md) | [Components Detail →](components.md)
