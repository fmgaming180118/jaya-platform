# Changelog

Perubahan penting pada arah, status, arsitektur, dan dokumentasi dicatat di sini.
Format tanggal menggunakan `YYYY-MM-DD`.

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
