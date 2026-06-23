# Alur Pengerjaan: PRD & SRS untuk `JAYA_CORE`

Versi: 0.1
Tanggal: 2026-05-30

## Tujuan
Dokumen ini menjabarkan alur pengerjaan, pembagian tugas, dan jadwal singkat untuk menyelesaikan PRD dan SRS `JAYA_CORE`, dilanjutkan dengan pemodelan proses dan desain basis data.

## Ringkasan Alur
1. Discovery & Requirements Gathering (1 w)
   - Kumpulkan use-case, device targets (phone, laptop, embedded), dan constraint teknis.
   - Output: daftar use-case prioritas, device profiles.

2. Draft PRD (1 w)
   - Buat PRD yang mencakup tujuan produk, MVP, success metrics, roadmap.
   - Output: `docs/PRD_JAYA_CORE.md` (draft).

3. Draft SRS (1–2 w)
   - Uraikan kebutuhan fungsional/non-fungsional, interface, data models, dan acceptance criteria.
   - Output: `docs/SRS_JAYA_CORE.md` (draft).

4. Review & Iterate (1 w)
   - Stakeholder review: core maintainers, research leads, security.
   - Perbaiki PRD/SRS sampai disetujui (minor/major review cycles).

5. Process Modeling (1 w)
   - Definisikan flow kerja E2E: device offline flows, sync flows, aggregation, merge.
   - Output: `docs/PROCESS_MODEL.md` (diagram + pseudocode).

6. Database Design & Data Contracts (1 w)
   - Rancang skema sentral untuk delta, overlays, provenance, dan audit logs.
   - Output: `docs/DB_DESIGN.md` (ERD + sample DDL).

7. Implementation Planning (1 w)
   - Breakdown tasks ke user stories, estimasi, dan sprint backlog.

## Roles & Tanggung Jawab
- Product Owner: menetapkan prioritas dan keputusan trade-off.
- Core Maintainers: verifikasi teknis PRD/SRS dan acceptance criteria.
- Research Leads: menyuplai contoh artefak riset dan kebutuhan promosi.
- Security/DevOps: review sync protocol, encryption, dan deployment.

## Deliverables & Acceptance
- Semua dokumen di `docs/` dengan versi dan tanggal.
- Setiap deliverable harus memiliki acceptance checklist (security, perf, compatibility).

## Komunikasi & Review Cadence
- Daily standup selama sprints; review mingguan untuk stakeholder.

## Risks & Mitigations
- Ambiguity in merge policy → early prototyping of overlay merge.
- Device heterogeneity → define device profiles and minimal viable footprint per profile.
