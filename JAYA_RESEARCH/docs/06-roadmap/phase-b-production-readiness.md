# Fase B — Production Readiness

> **Estimasi:** 2–3 minggu  
> **Prasyarat:** [Fase A selesai](phase-a-rag-foundation.md)  
> **Tujuan:** Membuat sistem thesis & RAG siap dipakai berulang tanpa kehilangan state, dengan evaluasi kualitas terukur dan UX analisis background yang lebih baik.

---

## Konteks Masalah

| Area | Kondisi saat ini | Target Fase B |
|------|------------------|---------------|
| `_thesis_sessions` | In-memory dict | Persisten (SQLite/Redis) |
| Analisis thesis | Polling `/thesis/status` saja | SSE/WebSocket progress events |
| Benchmark QA | Manual, test file dihapus | Test suite otomatis + ground truth |
| External APIs | Tanpa retry/circuit breaker | Resilient calls ke ArXiv/Scholar |
| Akurasi RAG | ~60% (v6) | ≥85% menuju target v5 (90%) |

---

## Workflow Anak

| ID | Nama | Dokumen | Bergantung pada |
|----|------|---------|-----------------|
| **B.1** | Session Persistence | [b1-session-persistence.md](workflows/phase-b/b1-session-persistence.md) | Fase A |
| **B.2** | Progress Streaming | [b2-progress-streaming.md](workflows/phase-b/b2-progress-streaming.md) | B.1 |
| **B.3** | Formal Benchmark | [b3-formal-benchmark.md](workflows/phase-b/b3-formal-benchmark.md) | Fase A (paralel dengan B.1) |

**Urutan disarankan:** B.1 dan B.3 paralel → B.2 setelah B.1.

---

## Master Checklist Fase B

### B.1 — Session Persistence
- [ ] Semua item di [b1-session-persistence.md](workflows/phase-b/b1-session-persistence.md) selesai
- [ ] Restart server tidak menghapus session thesis aktif

### B.2 — Progress Streaming
- [ ] Semua item di [b2-progress-streaming.md](workflows/phase-b/b2-progress-streaming.md) selesai
- [ ] UI menampilkan langkah analisis real-time (5 langkah)

### B.3 — Formal Benchmark
- [ ] Semua item di [b3-formal-benchmark.md](workflows/phase-b/b3-formal-benchmark.md) selesai
- [ ] Akurasi QA ≥85% pada test set standar

### Verifikasi Integrasi Fase
- [ ] Upload → analyze → restart API → status session masih valid
- [ ] Progress analisis terlihat di UI tanpa refresh manual berlebihan
- [ ] `pytest` benchmark QA lulus di CI lokal
- [ ] Retry ArXiv/Scholar teruji (simulasi timeout)
- [ ] Dokumen `testing.md` diperbarui dengan instruksi baru

---

## Kriteria Selesai Fase B

Fase B **selesai** jika:

1. **Session thesis** bertahan setelah restart backend.
2. **Progress analisis** dapat di-stream ke frontend (minimal SSE).
3. **Test suite PDF QA** otomatis dengan ≥20 pertanyaan ground truth, akurasi ≥85%.
4. **Tidak ada** regresi fungsional dari Fase A.

---

## File Utama yang Terdampak

```
JAYA_RESEARCH/src/network/research_api.py           ← _thesis_sessions, SSE endpoint
JAYA_RESEARCH/src/research/academic/                ← novelty, literature (retry)
JAYA_RESEARCH/ui/src/pages/ThesisPage.jsx           ← progress UI
JAYA_RESEARCH/tests/                                ← benchmark suite baru
JAYA_RESEARCH/docs/04-development/testing.md
JAYA_RESEARCH/docs/04-development/pdf-qa-benchmark.md
```

---

## Metrik Keberhasilan

| Metrik | Target |
|--------|--------|
| Session recovery rate | 100% setelah restart |
| QA accuracy (test set) | ≥85% |
| Analisis thesis p95 latency | <10 menit (PDF ~100 halaman) |
| API external failure recovery | Retry 3x dengan backoff |

---

**Sebelumnya:** [Fase A](phase-a-rag-foundation.md) · **Selanjutnya:** [Fase C →](phase-c-distillation-edge.md)
