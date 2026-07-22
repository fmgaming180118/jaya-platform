# Fase A — Checklist Eksekusi (Checkbox-Ready)

> **Cara pakai:** Copy ke GitHub Issues / Notion / Obsidian. Centang `[ ]` → `[x]` saat selesai.  
> **Konvensi:** `☐` = belum, `☑` = selesai, `⏳` = in progress, `🚫` = blocked.

---

## A.1 — NVIDIARAGClient Implementation

| ID | Task | Assignee | Est. | Status | Notes / Blocker |
|----|------|----------|------|--------|-----------------|
| A.1.1 | Create `src/rag/nvidia_rag_client.py` with class skeleton | | 0.5d | ☐ | |
| A.1.2 | Implement `embed()` → NVIDIA NIM embedding API | | 1d | ☐ | Need NIM endpoint + API key |
| A.1.3 | Implement `ingest_text()` → FAISS + SQLite | | 1d | ☐ | Depends on A.5.1 (schema) |
| A.1.4 | Implement `search()` with workspace filter | | 0.5d | ☐ | |
| A.1.5 | Add Nemotron reranker (optional, can defer to Phase B) | | 0.5d | ☐ | `rerank=True` param |
| A.1.6 | Error handling: retry, timeout, SSL, rate limit | | 0.5d | ☐ | Use `tenacity` or custom |

---

## A.2 — RAGClient Wrapper Refactor

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.2.1 | Refactor `src/rag/rag_client.py` → delegate to `NVIDIARAGClient` | | 0.5d | ☐ | |
| A.2.2 | Remove `evolution_memory.json` keyword search | | 0.25d | ☐ | Grep to confirm gone |
| A.2.3 | Add `workspace_id` param to all public methods | | 0.25d | ☐ | |
| A.2.4 | Verify backward compatibility (thesis_analyzer still works) | | 0.25d | ☐ | Run existing tests |

---

## A.3 — Missing API Endpoints

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.3.1 | `POST /ingest` in `research_api.py` | | 0.5d | ☐ | Pydantic schema required |
| A.3.2 | `POST /research/recursive` in `research_api.py` | | 1d | ☐ | Bounded recursion logic |
| A.3.3 | Create/update `src/api/schemas.py` with request/response models | | 0.5d | ☐ | |
| A.3.4 | Centralized error handling (HTTPException + structured logging) | | 0.5d | ☐ | |

---

## A.4 — Thesis Analyzer → RAG Integration

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.4.1 | Update `thesis_analyzer.py` upload → `RAGClient.ingest_text()` | | 0.5d | ☐ | |
| A.4.2 | Remove "ingest_text not available" warning | | 0.1d | ☐ | Log check |
| A.4.3 | `/thesis/chat` → `RAGClient.search(workspace_id=...)` | | 0.5d | ☐ | Grounded answer + citations |

---

## A.5 — FAISS Index & SQLite Metadata

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.5.1 | Design `rag_vault.db` schema + SQLAlchemy models (`src/rag/models.py`) | | 0.5d | ☐ | `chunks` table |
| A.5.2 | Migration script (Alembic or raw SQL) | | 0.5d | ☐ | |
| A.5.3 | FAISS global index + `workspace_id` metadata filter | | 1d | ☐ | Single `faiss_index.bin` |
| A.5.4 | Persist/load FAISS index to/from disk | | 0.5d | ☐ | Startup + shutdown hooks |
| A.5.5 | Cleanup old per-workspace index logic | | 0.25d | ☐ | Remove `faiss_index_{ws}.bin` |

---

## A.6 — Testing & Evaluation

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.6.1 | Unit test `NVIDIARAGClient` (mock NIM) | | 1d | ☐ | `test_nvidia_rag_client.py` |
| A.6.2 | Integration test: ingest → search → (delete) | | 1d | ☐ | `test_rag_integration.py` |
| A.6.3 | Create benchmark script `scripts/eval_rag_recall.py` | | 1d | ☐ | Ground truth from 3 thesis PDFs |
| A.6.4 | Run benchmark → recall@5 ≥ 0.80 | | 0.5d | ☐ | Record in this file |

---

## A.7 — Documentation & Changelog

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.7.1 | Update this CHECKLIST.md with final status | | 0.25d | ☐ | All ☑ |
| A.7.2 | Update root `CHANGELOG.md` with Phase A summary | | 0.25d | ☐ | |
| A.7.3 | Update `JAYA_RESEARCH/README.md` (remove "RAG not ready") | | 0.25d | ☐ | |

---

## Exit Criteria Verification (Final Gate)

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| EC1 | All A.1–A.7 tasks ☑ | | | ☐ |
| EC2 | `pytest JAYA_RESEARCH/tests/ -v` pass (incl. new tests) | | | ☐ |
| EC3 | `POST /ingest` returns 200 + chunk_id in Swagger UI | | | ☐ |
| EC4 | `POST /research/recursive` returns 200 + synthesis in Swagger UI | | | ☐ |
| EC5 | Upload PDF thesis → chat thesis answers grounded (manual test) | | | ☐ |
| EC6 | RAG recall@5 ≥ 0.80 on 3 thesis PDFs (benchmark script output) | | | ☐ |
| EC7 | Restart server → FAISS index loads, thesis data searchable | | | ☐ |
| EC8 | No "ingest_text not available" warning in logs | | | ☐ |

---

## Blocker / Risk Log

| Date | Blocker | Impact | Mitigation | Resolved |
|------|---------|--------|------------|----------|
| | | | | |

---

## Daily Standup Notes (Append-only)

```
YYYY-MM-DD: 
- Done: 
- Doing: 
- Blockers: 
```

---

> **Next Phase:** Setelah semua EC ☑ → [Fase B Checklist](../phase-B/CHECKLIST.md)