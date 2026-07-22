# Research Agent — Autonomous & Recursive Research

JAYA Research dapat melakukan riset akademis secara otonom: mencari paper, mensintesis temuan, dan menghasilkan laporan Markdown terstruktur — tanpa kamu perlu buka browser atau Google Scholar.

---

## Dua Mode Research

### 1. Autonomous Research (Single-Pass)

Cocok untuk: riset singkat, eksplorasi topik baru, overview cepat.

**Via UI:**
1. Buka halaman **Research**
2. Masukkan topik (misal: `"transformer architecture efficiency"`)
3. Opsional: tambahkan focus area (`"low-resource devices"`)
4. Klik **Start Research**

**Via API:**
```bash
curl -X POST "http://localhost:8000/research/autonomous" \
  -H "Content-Type: application/json" \
  -d '{"topic": "federated learning", "focus_areas": "privacy", "workspace_id": "default"}'
```

**Alur internal:**
```
Topic Input
    │
    ▼
Plan: LLM generates 3–5 sub-questions
    │
    ▼
Execute (parallel):
  ├── ArXiv search per sub-question
  ├── Semantic Scholar search
  └── RAG search (existing knowledge base)
    │
    ▼
Synthesize: LLM merges all findings
    │
    ▼
Output: Markdown report (saved to workspace)
```

---

### 2. Recursive Research (Multi-Pass)

Cocok untuk: riset mendalam, topik kompleks, butuh iterasi untuk validasi.

```bash
curl -X POST "http://localhost:8000/research/recursive" \
  -H "Content-Type: application/json" \
  -d '{"topic": "quantum computing optimization", "max_iterations": 3}'
```

**Alur internal:**
```
Iteration 1: Initial research
    │
    ▼ (jika temuan kurang memuaskan)
Iteration 2: Refine queries based on gaps
    │
    ▼ (jika masih kurang)
Iteration 3: Deep dive specific aspects
    │
    ▼
Final synthesis across all iterations
```

> [!IMPORTANT]
> `max_iterations` default = 3. Jangan set terlalu tinggi (> 5) karena akan memperbanyak API call ke NIM.

---

## Journal Search Langsung

Cari jurnal tanpa harus memulai research session:

```bash
curl -X POST "http://localhost:8000/research/journals" \
  -H "Content-Type: application/json" \
  -d '{"query": "graph neural network citation", "max_papers": 10}'
```

Hasilnya mencakup: title, authors, year, abstract, URL dari ArXiv dan Semantic Scholar.

---

## Hasil Research

Laporan disimpan ke workspace sebagai Markdown. Struktur laporan:

```markdown
# Research Report: [Topic]

## Executive Summary
...

## Key Findings
### Finding 1: ...
### Finding 2: ...

## Literature Analysis
...

## Research Gaps Identified
...

## Recommendations
...

## References
- [Paper Title] (ArXiv/Scholar link)
```

---

## Research Twin — Gabungan Research + Evolution

`research_twin.py` menggabungkan autonomous research dengan Digital Twin evolution loop. Sistem ini meriset teknik optimasi compiler secara otonom, lalu menerapkan temuannya ke mutasi kode.

```bash
python src/research/research_twin.py
```

> [!NOTE]
> Research Twin adalah modul eksperimental. Lihat detail di [Digital Twin](../05-research-notes/digital-twin.md).

---

## Tips Membuat Query Efektif

| Kurang baik | Lebih baik |
|---|---|
| `"AI"` | `"self-supervised learning for tabular data"` |
| `"machine learning healthcare"` | `"federated learning EHR privacy 2023"` |
| `"improve my thesis"` | `"knowledge distillation for edge deployment"` |

Semakin spesifik query, semakin relevan paper yang ditemukan.
