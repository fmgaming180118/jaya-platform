# Fase B — Checklist Eksekusi (Checkbox-Ready)

> **Cara pakai:** Copy ke GitHub Issues / Notion / Obsidian. Centang `[ ]` → `[x]` saat selesai.  
> **Konvensi:** `☐` = belum, `☑` = selesai, `⏳` = in progress, `🚫` = blocked.

---

## B.1 — Session Persistence (SQLite + Redis)

| ID | Task | Assignee | Est. | Status | Notes / Blocker |
|----|------|----------|------|--------|-----------------|
| B.1.1 | Design `thesis_sessions` schema + SQLAlchemy model (`src/academic/models.py`) | | 0.5d | ☐ | |
| B.1.2 | Create migration script (Alembic or raw SQL) | | 0.5d | ☐ | |
| B.1.3 | Implement `ThesisSessionManager` CRUD (replace in-memory dict) | | 1d | ☐ | |
| B.1.4 | Setup Celery/RQ + Redis (`src/workers/celery_app.py`) | | 1d | ☐ | Choose Celery (mature) or RQ (simpler) |
| B.1.5 | Create thesis analysis task chain: extract → meta → novelty → gap → review → defense | | 1.5d | ☐ | Celery `chain()` / `group()` |
| B.1.6 | Progress pub/sub to Redis channel `thesis:{session_id}:progress` | | 0.5d | ☐ | |
| B.1.7 | REST `GET /thesis/progress/{session_id}` + WS `/thesis/ws/{session_id}` | | 0.5d | ☐ | FastAPI WebSocket |

---

## B.2 — External API Resilience

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| B.2.1 | Create `ExternalAPIClient` base class with retry/timeout/circuit breaker | | 1d | ☐ | `src/external/api_client.py` |
| B.2.2 | Implement `ArXivClient` with SSL verify=True | | 0.5d | ☐ | Remove `verify=False` |
| B.2.3 | Implement `SemanticScholarClient` with rate limit handling | | 0.5d | ☐ | Respect `Retry-After` |
| B.2.4 | Implement `CrossrefClient` | | 0.5d | ☐ | |
| B.2.5 | Implement `GARUDAClient` | | 0.5d | ☐ | |
| B.2.6 | Circuit breaker: 5 failures → open 60s → half-open | | 0.5d | ☐ | `pybreaker` or custom |
| B.2.7 | Fallback chain in `LiteratureSearcher`: ArXiv → Semantic Scholar → Crossref → GARUDA | | 0.5d | ☐ | `src/academic/literature.py` |

---

## B.3 — Observability & Structured Logging

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| B.3.1 | Setup `structlog` / `python-json-logger` for JSON logs | | 0.5d | ☐ | `src/core/logging.py` |
| B.3.2 | Correlation ID middleware (request_id → worker headers) | | 0.5d | ☐ | FastAPI middleware + Celery task headers |
| B.3.3 | Prometheus metrics: requests, errors, latency, queue depth | | 0.5d | ☐ | `/metrics` endpoint |
| B.3.4 | Health check endpoints: `/health` (liveness) + `/health/ready` (readiness) | | 0.5d | ☐ | Check DB, Redis, NIM |

---

## B.4 — Formal RAG Evaluation (Continued from Phase A)

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| B.4.1 | Create ground truth: 10 thesis PDFs + 50 QA pairs each | | 2d | ☐ | `eval/ground_truth/{thesis_id}/qa.jsonl` |
| B.4.2 | Build `scripts/eval_rag_full.py` (recall@k, MRR, latency, groundedness) | | 1d | ☐ | Output JSON + HTML report |
| B.4.3 | Run eval → target recall@5 ≥ 0.85, MRR ≥ 0.70, p95 < 2s | | 0.5d | ☐ | Record in this file |
| B.4.4 | CI regression test (small sample) | | 0.5d | ☐ | `.github/workflows/rag-eval.yml` |

---

## B.5 — Export & Reporting

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| B.5.1 | `ThesisExporter.to_markdown(session_id)` — full report | | 0.5d | ☐ | `src/academic/exporter.py` |
| B.5.2 | `ThesisExporter.to_pdf(session_id)` — via WeasyPrint/pandoc | | 1d | ☐ | |
| B.5.3 | `ThesisExporter.to_json(session_id)` — raw results | | 0.25d | ☐ | |
| B.5.4 | Endpoint `GET /thesis/export/{session_id}?format=md|pdf|json` | | 0.5d | ☐ | File download response |

---

## B.6 — Testing & Quality Gate

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| B.6.1 | Unit test `ThesisSessionManager` CRUD + progress | | 0.5d | ☐ | `tests/test_thesis_session.py` |
| B.6.2 | Integration test: upload → background → WS progress → export | | 1d | ☐ | `tests/test_thesis_e2e.py` |
| B.6.3 | Chaos test: kill worker mid-analysis → resume from checkpoint | | 1d | ☐ | `tests/test_thesis_resilience.py` |
| B.6.4 | Load test: 10 concurrent thesis → p95 < 30s each | | 1d | ☐ | Locust/k6 script |

---

## B.7 — Documentation & Changelog

| ID | Task | Assignee | Est. | Status | Notes |
|----|------|----------|------|--------|-------|
| B.7.1 | Update this CHECKLIST.md final status | | 0.25d | ☐ | All ☑ |
| B.7.2 | Update root `CHANGELOG.md` Phase B summary | | 0.25d | ☐ | |
| B.7.3 | Update `JAYA_RESEARCH/README.md` — production-ready thesis workflow | | 0.25d | ☐ | Architecture diagram, API docs link |

---

## Exit Criteria Verification (Final Gate)

| # | Criteria | Verified By | Date | Status |
|---|----------|-------------|------|--------|
| EC1 | All B.1–B.7 tasks ☑ | | | ☐ |
| EC2 | `pytest JAYA_RESEARCH/tests/ -v` pass (incl. new tests) | | | ☐ |
| EC3 | Upload thesis → background analysis runs → progress real-time via WS | | | ☐ |
| EC4 | Kill worker mid-analysis → auto-resume from checkpoint | | | ☐ |
| EC5 | External API failure (ArXiv down) → fallback works → results returned | | | ☐ |
| EC6 | RAG recall@5 ≥ 0.85 on 10 thesis ground truth | | | ☐ |
| EC7 | Export MD/PDF/JSON works, files valid | | | ☐ |
| EC8 | `/health/ready` returns 200 only if DB+Redis+NIM ready | | | ☐ |
| EC9 | Structured JSON logs with correlation ID visible | | | ☐ |

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

> **Next Phase:** Setelah semua EC ☑ → [Fase C Checklist](../phase-C/CHECKLIST.md)