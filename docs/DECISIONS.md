# Keputusan Arsitektur Aktif

Dokumen ini mencatat keputusan yang mengikat lintas modul. Rincian historis
tersimpan di arsip, tetapi status keputusan aktif hanya ditentukan di sini.

| ID | Keputusan | Status |
|---|---|---|
| ADR-001 | Repository dikelola sebagai satu monorepo dengan `.git` hanya di root | Accepted |
| ADR-002 | Seluruh dokumentasi aktif berada di `docs/` root | Accepted |
| ADR-003 | Modul tidak saling import internal; integrasi memakai kontrak publik/versioned | Accepted |
| ADR-004 | JayaIR Phase 1 v0.1 dibekukan sampai migration, compatibility test, benchmark, dan approval tersedia | Accepted |
| ADR-005 | Research menghasilkan paket artefak; tidak menulis source modul tujuan | Accepted |
| ADR-006 | Hasil sintetis/random wajib berstatus `SIMULATION` | Accepted |
| ADR-007 | Loop otonom default nonaktif dan membutuhkan consent, batas, audit, serta kill switch | Accepted |
| ADR-008 | Output benchmark/report runtime berada di `reports/`, bukan folder dokumentasi | Accepted |

## ADR-001 — Satu Git root

Seluruh modul adalah bagian dari satu lifecycle perubahan. Nested repository
menyebabkan status/commit berbeda dan membuat perubahan lintas modul sulit
ditelusuri. Metadata Git lama Research disimpan sebagai backup arsip nonaktif.

Konsekuensi:

- Command Git dari modul tetap mengarah ke root.
- Branch, commit, hook, dan CI dikelola di root.
- Modul tidak memiliki `.git` sendiri.

## ADR-002 — Satu dokumentasi aktif

Sebelumnya PRD, SRS, roadmap, dan checklist tersebar serta mengandung klaim
status berbeda. `docs/` root sekarang menjadi sumber tunggal; README modul hanya
menjadi pintu masuk.

Konsekuensi:

- Tidak ada `<MODULE>/docs/`.
- Status ditentukan `STATUS.md`; prioritas ditentukan `ROADMAP.md`.
- Laporan generated masuk `reports/`; dokumen lama masuk `docs/archive/`.

## ADR-003 — Boundary kontrak publik

Core, Research, Agent, OS, dan Android memiliki domain berbeda. Direct import
internal atau penulisan file lintas modul membuat coupling dan bypass review.

Konsekuensi:

- Interaksi runtime menggunakan API/message/artifact contract versioned.
- Perubahan kontrak memerlukan compatibility test dan review kedua modul.
- Dependency internal lintas modul dilarang.

## ADR-004 — JayaIR v0.1 dibekukan

JayaIR adalah kontrak antara intent/planning dan executor. Perubahan opcode atau
schema berisiko merusak kompatibilitas serta rollback.

Perubahan hanya diterima jika:

1. versi schema baru dan migration ditetapkan;
2. backward compatibility atau breaking change dijelaskan;
3. architecture, unit, regression, dan benchmark gates lulus;
4. maintainer Core menyetujui;
5. rollback diuji.

## ADR-005 — Evidence artifact promotion

Research tidak boleh mengubah source Core secara langsung. Paket promosi dan
seluruh gate dijelaskan di [GOVERNANCE.md](GOVERNANCE.md).

## Proses keputusan baru

1. Tambahkan baris ADR dengan ID berikutnya dan status `Proposed`.
2. Jelaskan konteks, opsi, trade-off, dampak keamanan, dan migration.
3. Dapatkan review owner terdampak.
4. Ubah menjadi `Accepted` atau `Rejected`.
5. Selaraskan Architecture, Status, Roadmap, dan Changelog.

Keputusan `Accepted` tidak diubah diam-diam. Penggantinya mendapat ID baru dan
keputusan lama ditandai `Superseded by ADR-xxx`.

