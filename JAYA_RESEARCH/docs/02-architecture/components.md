# Komponen Sistem — Detail Teknis

Dokumen ini menjelaskan setiap modul utama di `src/`.

---

## `src/teacher.py` — NVIDIA NIM Interface

Wrapper utama untuk semua panggilan ke NVIDIA NIM API.

```python
from src.teacher import Teacher

brain = Teacher(model_type="reasoning")  # atau "standard", "chat"
response = brain.ask("Jelaskan konsep RAG")
response = brain.generate_completion(prompt)
```

**Model types:**
- `reasoning` → Nemotron Super (thinking mode aktif) — untuk analisis kompleks
- `standard` → Llama 3.1 — untuk chat dan penulisan
- `chat` → model chat ringan

**Konfigurasi** diambil otomatis dari `.env` (`NVIDIA_API_KEY`, `NVIDIA_LLAMA31_MODEL`, dll.)

---

## `src/research/rag_client.py` — RAG Engine

Mengelola vector store FAISS + embedding NVIDIA.

```python
from src.research.rag_client import RAGClient

client = RAGClient(workspace_id="default")
client.ingest_text("teks dokumen...", source="paper.pdf")
results = client.search("query", top_k=5)
# results: [{"snippet": "...", "score": 0.92, "source": "paper.pdf"}, ...]
```

**Alur ingest:**
1. Split teks menjadi chunk (ukuran dari `RAG_CHUNK_SIZE`)
2. Embed setiap chunk via NVIDIA embedding model
3. Simpan ke FAISS index di `workspaces/{id}/vector_store/`

---

## `src/research/academic/novelty_checker.py` — Novelty Checker

Mengecek apakah topik penelitian masih novel vs literatur yang ada.

```python
from src.research.academic.novelty_checker import NoveltyChecker

checker = NoveltyChecker()
result = checker.check_novelty(topic, abstract)
# result: {"is_novel": True, "confidence": 0.78, "reasoning": "..."}
```

**Cara kerja:**
1. Search ArXiv + Semantic Scholar untuk topik
2. Embed topik + setiap paper yang ditemukan
3. Hitung cosine similarity
4. LLM reasoning: "apakah penelitian ini berbeda cukup?"

---

## `src/research/academic/gap_finder.py` — Gap Finder

Mengidentifikasi research gap dari jaringan sitasi.

```python
from src.research.academic.gap_finder import GapFinder

finder = GapFinder()
report = finder.find_gaps(topic, abstract)
# returns: Markdown string berisi gap analysis
```

---

## `src/research/academic/reviewer.py` — Reviewer Agent

Menghasilkan kritik peer-review dan pertanyaan sidang.

```python
from src.research.academic.reviewer import ReviewerAgent

reviewer = ReviewerAgent()
critique = reviewer.critique(abstract, methodology)
defense_qs = reviewer.generate_defense_questions(title, abstract, topic)
```

---

## `src/research/academic/editor.py` — Academic Editor

Merevisi draft berdasarkan instruksi dan critique.

```python
from src.research.academic.editor import AcademicEditor

editor = AcademicEditor()
revised = editor.revise_chapter(draft, critique, context=topic)
```

---

## `src/research/academic/literature.py` — Literature Search

Client untuk ArXiv dan Semantic Scholar.

```python
from src.research.academic.literature import ArxivClient, SemanticScholarClient

arxiv = ArxivClient()
papers = arxiv.search_papers("federated learning", max_results=5)

scholar = SemanticScholarClient()
papers = scholar.search_papers("graph neural network", max_results=5)
```

**Paper format:**
```python
{
  "title": str,
  "authors": List[str],
  "year": str,
  "abstract": str,
  "url": str,
  "id": str,
}
```

---

## `src/research/agent.py` — Research Agent

Orchestrator untuk autonomous dan recursive research.

```python
from src.research.agent import ResearchAgent

agent = ResearchAgent(workspace_id="default")
report = agent.research(topic="Large Language Models", focus_areas="efficiency")
```

**Alur internal:**
1. `plan()` — LLM generate 3–5 sub-question
2. `execute_parallel()` — fetch papers untuk setiap sub-question
3. `synthesize()` — LLM tulis laporan akhir
4. `save()` — simpan ke workspace

---

## `src/network/research_api.py` — FastAPI App

Entry point utama backend. Tidak boleh mengandung business logic — hanya routing.

Semua endpoint didokumentasikan di → [API Reference](api-reference.md)

---

## Digital Twin Modules (Experimental)

| File | Fungsi |
|---|---|
| `src/digital_twin_compiler.py` | Evolusi bahasa `.jaya` + compiler |
| `src/generate_training_data.py` | Generate dataset fine-tuning dari hasil evolusi |
| `src/research/research_twin.py` | Kombinasi autonomous research + compiler evolution |

Dokumentasi lengkap → [Digital Twin](../05-research-notes/digital-twin.md)
