# JAYA Roadmap — Dokumentasi Fase A, B, C, D

> **Sumber:** Insight dari analisis Cursor AI (2026-07-02)  
> **Tujuan:** Mengubah JAYA dari prototype penelitian menjadi sistem produksi yang *reliable*, *offline-first*, dan siap demo ke stakeholder akademik.

---

## Ringkasan Fase

| Fase | Fokus Utama | Durasi Est. | Output Utama |
|------|-------------|-------------|--------------|
| **A** | **Fix RAG & API Completeness** | 1–2 minggu | RAG semantic berfungsi, endpoint `/ingest` & `/research/recursive` live, thesis chat grounded |
| **B** | **Production Hardening Thesis** | 2–3 minggu | Session persist (SQLite), progress streaming, retry/circuit-breaker, evaluasi formal RAG |
| **C** | **Distillation Pipeline & Local Student** | 1 bulan | Dataset 500–1k sampel, eval holdout, GGUF q4_k_m <300 MB, router lokal↔cloud |
| **D** | **Bridge CORE↔RESEARCH + Advanced Features** | Ongoing | Unified chat router, LAN sync knowledge, Evolution UI, multimodal, voice, citation graph |

---

## Prinsip Umum

1. **Definition of Done (DoD) per task**: unit test + integration test + update docs (`docs/roadmap/phase-*/CHECKLIST.md`).
2. **Branching**: `feature/phase-A-<task>`, `feature/phase-B-<task>`, dst. Merge via PR dengan review minimal 1 orang.
3. **CI Gate**: Semua PR harus lulus `pytest JAYA_RESEARCH/tests/ -v` dan `pytest JAYA_CORE/tests/ -v` (phase-1 & phase-2 gates).
4. **Dokumentasi hidup**: Setiap task selesai → update `CHECKLIST.md` fase terkait + catatan di `CHANGELOG.md`.

---

## Navigasi Cepat

- [Fase A — RAG & API Completeness](phase-A/README.md)
- [Fase B — Production Hardening](phase-B/README.md)
- [Fase C — Distillation & Local Student](phase-C/README.md)
- [Fase D — Bridge & Advanced](phase-D/README.md)

---

## Metrik Sukses Keseluruhan

| Metrik | Target Fase A | Target Fase B | Target Fase C | Target Fase D |
|--------|---------------|---------------|---------------|---------------|
| RAG Recall@5 (thesis PDF) | ≥ 0.80 | ≥ 0.85 | ≥ 0.90 | ≥ 0.92 |
| Thesis chat latency (p95) | < 3 s | < 2 s | < 1.5 s (lokal) | < 1 s (hybrid) |
| Session survival restart | ❌ | ✅ SQLite | ✅ + Redis | ✅ + LAN sync |
| Student model size | — | — | q4_k_m < 300 MB | q4_k_m + q8_0 |
| Offline capability | ❌ | ❌ | ✅ chat dasar | ✅ full pipeline |
| Evolution gate pass rate | — | — | 100% (2/2 policy) | 100% (≥4 policy) |

---

> **Catatan**: Setiap fase memiliki file `CHECKLIST.md` terpisah yang berisi daftar tugas atomik (checkbox-ready) untuk *sprint planning* harian.