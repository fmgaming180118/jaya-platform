# Status Implementasi

**Snapshot:** 2 Agustus 2026
**Fokus:** membedakan bukti software lokal dari bukti mutu ilmiah dan produksi

Dokumen ini adalah dashboard kondisi aktual. Urutan pengerjaan berada di
[ROADMAP.md](ROADMAP.md), sedangkan gate ilmiah Phase A berada di
[ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md).

## Definisi kematangan

| Status | Arti |
|---|---|
| IDEA | Konsep belum dijadwalkan |
| PLANNED | Scope dan exit criteria sudah ditentukan |
| PROTOTYPE | Ada kode/demo, tetapi masih memakai asumsi atau simulasi |
| IMPLEMENTED | Jalur utama tersedia dan memiliki tes terarah |
| INTEGRATED | Terhubung end-to-end dengan dependency nyata |
| VERIFIED | Exit criteria, benchmark, keamanan, dan risiko utama telah diverifikasi |
| PRODUCTION | Verified, terobservasi, aman, terdokumentasi, dan memiliki rollback |

Label bukti yang dipakai bersama status kematangan:

| Label | Arti |
|---|---|
| `PASS_LOCAL` | Kontrak deterministik/offline lulus; tidak membuktikan mutu produksi |
| `PASS_REPRESENTATIVE` | Evaluasi lulus pada dataset representatif yang disetujui dan dapat diaudit |
| `BLOCKED_EXTERNAL` | Bukti memerlukan corpus, provider, reviewer, approval, compute, atau perangkat nyata |
| `SMOKE_ONLY` | Fixture kecil untuk memeriksa wiring/kontrak; bukan benchmark kualitas |

## Dashboard aktual

### CEL Pipeline Status (Area Utama)

| Area CEL | Status | Bukti aktif | Gap utama |
|---|---|---|---|
| Evidence acquisition | IMPLEMENTED / PASS_LOCAL | Ingestion, provenance, citation, source validation diuji offline | Dataset representatif dan corpus gold belum tersedia |
| Provenance | IMPLEMENTED / PASS_LOCAL | Citation membawa source ID/URI, page/span, chunk hash, score, license | Audit entailment dan review manusia belum tersedia |
| Knowledge gap detection | IMPLEMENTED / PASS_LOCAL | Offline acceptance contract menolak positive novelty tanpa evaluator | Corpus berlabel dan reviewer domain belum tersedia |
| Novelty detection | IMPLEMENTED / PASS_LOCAL | Offline acceptance contract tersedia; simulasi/unverified dilabeli | Evaluasi novelty pada corpus berlabel belum dilakukan |
| Hypothesis generation | IMPLEMENTED / PASS_LOCAL | Hipotesis grounded dengan evidence ID tersedia | Falsifiability review oleh manusia belum ada |
| Experiment design | IMPLEMENTED / PASS_LOCAL | ExperimentDesigner dengan acceptance criteria tersedia | Eksperimen empiris nyata belum dijalankan |
| Experiment execution | PROTOTYPE / BLOCKED_EXTERNAL | Sandbox runner dan ExperimentRunner tersedia | Data, etik/legal, compute, dan reproduksi nyata belum ada |
| Reproducibility | PROTOTYPE / BLOCKED_EXTERNAL | Validasi receipts ada; pipeline reproduksi tersedia | Reproduksi independen nyata belum dilakukan |
| Candidate artifact creation | IMPLEMENTED / PASS_LOCAL | `research_artifact.py` immutable, status CANDIDATE, `executable=false` | Artifact schema lengkap masih perlu provenance + benchmark nyata |
| Promotion gate | PROTOTYPE / BLOCKED | Gate komponen tersedia; boundary candidate-only aktif | Gate integrasi, human approval, canary nyata belum diverifikasi |
| Core integration | PROTOTYPE / BLOCKED | Boundary kontrak ada; direct mutation dilarang dan diuji | Kontrak versioned end-to-end belum ada |
| Regression detection | PROTOTYPE | Komponen ada | Observability produksi belum tersedia |
| Rollback | PROTOTYPE / BLOCKED | Konsep ada | Deployment drill rollback nyata belum diuji |
| JARVIS end-to-end | IDEA | Arah roadmap | Belum ada bukti apapun |

### Domain Adapter Status

| Adapter | Status | Bukti aktif | Gap utama |
|---|---|---|---|
| Thesis Analysis | IMPLEMENTED / PASS_LOCAL | Source extraction, sesi persisten, status, checksum, output provider berlabel tidak terverifikasi | Validasi novelty/gap/sintesis pada corpus nyata dan reviewer domain |
| Deep Research | IMPLEMENTED / PASS_LOCAL | Retrieval bounded, abstention, citation, job status diuji | Search provider nyata, audit kualitas, worker produksi |

### Infrastruktur

| Area | Status | Bukti aktif | Gap utama |
|---|---|---|---|
| Dokumentasi dan monorepo | VERIFIED | Dokumen kanonis di root, satu Git root, validator tersedia | Disiplin pembaruan pada setiap perubahan |
| API Research Phase A | IMPLEMENTED / PASS_LOCAL | Suite API+E2E `100 passed` | Deployment, observability, dan provider nyata belum diverifikasi |
| Knowledge graph | IMPLEMENTED | Graph dan tes komponen tersedia | Skala, migrasi schema, dan kualitas retrieval dunia nyata |
| Auto-finetune/LoRA | PROTOTYPE / BLOCKED_EXTERNAL | Boundary kandidat dan artefak lokal tersedia | Dataset, training, compute, evaluasi holdout, model card, approval nyata |
| JAYA Core reasoning/JayaIR | IMPLEMENTED | Source, tes unit, readiness contract, dan gate artefak tersedia | Model target final dan benchmark hardware |
| JAYA Agent | PROTOTYPE | API/tool boundary dan tes komponen tersedia | E2E dengan provider dan environment produksi |
| JAYA OS | PROTOTYPE | Capability sandbox dan runtime komponen tersedia | Ownership kernel legacy dan deployment target |
| JAYA Android | PROTOTYPE | Proyek, unit test, dan kontrol konfigurasi tersedia | Build APK, model, sync, dan perangkat fisik `BLOCKED_EXTERNAL` |

## Bukti audit aktif — 1 Agustus 2026

- Suite Research offline: `352 passed, 11 deselected`.
- Acceptance suite Phase A terarah: `194 passed`.
- Suite fokus API Phase A dan E2E: `100 passed`.
- Suite kontrak UI: `12 passed`; `npm run lint` dan production build lulus;
  `npm audit` melaporkan 0 vulnerability.
- Deep Research UI tidak memiliki klaim automatic Core application: hasil
  ditampilkan non-promotable, dengan provenance/citation dan identitas artefak
  bila tersedia. API key hanya hidup di memori runtime dan gate memakai operasi
  baca untuk verifikasi. Preview/download/export tetap terautentikasi, status
  index tesis tidak dipalsukan, dan UI evolution aktif hanya sebagai boundary
  `BLOCKED` tanpa transport mutasi. Renderer Electron memakai context isolation
  dan sandbox tanpa Node integration.
- Kontrak request, route audit, workspace containment, provider failure,
  abstention, citation, PDF, tesis, dan artefak deep research tercakup dalam tes
  lokal.
- `JAYA_RESEARCH/evaluation/rag_smoke_v2.json` adalah dataset sintetis
  `SMOKE_ONLY`; hasilnya hanya membuktikan harness dan memiliki
  `production_gate_passed=false` secara kontraktual.
- `rag_representative_v1.json` telah dihapus karena tidak memenuhi syarat
  representativeness. Seluruh klaim metrik dari dataset tersebut telah ditarik
  dan bukan bukti aktif.
- [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md) menetapkan software offline
  sebagai `PASS_LOCAL`, sedangkan kesiapan ilmiah Phase A tetap
  `BLOCKED_EXTERNAL`.

Angka tes adalah snapshot dari working tree lokal, bukan pengganti CI bersih.
Setiap klaim baru wajib menyertakan command, commit, konfigurasi, environment,
dan artefak hasil yang dapat diulang.

## Keputusan Phase A

| Lapisan | Status | Keputusan |
|---|---|---|
| Kontrak software offline | `PASS_LOCAL` | Boleh menyatakan fondasi kode bekerja pada suite lokal |
| Kontrak dan build UI | `PASS_LOCAL` | Suite kontrak 12 tes, lint, production build, dan audit dependency lokal lulus |
| Browser E2E, deployment, provider live | `BLOCKED_EXTERNAL` | Belum ada bukti run browser terhadap API ter-deploy dan dependency nyata |
| Harness RAG | `PASS_LOCAL / SMOKE_ONLY` | Boleh menguji wiring dan regresi kontrak, bukan mutu produksi |
| Dataset dan QA representatif | `BLOCKED_EXTERNAL` | Dataset representatif yang disetujui belum tersedia |
| Novelty/gap ilmiah | `BLOCKED_EXTERNAL` | Corpus berlabel dan reviewer domain belum tersedia |
| PDF representatif | `BLOCKED_EXTERNAL` | Corpus gold dan evaluasi provider nyata belum tersedia |
| Eksperimen empiris | `BLOCKED_EXTERNAL` | Data, etik/legal, compute, dan reproduksi nyata belum tersedia |
| Sintesis/citation ilmiah | `BLOCKED_EXTERNAL` | Audit entailment serta review manusia belum tersedia |
| Phase A keseluruhan | `IN PROGRESS / BLOCKED_EXTERNAL` | Belum boleh disebut selesai ilmiah, production-ready, atau publication-ready |

## Risiko prioritas

### P0 — klaim ilmiah melebihi bukti

Nilai dari fixture sintetis, output LLM, persona ahli, self-score, atau simulasi
tidak boleh diberi label representatif, empiris, verified, atau promotable.

### P0 — dataset representatif belum tersedia

Sampling frame, lisensi/provenance, label relevansi, reviewer, serta approval
dataset belum tersedia. Target QA 85% tetap merupakan exit gate, bukan hasil
yang sudah dicapai.

### P1 — dependency eksternal

OCR, pencarian akademik, evaluator novelty, compute eksperimen, model target,
dan perangkat nyata dapat unavailable. Sistem wajib mengembalikan status
bertipe dan tidak menyimpan pesan error sebagai pengetahuan.

### P1 — operasional produksi

Sebagian kontrak job dan persistence telah ada, tetapi queue/worker terpisah,
observability lintas proses, clean install, backup/restore, dan deployment drill
belum menjadi bukti produksi.

Browser E2E terhadap API ter-deploy, provider live, dan konfigurasi CORS target
juga belum dijalankan. Kelulusan contract test, lint, build, dan audit dependency
UI tetap merupakan bukti lokal, bukan bukti operasional produksi.

## Aturan kenaikan status

- PROTOTYPE → IMPLEMENTED: happy path dan failure path memiliki tes
  deterministik.
- IMPLEMENTED → INTEGRATED: dependency nyata terhubung end-to-end.
- INTEGRATED → VERIFIED: exit criteria, benchmark representatif, keamanan, dan
  reproduksi lulus.
- VERIFIED → PRODUCTION: deployment terobservasi, runbook/rollback diuji, dan
  maintainer menyetujui.

`PASS_LOCAL` tidak pernah otomatis menaikkan status menjadi `VERIFIED`.
Perubahan wajib dicatat juga di [ROADMAP.md](ROADMAP.md) dan
[CHANGELOG.md](CHANGELOG.md).
