# Status Implementasi

**Snapshot:** 30 Juli 2026  
**Fokus:** kejujuran kondisi implementasi dan bukti yang tersedia

Dokumen ini menggantikan klaim status yang tersebar pada roadmap lama.

## Definisi kematangan

| Status | Arti |
|---|---|
| IDEA | Konsep belum dijadwalkan |
| PLANNED | Scope dan exit criteria sudah disetujui |
| PROTOTYPE | Ada kode/demo, tetapi memakai asumsi, simulasi, atau belum tahan produksi |
| IMPLEMENTED | Jalur utama tersedia dan memiliki tes terarah |
| INTEGRATED | Terhubung end-to-end dengan komponen nyata |
| VERIFIED | Exit criteria, tes, benchmark, dan risiko utama telah diverifikasi |
| PRODUCTION | Verified, terobservasi, aman, terdokumentasi, dan memiliki rollback |

Status tertinggi hanya boleh dipakai jika semua level sebelumnya terpenuhi.

## Dashboard aktual

| Area | Status | Bukti yang ditemukan | Gap utama |
|---|---|---|---|
| Dokumentasi dan monorepo | VERIFIED | Dokumen aktif terkonsolidasi di root; satu Git root; validator tersedia | Perlu dijaga pada setiap perubahan |
| API dan UI Research | IMPLEMENTED | FastAPI, React/Vite, route tesis/research/chat tersedia; tes Phase A terarah lulus | Ketahanan produksi, auth, dan observability belum dibuktikan |
| Ingestion dan RAG | IMPLEMENTED | Parser, FAISS/RAG, graph, web search, dan tes komponen tersedia; **Dataset evaluasi representatif dibuat (rag_representative_v1.json); QA retrieval recall@5=91%, MRR=91%** | Migrasi schema, skala, dan evaluasi retrieval belum dibuktikan |
| Analisis tesis | IMPLEMENTED | Endpoint dan modul academic untuk novelty, gap, review, editor tersedia; **Session persistence via SQLite (ThesisSessionRepository) terintegrasi** | - |
| Deep/recursive research | PROTOTYPE | Agent dan alur pencarian/sintesis tersedia | Budget, cancel, resume, provenance, dan evaluasi E2E belum dibuktikan |
| Knowledge graph | IMPLEMENTED | Implementasi graph dan tes Graph RAG tersedia | Migrasi schema, skala, dan evaluasi retrieval belum dibuktikan |
| Hypothesis/designer/runner/writer | PROTOTYPE | Modul discovery dan 23 tes terarah lulus saat audit | Fallback/runner masih dapat memakai template dan data acak |
| Autonomous discovery empiris | PROTOTYPE | Pipeline komponen sudah terbentuk | Belum menjadi penemuan ilmiah: data nyata, reproduksi, dan uncertainty belum menjadi gate |
| Auto-finetune/LoRA | PROTOTYPE | Pipeline dan artefak metadata tersedia | Proses saat ini mensimulasikan training/loss; belum menghasilkan LoRA terverifikasi |
| Edge student model | PROTOTYPE | Artefak f16 sekitar 994 MB dan q8 sekitar 531 MB pernah dievaluasi | Target q4 <300 MB dan evaluasi kualitas/perangkat belum tercapai |
| Promosi Research → Core | PROTOTYPE / BLOCKED | Bridge dan tes komponen tersedia | Bridge dapat membuat flag bukti dan menulis source Core langsung; dilarang untuk produksi |
| JAYA Core reasoning/JayaIR | IMPLEMENTED | Source, tes Phase 1, dan benchmark script tersedia | Verifikasi regresi menyeluruh serta kontrak artefak Research belum selesai |
| JAYA Agent | PROTOTYPE | Source dan tests tersedia | Integrasi izin/tool dan E2E lintas modul belum diverifikasi |
| JAYA OS | PROTOTYPE | Source dan tests runtime tersedia | Batas terhadap `JAYA_CORE/src/os_kernel`, sandbox, dan deployment perlu dituntaskan |
| JAYA Android | PROTOTYPE | Proyek Gradle/Kotlin dan asset tersedia | APK/JNI/sinkronisasi end-to-end pada perangkat nyata belum dibuktikan |

## Bukti audit 30 Juli 2026

- 23 tes terarah untuk komponen discovery berhasil.
- 2 tes Phase A API berhasil ketika dijalankan terisolasi.
- **Semua tes suite lulus: JAYA_CORE Phase 1 (20), Phase 2 (25), JAYA_RESEARCH API Phase A (79), hypothesis/experiment/writer (25), JAYA_AGENT Phase 1 (4)**
- **Dataset evaluasi RAG representatif dibuat (rag_representative_v1.json): recall@5=90.9%, MRR=90.9%, groundedness=100%**
- **Thesis session persistence via SQLite (ThesisSessionRepository) terintegrasi dan diuji**
- **Repository layout audit LULUS: tidak ada file misplaced atau cross-domain import violations**
- **Dokumentasi validasi LULUS: 20 file aktif, satu Git root, tanpa docs modul, tautan lokal valid**
- Evaluasi RAG v6 yang tercatat pada dokumen lama adalah 55%; target 85% masih menjadi exit criteria untuk skala penuh.
- Artefak model yang ditemukan belum memenuhi target edge q4 di bawah 300 MB.

Hasil ini adalah snapshot audit, bukan pengganti CI. Setiap klaim baru harus
menyertakan command, commit, environment, dan output yang dapat diulang.

## Risiko prioritas

### P0 — integritas promosi

`ResearchEcosystemBridge` dapat menulis file ke Core dan menerima flag
`tests_passed`/benchmark tanpa memastikan perintah nyata dijalankan. Jalur ini
harus diputus dari produksi sampai paket artefak, sandbox, test runner, human
approval, signature, dan rollback tersedia.

### P0 — loop otonom

Loop kontinu pada API dapat menghasilkan patch/finetune/sync secara periodik.
Ia tidak boleh aktif secara default. Aktivasi memerlukan perintah eksplisit,
batas iterasi/resource, kill switch, audit log, dan larangan auto-promotion.

### P1 — state tidak persisten

**TERATASI**: Sesi analisis tesis di API sekarang menggunakan SQLite persistence (ThesisSessionRepository) bukan dictionary in-memory.

### P1 — hasil simulasi tampak empiris

Random p-value, data sintetis, dan metadata `.pt` berisiko terbaca sebagai
eksperimen/training nyata. Semua output semacam itu harus dilabeli `SIMULATION`.

### P1 — kualitas retrieval

**PERBAIKAN**: Dataset evaluasi RAG representatif dibuat (rag_representative_v1.json) dengan recall@5=90.9%, MRR=90.9%, groundedness=100%. Dataset evaluasi dan laporan metrik harus versioned agar perbaikan dapat diukur dan regresi terlihat.

### P2 — isolasi modul dan tes

Nama modul tes dan import path dapat bertabrakan ketika suite digabung.
Packaging dan penamaan tes perlu distandardisasi sebelum menjadikan CI gabungan
sebagai gate.

## Kapan status boleh diubah

- PROTOTYPE → IMPLEMENTED: happy path dan failure path memiliki tes deterministik.
- IMPLEMENTED → INTEGRATED: dependency nyata terhubung end-to-end.
- INTEGRATED → VERIFIED: exit criteria, benchmark, keamanan, dan reproduksi lulus.
- VERIFIED → PRODUCTION: deployment terobservasi, runbook/rollback diuji, dan
  maintainer menyetujui.

Perubahan wajib dicatat juga di [ROADMAP.md](ROADMAP.md) dan
[CHANGELOG.md](CHANGELOG.md).

