# Kontrak Penerimaan Phase A - JAYA Research

**Status dokumen:** kanonis  
**Status Phase A:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk kesiapan ilmiah  
**Pemilik:** maintainer JAYA Research bersama penanggung jawab ilmiah  
**Terakhir diverifikasi:** 1 Agustus 2026

Dokumen ini menentukan kapan fondasi penelitian JAYA boleh disebut lulus.
Ketersediaan kelas, endpoint, keluaran model, atau tes dengan data sintetis bukan
bukti mutu penelitian. Phase A baru selesai secara ilmiah setelah gate lokal,
gate dataset representatif, dan review manusia yang diwajibkan di bawah ini
semuanya memiliki bukti yang dapat diaudit.

## 1. Arti status gate

| Status | Arti | Boleh digunakan untuk |
|---|---|---|
| `PASS_LOCAL` | Kontrak deterministik/offline lulus pada kode saat ini. Mock atau fake provider hanya menguji batas sistem. | Menyatakan perilaku software lokal bekerja. |
| `PASS_REPRESENTATIVE` | Evaluasi lulus pada dataset versioned, berlisensi, memiliki sampling frame, dan disetujui sebagai representatif. Run terikat commit, kode, konfigurasi, runner, dan environment. | Menyatakan hasil pada populasi evaluasi yang didefinisikan, bukan klaim universal. |
| `BLOCKED_EXTERNAL` | Implementasi lokal tersedia, tetapi bukti membutuhkan corpus nyata, akses provider, reviewer domain, persetujuan etik/legal, atau run independen. | Melacak pekerjaan yang tidak boleh ditutup dengan simulasi. |
| `FAIL` | Satu atau lebih invariant atau ambang yang diwajibkan gagal. | Menghentikan promosi dan memulai remediasi. |

Aturan status:

1. `PASS_LOCAL` tidak otomatis menjadi `PASS_REPRESENTATIVE`.
2. `BLOCKED_EXTERNAL` bukan kegagalan implementasi, tetapi Phase A tidak boleh
   disebut selesai secara ilmiah selama status ini masih ada.
3. LLM tidak boleh menjadi hakim kualitas, domain expert, pemberi persetujuan,
   atau pengganti reviewer manusia.
4. Persona "expert", self-score model, majority vote model, dan expert
   simulation bukan bukti penerimaan.
5. Data simulasi hanya membuktikan jalur rekayasa. Data itu tidak boleh diberi
   label empiris, menaikkan keyakinan ilmiah, atau membuka publication gate.

## 2. Bukti yang sah

Setiap bukti gate harus menyimpan:

- command lengkap dan exit code;
- commit SHA serta SHA-256 kode/config yang dievaluasi;
- versi Python/dependency, runner ID, dan environment ID;
- ID, versi, SHA-256, provenance, lisensi, dan sampling frame dataset;
- hasil per kasus, metrik agregat, kegagalan, dan status abstain;
- untuk gate manusia: rubric, reviewer domain nyata, waktu review, keputusan,
  konflik, dan receipt persetujuan.

Bukti berikut tidak sah untuk menutup gate ilmiah:

- prompt atau jawaban LLM tanpa evidence ID;
- angka benchmark yang tidak memiliki dataset dan report aktif;
- hasil smoke fixture yang dinamai "representatif";
- referensi, bibliografi, hasil eksperimen, atau approval yang dibuat otomatis;
- screenshot tanpa data mentah dan command reproduksi;
- jumlah tes dari run lama yang tidak dapat dijalankan ulang.

## 3. Invariant lintas komponen

Semua komponen Phase A wajib memenuhi invariant berikut.

| ID | Invariant lokal | Syarat lulus |
|---|---|---|
| `A-TRUTH-001` | Tidak ada klaim positif dari ketiadaan hasil/provider failure. | Empty result dan provider failure menghasilkan status `indeterminate`, `ABSTAINED`, atau error bertipe. |
| `A-TRUTH-002` | Evidence ID tidak boleh dibuat oleh generator. | Setiap ID pada keputusan/claim merupakan subset ID input yang diberikan. ID asing membuat output ditolak. |
| `A-TRUTH-003` | Simulasi tidak pernah menjadi bukti empiris. | `evidence_kind=SIMULATION`, tidak promotable, dan hasil deterministik untuk seed yang sama. |
| `A-TRUTH-004` | Reproduksi bukan approval publikasi. | Draft empiris hasil reproduksi tetap `publication_ready=false` dan `human_review_required=true`. |
| `A-TRUTH-005` | Provider opsional gagal secara eksplisit. | Tidak ada fallback template/fakta/sample tersembunyi; error provider tidak dikembalikan sebagai konten ilmiah. |
| `A-TRUTH-006` | Artefak tampered ditolak. | Digest dataset, source chunk, result receipt, dan report diverifikasi sebelum dipakai. |
| `A-TRUTH-007` | Promotion tidak berasal dari Research secara langsung. | Output Phase A hanya candidate/evidence package dan tetap melewati review serta gate Core. |

## 4. Gate per komponen

### 4.1 Novelty checker

Implementasi: [novelty_checker.py](../JAYA_RESEARCH/src/research/academic/novelty_checker.py).

Gate lokal `A-NOV-LOCAL`:

- query memiliki minimal tiga keyword teknis yang dinormalisasi;
- minimal dua provider literatur independen menyelesaikan pencarian; coverage di
  bawah batas menghasilkan `indeterminate`;
- hasil kosong tidak menjadi bukti novelty;
- penolakan lexical hanya boleh menunjuk evidence ID yang ditemukan;
- keputusan positif evaluator harus berupa data terstruktur, confidence pada
  rentang 0 sampai 1, dan seluruh `decision_evidence_ids` merupakan subset
  evidence hasil pencarian;
- keluaran malformed atau ID asing menjadi `indeterminate`;
- keputusan novelty tidak pernah memberi promotion approval.

Gate representatif `A-NOV-REP`:

- benchmark minimal 100 kasus berlabel dari minimal tiga domain dan bahasa
  Indonesia serta Inggris, dengan metode sampling dan timestamp pencarian;
- known-prior control set memiliki false-novelty rate maksimal 5%;
- precision keputusan positif minimal 90%;
- coverage, abstention rate, dan disagreement antar reviewer dilaporkan, bukan
  dikeluarkan dari denominator secara diam-diam;
- setiap label gold ditinjau minimal dua reviewer domain nyata dan konflik
  diselesaikan manusia.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk `A-NOV-REP` karena benchmark
representatif dan review domain belum tersedia.

### 4.2 Gap finder

Implementasi: [gap_finder.py](../JAYA_RESEARCH/src/research/academic/gap_finder.py).

Gate lokal `A-GAP-LOCAL`:

- analisis sebelum search berstatus `SEARCH_NOT_RUN`;
- pencarian kosong berstatus `INSUFFICIENT_EVIDENCE`;
- satu cluster terhubung tidak menghasilkan structural-hole candidate;
- cluster terputus hanya menghasilkan `CANDIDATE_REQUIRES_REVIEW`, bukan
  verified gap;
- setiap candidate membawa ID node/citation yang benar-benar berada di graph;
- depth, jumlah seed, dan citations per seed dibatasi;
- graph di-reset antar topik dan `promotion_eligible=false`.

Gate representatif `A-GAP-REP`:

- minimal 30 pencarian topik dari minimal tiga domain menggunakan search log,
  query, waktu, provider, dan corpus snapshot yang dapat diulang;
- 100% candidate yang diterima memiliki jalur evidence yang dapat dibuka;
- tidak ada structural hole yang otomatis disebut novel/verified gap;
- setiap gap yang hendak dipakai ditinjau minimal dua expert domain nyata,
  dengan agreement minimal 80% atau adjudication tercatat;
- coverage bias, indexing gap, istilah alternatif, dan citation delay dicatat.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk corpus snapshot dan review
domain `A-GAP-REP`.

### 4.3 Hypothesis generator

Implementasi: [hypothesis_generator.py](../JAYA_RESEARCH/src/research/hypothesis_generator.py).

Gate lokal `A-HYP-LOCAL`:

- tanpa corpus, proposal berstatus `UNGROUNDED_SEED`, novelty
  `NOT_EVALUATED`, evidence `UNVERIFIED`, dan tidak promotable;
- generator tidak mengarang persentase, p-value, latency, atau pengukuran;
- proposal memiliki variabel independen, dependen, kontrol, hubungan yang dapat
  diuji, dan kriteria falsifikasi;
- keluaran model yang diinjeksi tetap unverified dan tidak promotable;
- topic kosong ditolak.

Gate representatif `A-HYP-REP`:

- minimal 30 candidate dari topik benchmark `A-GAP-REP`;
- 100% candidate memiliki evidence IDs yang valid, hipotesis falsifiable,
  variabel operasional, dan hubungan ke gap candidate;
- minimal dua reviewer domain nyata menilai kelayakan ilmiah dan keselamatan;
- candidate yang diterima minimal 80%, atau kegagalan dan kategori penyebabnya
  dipublikasikan sebagai hasil evaluasi;
- keputusan tidak boleh memakai novelty score lokal sebagai bukti novelty.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk evaluasi domain
representatif.

### 4.4 Experiment designer dan runner

Implementasi: [experiment_designer.py](../JAYA_RESEARCH/src/research/experiment_designer.py)
dan [experiment_runner.py](../JAYA_RESEARCH/src/research/experiment_runner.py).

Gate lokal `A-EXP-LOCAL`:

- design memuat variabel, procedure, execution mode, safety status, fixed-sample
  stop rule, metode statistik, alpha, effect size, dan syarat reproduksi;
- operasi berisiko diblokir oleh safety interlock;
- simulasi deterministik untuk input/seed sama, berlabel `SIMULATION`, tidak
  mengubah confidence, dan tidak promotable;
- empirical mode tanpa observations/provenance/license/runner/environment yang
  lengkap ditolak sebagai `UNVERIFIED`;
- boolean `reproduced=true` dari input tidak dipercaya;
- review eligibility memerlukan minimal satu prior receipt empiris valid dengan
  dataset, runner, dan environment berbeda serta effect direction/tolerance
  yang sesuai;
- result receipt memiliki digest dan tampering ditolak.

Gate eksternal `A-EXP-REP`:

- protocol, power analysis, sample size, exclusion rule, dan statistical plan
  dipraregistrasi dan disetujui penanggung jawab domain/etik;
- data nyata mempunyai consent/legal basis, license, lineage, serta raw artifact
  yang immutable;
- minimal dua run empiris benar-benar independen menggunakan runner,
  environment, dan dataset berbeda;
- analisis statistik dan klaim hasil ditinjau manusia;
- `promotion_eligible` dari runner hanya berarti layak masuk review, bukan
  accepted finding atau publication approval.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk data, etik, compute, dan
reproduksi independen nyata.

### 4.5 PDF ingestion

Implementasi: [multimodal_pdf.py](../JAYA_RESEARCH/src/research/multimodal_pdf.py).

Gate lokal `A-PDF-LOCAL`:

- signature, enkripsi, byte limit, page limit, corrupt structure, dan dependency
  failure menghasilkan kode error stabil;
- setiap halaman menyimpan nomor, offset, extraction method, source URI,
  license ID, dan SHA-256 sumber;
- halaman scan tanpa provider berstatus `PARTIAL_OCR_REQUIRED` dan tidak
  promotable;
- OCR/table/figure hanya berasal dari provider yang diinjeksi dan provenance
  metodenya dicatat;
- kegagalan OCR bertipe dan tidak membocorkan response provider;
- sistem tidak membuat tabel, gambar, formula, atau nilai contoh ketika provider
  tidak tersedia.

Gate representatif `A-PDF-REP`:

- corpus minimal 30 dokumen berlisensi yang mencakup born-digital, scan,
  corrupt/encrypted controls, dua bahasa, tabel, gambar, dan formula;
- classification untuk corrupt/encrypted/limit controls harus 100%;
- page order, page number, source digest, dan provenance harus 100% benar;
- OCR word error rate maksimal 10% pada bahasa yang dinyatakan didukung;
- table cell F1 dan figure/formula association masing-masing minimal 90%;
- semua kasus gagal dan halaman yang membutuhkan OCR tetap masuk laporan.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` karena corpus gold dan adapter OCR,
table, serta figure yang disetujui belum dievaluasi representatif.

### 4.6 Grounded RAG dan evaluasi

Implementasi: [retrieval_evidence.py](../JAYA_RESEARCH/src/research/retrieval_evidence.py),
[rag_evaluation.py](../JAYA_RESEARCH/src/research/rag_evaluation.py), dan
[rag_smoke_v2.json](../JAYA_RESEARCH/evaluation/rag_smoke_v2.json).

Gate lokal `A-RAG-LOCAL`:

- setiap claim yang dijawab memiliki citation ID yang membuka source URI,
  page/span, source/content digest, retrieval score, license, dan access time;
- empty/low-confidence retrieval abstain dan conflicting evidence tidak
  disintesis diam-diam;
- chunk/dataset/report digest yang berubah ditolak;
- dataset wajib memiliki schema, version, license, provenance, source digest,
  query language, relevant source IDs, dan representativeness status;
- retriever malformed gagal, bukan diberi skor nol;
- smoke fixture bilingual memuat positive dan abstention control;
- ketujuh metrik lokal harus masing-masing `>= 0.85`: recall@k, hit rate@k,
  MRR, citation precision, citation recall, groundedness, dan abstention
  accuracy.

Gate representatif `A-RAG-REP` mengikuti kontrak implementasi:

- dataset berstatus `APPROVED_REPRESENTATIVE` dan memiliki `approved_by`,
  `approved_at`, approval receipt SHA-256, serta sampling frame;
- run memiliki runner ID, environment ID, commit SHA valid, code SHA-256, dan
  config SHA-256;
- seluruh tujuh metrik masing-masing `>= 0.85` pada dataset tersebut;
- `production_gate_passed=true` dan status report
  `VERIFIED_REPRESENTATIVE`;
- latency p50/p95/max dilaporkan. Ambang latency harus dipraregistrasi sesuai
  deployment target sebelum run dan tidak boleh dipilih setelah melihat hasil.

Fixture aktif saat ini berstatus `SMOKE_ONLY`. Nilai 1.0 pada tiga kasus
sintetis hanya membuktikan harness dan tidak mengukur kualitas corpus atau
retrieval produksi.

**Status:** `PASS_LOCAL` dengan `LOCAL_SMOKE_PASSED`;
`BLOCKED_EXTERNAL` untuk `A-RAG-REP`.

### 4.7 Scientific writer, drafter, reviewer, dan editor

Implementasi: [scientific_writer.py](../JAYA_RESEARCH/src/research/scientific_writer.py),
[contracts.py](../JAYA_RESEARCH/src/research/academic/contracts.py),
[drafter.py](../JAYA_RESEARCH/src/research/academic/drafter.py),
[reviewer.py](../JAYA_RESEARCH/src/research/academic/reviewer.py), dan
[editor.py](../JAYA_RESEARCH/src/research/academic/editor.py).

Gate lokal `A-SYN-LOCAL`:

- paper memakai struktur IMRaD dan melaporkan evidence kind, reproduction,
  limitations, unsupported claims, serta citation coverage;
- setiap claim penting memakai evidence ID yang diberikan atau marker
  `UNSUPPORTED`;
- reference tanpa ID/title traceable dibuang, bukan diisi placeholder;
- bibliography canonical hanya dibuat dari record input; bibliography buatan
  provider dibuang dan citation ID asing menolak output;
- missing evidence menghasilkan abstain, bukan synthesis positif;
- provider tidak dibuat saat constructor; provider failure menghasilkan status
  bertipe tanpa fabricated fallback;
- editor menerima revisi hanya bila urutan heading, jumlah citation asli, dan
  bibliography asli tetap utuh; jika gagal, naskah asli dikembalikan persis;
- review otomatis tidak boleh memberi publication-readiness decision;
- simulation report selalu non-empirical dan tidak publishable;
- reproduced empirical draft tetap `publication_ready=false` dan
  `human_review_required=true`.

Gate representatif `A-SYN-REP`:

- audit minimal 50 claim penting dari corpus Phase A representatif;
- evidence-ID traceability 100%, fabricated citation/bibliography 0, dan
  unsupported claim tanpa marker 0;
- human citation-entailment precision minimal 95%;
- reviewer/editor diuji pada minimal 20 bab oleh minimal dua reviewer manusia;
  structure/citation preservation dan critical integrity violations harus
  masing-masing 100% dan 0;
- usefulness rubric rata-rata minimal 4/5 dengan inter-rater agreement minimal
  0.67;
- semua draft tetap memerlukan keputusan author, reviewer domain, etik, dan
  publisher manusia.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk audit entailment, kualitas
editorial, dan approval manusia.

### 4.8 Deep research dan API evidence flow

Implementasi: [agent.py](../JAYA_RESEARCH/src/research/agent.py),
[research_api.py](../JAYA_RESEARCH/src/network/research_api.py), dan
[api_models.py](../JAYA_RESEARCH/src/network/api_models.py).

Gate lokal `A-DEEP-LOCAL`:

- planner malformed ditolak; tidak ada pertanyaan fallback generik yang
  disamarkan sebagai hasil planner;
- retrieval kosong/lemah menghasilkan abstain tanpa meminta model mengisi
  fakta dari pengetahuan internal;
- retry menyimpan audit attempt, tetapi keputusan aktif memakai hasil terbaru
  per query;
- kegagalan provider sintesis opsional tidak membatalkan jawaban extractive
  yang sudah grounded;
- prose model disimpan terpisah sebagai draft tidak terverifikasi dan tidak
  pernah dimasukkan ke evidence store atau knowledge graph;
- source label tanpa URI/path nyata tidak dapat menjadi complete provenance;
- report memakai run ID unik, write-once, checksum, dan status non-promotable;
- request API dibatasi, field asing ditolak, workspace tidak dibuat diam-diam,
  citation path harus canonical/contained, dan artefak membawa SHA-256;
- chat serta recursive endpoint hanya mengembalikan evidence extractive atau
  abstain; tidak ada jalur generatif lama setelah response aktif.

Gate representatif `A-DEEP-REP`:

- minimal 50 tugas research lintas domain/bahasa pada corpus representatif;
- source recall, claim-citation entailment, abstention, conflict handling,
  latency, biaya, dan provider-failure rate dilaporkan;
- audit manusia memastikan fabricated claim/citation 0 dan keputusan ilmiah
  tidak berasal dari model saja;
- worker terpisah, cancel/resume, observability, quota, serta recovery diuji
  pada deployment target.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk corpus representatif, provider
live, audit manusia, dan deployment worker.

### 4.9 Deep Research UI

Implementasi: [ResearchPage.jsx](../JAYA_RESEARCH/ui/src/pages/ResearchPage.jsx),
[api.js](../JAYA_RESEARCH/ui/src/services/api.js),
[contracts.js](../JAYA_RESEARCH/ui/src/services/contracts.js), dan
[router.jsx](../JAYA_RESEARCH/ui/src/routing/router.jsx).

Gate lokal `A-UI-LOCAL`:

- Deep Research UI membangun request melalui kontrak service kanonis dan hanya
  mengirimkannya ke `/research/recursive`;
- respons membedakan `ANSWERED`, abstain, dan conflict tanpa menyamarkan
  abstention atau contract violation sebagai keberhasilan;
- citation/provenance serta URI dan SHA-256 artefak ditampilkan ketika tersedia;
- hasil tetap non-promotable dan UI tidak mengklaim `applied`, deployment, atau
  perubahan pada JAYA Core;
- API key hanya disimpan di memori runtime, hilang saat reload, dan gate
  memverifikasi kredensial memakai operasi baca tanpa menulis secret ke storage
  atau log UI;
- transcript chat Research juga memory-only secara default; persistence belum
  boleh diaktifkan tanpa consent, enkripsi, retention, dan deletion policy;
- kegagalan HTTP dipertahankan sebagai `ApiError` terstruktur; request
  autonomous research membawa `Idempotency-Key`, dan CORS tetap dikendalikan
  kontrak backend;
- preview/download source dan export tesis tetap memakai transport Bearer yang
  sama; status `EXTRACTED_INDEX_UNAVAILABLE` tidak boleh ditampilkan sebagai
  source yang sudah masuk RAG;
- halaman evolution tidak mengirim request mutasi dan hanya menampilkan status
  `BLOCKED`; feature flag berbahaya nonaktif secara default;
- Electron hanya menerima URL HTTP loopback dari launcher, dengan Node
  integration nonaktif, context isolation dan sandbox aktif; preview produksi
  mem-proxy `/api` ke target lokal yang dikonfigurasi;
- router internal memvalidasi same-origin path serta batas workspace/modul dan
  menggantikan dependency `react-router` yang terkena advisory;
- Vite 8 dan lazy chunks dipakai; contract test `12 passed`, lint, production
  build, dan `npm audit` 0 vulnerability telah lulus secara lokal.

Gate representatif/operasional `A-UI-REP`:

- jalankan browser E2E terhadap API ter-deploy dengan auth, CORS, idempotency,
  reload/navigation, dan network/provider failure nyata;
- uji tampilan answered, abstain, conflict, citation/provenance, serta tautan
  artefak dengan provider live dan data representatif;
- simpan bukti deployment, konfigurasi, browser, commit, dan artefak hasil tanpa
  merekam credential.

**Status:** `PASS_LOCAL`; `BLOCKED_EXTERNAL` untuk browser E2E, deployment, dan
provider live.

## 5. Command bukti lokal

Jalankan dari root repository menggunakan PowerShell.

### 5.1 Acceptance suite Phase A

```powershell
$env:PYTHONPATH='JAYA_RESEARCH/src;JAYA_RESEARCH;.'
$env:JAYA_ENV='test'
$env:JAYA_HTTP_SECURITY_TEST_MODE='1'
python -m pytest JAYA_RESEARCH/tests/test_academic_quality_contracts.py JAYA_RESEARCH/tests/test_hypothesis_generator.py JAYA_RESEARCH/tests/test_experiment_designer.py JAYA_RESEARCH/tests/test_experiment_runner.py JAYA_RESEARCH/tests/test_scientific_writer.py JAYA_RESEARCH/tests/test_academic_synthesis_truth.py JAYA_RESEARCH/tests/test_multimodal_pdf.py JAYA_RESEARCH/tests/test_retrieval_evidence_and_eval.py JAYA_RESEARCH/tests/test_grounded_rag_integration.py JAYA_RESEARCH/tests/test_phase_a_rag_contract.py JAYA_RESEARCH/tests/test_research_agent_truth.py JAYA_RESEARCH/tests/test_research_api_phase_a.py JAYA_RESEARCH/tests/test_e2e_api_ui.py -q -p no:cacheprovider --basetemp=JAYA_RESEARCH/.pytest_tmp_phase_a_acceptance
```

Bukti terakhir pada 1 Agustus 2026: `194 passed`. Run ini membuktikan gate lokal
saja; fake provider dan fixture sintetis di dalam tes tidak menjadi bukti mutu
ilmiah.

### 5.2 RAG contract smoke

```powershell
$env:PYTHONPATH='JAYA_RESEARCH/src;JAYA_RESEARCH;.'
python -m research.evaluation_cli --dataset JAYA_RESEARCH/evaluation/rag_smoke_v2.json --target 0.85
```

Expected invariant:

- dataset SHA-256
  `0ada9b26b3384b01eb8a7dcdb7f5508e4e3cc0eea13896e9e507d01b32d442e8`;
- `representation_status=SMOKE_ONLY`;
- `local_target_met=true`;
- `status=LOCAL_SMOKE_PASSED`;
- `production_gate_passed=false`;
- run default `attested=false`.

### 5.3 Kontrak dan build UI

```powershell
Set-Location JAYA_RESEARCH\ui
npm run test:contracts
npm run lint
npm run build
npm audit
Set-Location ..\..
```

Bukti terakhir pada 1 Agustus 2026: contract test `12 passed`, lint dan
production build lulus, serta `npm audit` melaporkan 0 vulnerability. Ini belum
membuktikan browser E2E, deployment, atau provider live.

### 5.4 Validasi dokumentasi

```powershell
python scripts/validate_docs.py
```

## 6. Keputusan exit Phase A

| Lapisan | Keadaan 1 Agustus 2026 | Alasan |
|---|---|---|
| Kontrak software offline | `PASS_LOCAL` | Acceptance suite 194 tes lulus. |
| Kontrak dan build UI | `PASS_LOCAL` | Contract test 12 tes, lint, production build, dan audit dependency lokal lulus. |
| Browser E2E, deployment, provider live | `BLOCKED_EXTERNAL` | Belum ada bukti run browser terhadap API ter-deploy dan dependency nyata. |
| RAG smoke harness | `PASS_LOCAL` | Semua metrik fixture lokal memenuhi 0.85, tetapi dataset `SMOKE_ONLY`. |
| Novelty dan gap representatif | `BLOCKED_EXTERNAL` | Corpus berlabel dan reviewer domain nyata belum tersedia. |
| PDF representatif | `BLOCKED_EXTERNAL` | Corpus gold dan evaluasi OCR/table/figure belum tersedia. |
| Eksperimen empiris | `BLOCKED_EXTERNAL` | Data, approval etik/legal, serta reproduksi independen nyata belum tersedia. |
| Sintesis dan review ilmiah | `BLOCKED_EXTERNAL` | Audit citation entailment dan review manusia belum tersedia. |
| Phase A ilmiah keseluruhan | `BLOCKED_EXTERNAL` | Gate lokal tidak menggantikan seluruh gate representatif dan manusia. |

Phase A boleh disebut **siap untuk pengujian representatif**, tetapi belum boleh
disebut **selesai secara ilmiah**, **production-ready**, atau
**publication-ready**. Status hanya boleh dinaikkan setelah artefak eksternal
yang diwajibkan tersimpan, validator lulus, dan tidak ada gate `FAIL` atau
`BLOCKED_EXTERNAL` yang tersisa.
