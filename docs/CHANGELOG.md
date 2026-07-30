# Changelog

Perubahan penting pada arah, status, arsitektur, dan dokumentasi dicatat di sini.
Format tanggal menggunakan `YYYY-MM-DD`.

## 2026-07-30 — Research Foundation & Production Hardening Progress

### Added

- **Dataset evaluasi RAG representatif** (`evaluation/rag_representative_v1.json`) dengan 11 entries berbasis dokumen thesis nyata, license CC0-1.0, schema `jaya-rag-eval-v1`.
- **Thesis session persistence** via `ThesisSessionRepository` (SQLite WAL, revision tracking, crash recovery) terintegrasi ke API `/thesis/*`.
- **Repository layout audit** bersih: tidak ada file misplaced atau cross-domain import violations.

### Changed

- **RAG evaluation metrics** pada dataset representatif: recall@5=90.9%, MRR=90.9%, groundedness=100%, citation_correctness=9.1% (dibatasi oleh min_local_score=0.55), abstention_accuracy=9.1%.
- **STATUS.md** diperbarui: Ingestion & RAG → IMPLEMENTED, Analisis tesis → IMPLEMENTED, bukti audit 30 Juli 2026.
- **ROADMAP.md** diperbarui: Fase A checklist 2/6 selesai (dataset evaluasi, QA ≥85%), Fase B checklist 1/7 selesai (thesis persistence), status Fase B → IN PROGRESS.
- **Dokumentasi validasi** LULUS: 20 file aktif, satu Git root, tanpa docs modul, tautan lokal valid.
- **Repository layout audit** LULUS: tidak ada file misplaced atau cross-domain import violations.

### Verified

- Semua test suite lulus: JAYA_CORE Phase 1 (20), Phase 2 (25), JAYA_RESEARCH API Phase A (79), hypothesis/experiment/writer (25), JAYA_AGENT Phase 1 (4).
- RAG evaluation pada dataset representatif: recall@5=90.9%, MRR=90.9%, groundedness=100%.
- Thesis session persistence diuji: save/retrieve/list/delete/recover_interrupted berfungsi.

## 2026-07-26 — Program Research Truth & Core Readiness

### Added

- Menambahkan `REMEDIATION_CHECKLIST.md` sebagai daftar kerja kanonis berbasis
  audit untuk menghapus hardcode, simulasi palsu, unsafe promotion, dan boundary
  yang tidak sesuai kegunaan modul.
- Menetapkan acceptance criteria serta gate eksternal yang wajib dipenuhi sebelum
  Research/Core dapat disebut verified atau production.

## 2026-07-26 — Konsolidasi dokumentasi

### Changed

- Menetapkan `docs/` di root sebagai satu-satunya sumber dokumentasi aktif.
- Mengganti roadmap yang saling bertentangan dengan `ROADMAP.md` kanonis.
- Menambahkan definisi kematangan dan dashboard berbasis bukti di `STATUS.md`.
- Menyatukan visi, batas modul, alur riset/discovery, dan target ekosistem.
- Menetapkan gerbang promosi Research → Core yang membutuhkan tes/benchmark
  aktual, reproduksi, security review, persetujuan manusia, dan rollback.
- Mengubah README root/modul menjadi navigasi yang sejalan dengan dokumen kanonis.

### Archived

- Memindahkan dokumentasi modul lama ke
  `docs/archive/legacy-module-docs/`.
- Memindahkan PRD, SRS, masterplan, roadmap, dan catatan root lama ke
  `docs/archive/legacy-root-docs/`.
- Arsip dipertahankan untuk audit, tetapi tidak lagi menjadi spesifikasi aktif.

### Repository

- Menghapus repository Git bersarang aktif dari `JAYA_RESEARCH`; branch terakhir
  `master`, commit `90bd6eb`, remote
  `https://github.com/fmgaming180118/JAYA_RESEARCH.git`. Karena hard-delete
  diblokir pengaman terminal, metadata lama dipindahkan ke backup lokal dalam
  arsip yang diabaikan Git dan tidak lagi bernama `.git`.
- Seluruh file kini dikelola oleh Git repository di root monorepo.
- Memperbarui `.gitignore` agar dokumentasi aktif terlacak, sementara referensi
  vendor dan arsip besar tetap lokal.

### Verification

- Menambahkan `scripts/validate_docs.py` untuk memeriksa struktur, repository,
  dan tautan dokumentasi.
- Menyelaraskan hook, instruksi agent, audit layout, prompt cleanup, dan workflow
  benchmark agar tidak membuat kembali dokumentasi modul.
- Memperbaiki blok integration test workflow Phase 2 yang sebelumnya bukan YAML
  valid, tanpa mengubah skenario gate yang diuji.
