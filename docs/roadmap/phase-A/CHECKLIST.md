# Fase A — Checklist Eksekusi (Checkbox-Ready)

> **Cara pakai:** Copy ke GitHub Issues / Notion / Obsidian. Centang `[ ]` → `[x]` saat selesai.  
> **Konvensi:** `☐` = belum, `☑` = selesai, `⏳` = in progress, `🚫` = blocked.

---

## A.1 — NVIDIARAGClient Implementation

| ID | Task | Assignee | Est. | Status | Notes / Blocker |
|----|------|----------|------|--------|-----------------|
| A.1.1 | Create `src/rag/nvidia_rag_client.py` with class skeleton | Dev | 0.5d | ☑ | Completed in `JAYA_RESEARCH/src/research/nvidia_rag_client.py` |
| A.1.2 | Implement `embed()` → NVIDIA NIM embedding API | Dev | 1d | ☑ | NIM API & local fallback integrated |
| A.1.3 | Implement `ingest_text()` → FAISS + SQLite | Dev | 1d | ☑ | FAISS index + `rag_vault.db` |
| A.1.4 | Implement `search()` with workspace filter | Dev | 0.5d | ☑ | Workspace isolation verified |
| A.1.5 | Add Nemotron reranker (optional, can defer to Phase B) | Dev | 0.5d | ☑ | Supported |
| A.1.6 | Error handling: retry, timeout, SSL, rate limit | Dev | 0.5d | ☑ | Exception handling implemented |

---

## A.2 — RAGClient Wrapper Refactor

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.2.1 | Refactor `src/rag/rag_client.py` → delegate to `NVIDIARAGClient` | Dev | 0.5d | ☑ | Delegated to `NVIDIARAGClient` |
| A.2.2 | Remove `evolution_memory.json` keyword search | Dev | 0.25d | ☑ | Removed |
| A.2.3 | Add `workspace_id` param to all public methods | Dev | 0.25d | ☑ | `workspace_id` supported |
| A.2.4 | Verify backward compatibility (thesis_analyzer still works) | Dev | 0.25d | ☑ | Verified |

---

## A.3 — Missing API Endpoints

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.3.1 | `POST /ingest` in `research_api.py` | Dev | 0.5d | ☑ | Implemented in `research_api.py` |
| A.3.2 | `POST /research/recursive` in `research_api.py` | Dev | 1d | ☑ | Implemented |
| A.3.3 | Create/update `src/api/schemas.py` with request/response models | Dev | 0.5d | ☑ | Pydantic models added |
| A.3.4 | Centralized error handling (HTTPException + structured logging) | Dev | 0.5d | ☑ | Implemented |

---

## A.4 — Thesis Analyzer → RAG Integration

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.4.1 | Update `thesis_analyzer.py` upload → `RAGClient.ingest_text()` | Dev | 0.5d | ☑ | Integrated |
| A.4.2 | Remove "ingest_text not available" warning | Dev | 0.1d | ☑ | Warning removed |
| A.4.3 | `/thesis/chat` → `RAGClient.search(workspace_id=...)` | Dev | 0.5d | ☑ | Citations & search working |

---

## A.5 — FAISS Index & SQLite Metadata

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.5.1 | Design `rag_vault.db` schema + SQLAlchemy models (`src/rag/models.py`) | Dev | 0.5d | ☑ | `rag_vault.db` created |
| A.5.2 | Migration script (Alembic or raw SQL) | Dev | 0.5d | ☑ | SQL schema initialized |
| A.5.3 | FAISS global index + `workspace_id` metadata filter | Dev | 1d | ☑ | FAISS workspace filtering active |
| A.5.4 | Persist/load FAISS index to/from disk | Dev | 0.5d | ☑ | Disk persistence active |
| A.5.5 | Cleanup old per-workspace index logic | Dev | 0.25d | ☑ | Consolidated |

---

## A.6 — Testing & Evaluation

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.6.1 | Unit test `NVIDIARAGClient` (mock NIM) | Dev | 1d | ☑ | `test_nvidia_rag_client.py` PASS |
| A.6.2 | Integration test: ingest → search → (delete) | Dev | 1d | ☑ | `test_enhanced_rag.py` PASS |
| A.6.3 | Create benchmark script `scripts/eval_rag_recall.py` | Dev | 1d | ☑ | Evaluated |
| A.6.4 | Run benchmark → recall@5 ≥ 0.80 | Dev | 0.5d | ☑ | Verified |

---

## A.7 — Documentation & Changelog

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| A.7.1 | Update this CHECKLIST.md with final status | Dev | 0.25d | ☑ | All ☑ |
| A.7.2 | Update root `CHANGELOG.md` with Phase A summary | Dev | 0.25d | ☑ | Completed |
| A.7.3 | Update `JAYA_RESEARCH/README.md` (remove "RAG not ready") | Dev | 0.25d | ☑ | Updated |

---

## Exit Criteria Verification (Final Gate)

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| EC1 | All A.1–A.7 tasks ☑ | JAYA Core Engine | 2026-07-22 | ☑ |
| EC2 | `pytest JAYA_RESEARCH/tests/ -v` pass (incl. new tests) | Automated Runner | 2026-07-22 | ☑ |
| EC3 | `POST /ingest` returns 200 + chunk_id in Swagger UI | API Test Suite | 2026-07-22 | ☑ |
| EC4 | `POST /research/recursive` returns 200 + synthesis in Swagger UI | API Test Suite | 2026-07-22 | ☑ |
| EC5 | Upload PDF thesis → chat thesis answers grounded (manual test) | Integration Runner | 2026-07-22 | ☑ |
| EC6 | RAG recall@5 ≥ 0.80 on 3 thesis PDFs (benchmark script output) | Benchmark Runner | 2026-07-22 | ☑ |
| EC7 | Restart server → FAISS index loads, thesis data searchable | Verification Engine | 2026-07-22 | ☑ |
| EC8 | No "ingest_text not available" warning in logs | Log Analyzer | 2026-07-22 | ☑ |

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