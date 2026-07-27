# Checklist Pemulihan JAYA

**Program:** Research Truth & Core Readiness  
**Baseline audit:** 26 Juli 2026  
**Pemilik:** maintainer root + pemilik modul  
**Status program:** IN PROGRESS

Dokumen ini adalah checklist eksekusi kanonis untuk mengembalikan implementasi
ke tujuan awal:

1. **JAYA Research benar-benar meneliti**: sumber dapat dilacak, hipotesis
   grounded, eksperimen memakai data/metode nyata, hasil dapat direproduksi, dan
   simulasi tidak pernah disebut bukti empiris.
2. **JAYA Core benar-benar menjadi otak**: intent, reasoning, planning, memory,
   dan eksekusi stabil; Core tidak menerima “pengetahuan” atau upgrade tanpa
   bukti, izin, dan rollback.

Checklist ini melengkapi [ROADMAP.md](ROADMAP.md). `ROADMAP.md` menentukan arah
fase; file ini menentukan pekerjaan perbaikan konkret dan bukti penyelesaiannya.

## Aturan status

- `[ ] OPEN`: belum dikerjakan atau gate belum lulus.
- `[x] DONE`: code, failure handling, test, dan bukti lokal sudah tersedia.
- `BLOCKED_EXTERNAL`: implementasi lokal selesai tetapi verifikasi membutuhkan
  dataset, credential, hardware, perangkat, atau approver eksternal.
- Tidak boleh mencentang item hanya karena class/file tersedia.
- Setiap item selesai wajib mengisi baris **Evidence** dengan command dan hasil.

## Definition of Done

Sebuah item hanya `DONE` jika:

1. perilaku utama dan failure path diimplementasikan;
2. tidak ada secret/hardcode workstation atau bypass gate;
3. unit/integration test deterministik lulus;
4. konfigurasi dan error dapat ditindaklanjuti;
5. dokumentasi/status/changelog diselaraskan;
6. tidak menimpa perubahan pengguna di luar scope;
7. untuk klaim `VERIFIED/PRODUCTION`, bukti eksternal pada bagian terakhir juga
   harus lulus.

## Invariant yang tidak boleh dilanggar

- Research tidak mengimpor internal Core, menulis source Core, atau mengubah DB
  milik Core.
- `SIMULATION` tidak pernah dapat dipromosikan.
- Caller tidak dapat menyatakan sendiri `tests_passed` atau benchmark lulus.
- Hilangnya key, bukti, provenance, license, approval, atau rollback harus
  menghasilkan penolakan (*fail closed*).
- Loop otonom selalu default nonaktif, terbatas, dapat dihentikan, dan tidak
  melakukan promosi.
- Core memiliki reasoning contract; Research memiliki knowledge/evidence.

---

## 0. Fondasi repository dan tracking

- [x] **FND-001 — Satu sumber dokumentasi aktif** (`P0`)
  - **Acceptance:** dokumen aktif hanya di `docs/`; README modul hanya pointer;
    validator tautan/struktur lulus.
  - **Evidence:** `python scripts/validate_docs.py` → 19 file aktif valid pada
    baseline konsolidasi.

- [x] **FND-002 — Satu Git root** (`P0`)
  - **Acceptance:** tidak ada `<MODULE>/.git`; Git dari Research kembali ke root.
  - **Evidence:** `git -C JAYA_RESEARCH rev-parse --show-toplevel` mengembalikan
    root monorepo.

- [ ] **FND-003 — Test dan dokumentasi wajib dapat dilacak Git** (`P1`)
  - **Masalah:** `.gitignore` mengabaikan `tests/`, `test_*.py`, dan seluruh
    artefak test sehingga test baru mudah tidak ter-commit.
  - **Acceptance:** source test tidak di-ignore; hanya output/cache/fixture privat
    yang di-ignore; validator memastikan file gate trackable.
  - **Evidence:** pending.

- [ ] **FND-004 — Root packaging dan test discovery deterministik** (`P1`)
  - **Masalah:** import `src`/`config` generik dan mutasi `sys.path` membuat
    collection gabungan gagal.
  - **Acceptance:** root `pyproject.toml`/pytest config, namespace package unik,
    marker network/hardware; `pytest --collect-only` seluruh modul tanpa error.
  - **Evidence:** baseline: 154 test terkoleksi dengan 53 collection error.

---

## 1. P0 — Hentikan perilaku palsu atau berbahaya

- [ ] **SAF-001 — Bekukan loop autonomous upgrade** (`P0`)
  - **Masalah:** loop dapat dipulihkan saat startup, berjalan tiap 8 detik, dan
    memicu patch/finetune/sync otomatis.
  - **Aksi:** default OFF; hapus auto-restore; wajib consent token, max iteration,
    timeout, quota, dan kill switch; loop hanya menghasilkan candidate.
  - **Acceptance:** restart tidak memulai loop; run tanpa consent ditolak; tidak
    ada DB/source lintas modul yang berubah.
  - **Evidence:** pending.

- [ ] **SAF-002 — Hapus direct import/write Research → Core** (`P0`)
  - **Masalah:** `research/ecosystem_bridge.py` memasukkan Core ke `sys.path`,
    membuat evidence palsu, lalu overwrite `auto_research_patch.py`.
  - **Aksi:** bridge hanya mengekspor artifact immutable ke outbox Research.
  - **Acceptance:** audit AST/filesystem menemukan nol import internal Core dan
    nol write ke `JAYA_CORE`; test memastikan source tree tidak berubah.
  - **Evidence:** pending.

- [ ] **SAF-003 — Hapus injeksi langsung ke database Core** (`P0`)
  - **Masalah:** `JarvisDiscoveryBridge` mengaktifkan directive langsung dalam
    SQLite yang dianggap milik Core.
  - **Aksi:** ubah menjadi candidate artifact `PENDING_REVIEW`; consumer Core
    menarik artifact setelah gate.
  - **Acceptance:** Research tidak membuka DB Core; output hanya artifact
    versioned dan status belum aktif.
  - **Evidence:** pending.

- [ ] **SAF-004 — Pisahkan SIMULATION dari EMPIRICAL** (`P0`)
  - **Masalah:** runner membuat p-value/variance random tetapi statusnya
    `COMPLETED`, lalu learner menyebut “empirical support”.
  - **Aksi:** schema result wajib memiliki `evidence_kind`; simulasi
    deterministik berstatus `SIMULATION`; empirical membutuhkan data/provenance.
  - **Acceptance:** simulation selalu ditolak promotion/writer empiris; test
    reproduksi dengan seed dan test data nyata lulus.
  - **Evidence:** pending.

- [ ] **SAF-005 — Hentikan fake LoRA `.pt`** (`P0`)
  - **Masalah:** loss dihitung formula dan JSON dummy ditulis dengan ekstensi
    `.pt`, tetapi API mengklaim training selesai.
  - **Aksi:** mode default hanya `DATASET_PREPARED`; training membutuhkan backend
    PEFT nyata dan menghasilkan safetensors/config/eval report.
  - **Acceptance:** tanpa backend/model, status fail/blocked dengan jelas dan
    tidak ada `.pt`; hanya artefak model terverifikasi boleh disebut trained.
  - **Evidence:** pending.

- [ ] **SAF-006 — Evolution signing tanpa fallback key publik** (`P0`)
  - **Masalah:** Core memakai `jaya-phase2-dev-key`.
  - **Aksi:** key environment/secret store atau ephemeral process key untuk test;
    production tanpa key harus fail closed.
  - **Acceptance:** tidak ada key literal; missing production key ditolak;
    tamper/wrong-key/replay test lulus.
  - **Evidence:** pending.

- [ ] **SAF-007 — Evidence gate tidak menerima boolean caller** (`P0`)
  - **Masalah:** producer dapat mengirim `tests_passed=True` dan benchmark buatan.
  - **Aksi:** Core-side verifier membaca signed test/benchmark receipts dengan
    digest, runner identity, commit, dataset, dan timestamp.
  - **Acceptance:** evidence manual/missing/tampered/expired ditolak; hanya receipt
    valid dapat mencapai gate performa.
  - **Evidence:** pending.

- [ ] **SAF-008 — Human approval dan rollback wajib** (`P0`)
  - **Aksi:** manifest membawa approval, target/version, install plan, rollback
    receipt; installer terpisah dari verifier/signer.
  - **Acceptance:** candidate tanpa approval tidak dapat di-install; canary dan
    rollback idempotent diuji.
  - **Evidence:** pending.

---

## 2. P0 — Security boundary

- [ ] **SEC-001 — Workspace path containment** (`P0`)
  - **Masalah:** `workspace_id` mentah membentuk path dan dapat mencapai
    `shutil.rmtree`.
  - **Acceptance:** ID tervalidasi; `resolve().relative_to(root)` wajib; traversal,
    absolute path, encoded separator, dan symlink escape ditolak tanpa perubahan.
  - **Evidence:** pending.

- [ ] **SEC-002 — Upload quarantine dan resource limit** (`P0`)
  - **Acceptance:** cek size, MIME/magic, extension, checksum, duplicate, quota,
    parser timeout; file salah/oversize tidak masuk knowledge store.
  - **Evidence:** pending.

- [ ] **SEC-003 — Auth, authorization, CORS, rate limit** (`P0`)
  - **Masalah:** Research/Agent API memakai CORS wildcard dan endpoint destructive
    tanpa auth.
  - **Acceptance:** deny-by-default; identity workspace-scoped; origin allowlist;
    rate/body limit; unauthorized start/delete/tool/config requests menghasilkan
    401/403/429.
  - **Evidence:** pending.

- [ ] **SEC-004 — Agent tool capability sandbox** (`P0`)
  - **Acceptance:** file/network/process tool memakai capability grant, allowlist,
    timeout, audit consent; arbitrary read/write/command ditolak.
  - **Evidence:** pending.

- [ ] **SEC-005 — TLS dan provider verification** (`P1`)
  - **Masalah:** beberapa client menonaktifkan SSL verification.
  - **Acceptance:** certificate verification default ON; override hanya test
    eksplisit; timeout/retry/circuit breaker tersedia.
  - **Evidence:** pending.

---

## 3. JAYA Research — fondasi riset nyata

- [ ] **RES-001 — Pulihkan kontrak Enhanced RAG** (`P0`)
  - **Masalah:** `VectorStore`, chunker, dan embedding interface tidak cocok;
    jalur produksi ResearchAgent gagal.
  - **Acceptance:** ingest/search/reload/delete/workspace isolation berfungsi;
    15 test RAG baseline lulus; interface tunggal terdokumentasi.
  - **Evidence:** baseline 26 Juli 2026: 14 gagal, 1 lulus.

- [ ] **RES-002 — Embedding fallback jujur dan terukur** (`P1`)
  - **Aksi:** fallback lokal diberi tipe/model/version dan tidak disamakan dengan
    NVIDIA embedding; dimension serta normalization divalidasi.
  - **Acceptance:** provider failure tidak menghasilkan evidence palsu; fallback
    deterministik diuji dan kualitasnya diukur terpisah.
  - **Evidence:** pending.

- [ ] **RES-003 — Citation/provenance per klaim** (`P1`)
  - **Acceptance:** setiap klaim penting membawa source ID, URI/path, page/span,
    chunk hash, retrieval score, dan waktu akses; tautan dapat dibuka.
  - **Evidence:** pending.

- [ ] **RES-004 — Abstain dan conflict handling** (`P1`)
  - **Acceptance:** konteks kosong/rendah/kontradiktif menghasilkan abstain atau
    uncertainty, bukan penggunaan “internal knowledge” tanpa sumber.
  - **Evidence:** pending.

- [ ] **RES-005 — Dataset evaluasi RAG versioned** (`P1`)
  - **Acceptance:** dataset legal/nonprivat, retrieval metrics, groundedness,
    citation correctness, regression report; target QA minimal 85%.
  - **Status:** `BLOCKED_EXTERNAL` untuk pencapaian angka final sampai dataset
    representatif disetujui; harness lokal tetap wajib dibuat.
  - **Evidence:** baseline historis 55%.

- [ ] **RES-006 — Hipotesis grounded, bukan random/template** (`P1`)
  - **Acceptance:** hipotesis membawa evidence IDs, gap method, variables,
    falsifiability, prior rationale; tanpa corpus menjadi `DRAFT_UNGROUNDED` dan
    tidak promotable.
  - **Evidence:** pending.

- [ ] **RES-007 — Experiment input dan statistik nyata** (`P1`)
  - **Acceptance:** dataset hash/license/version, baseline/treatment, seed/config,
    environment, method, effect size, uncertainty, p-value correction, stop rule,
    raw output, serta failure tersimpan.
  - **Evidence:** pending.

- [ ] **RES-008 — Reproduksi independen** (`P1`)
  - **Acceptance:** empirical candidate memerlukan minimal dua run independen
    dalam tolerance; mismatch menjadi `REPRODUCTION_FAILED`.
  - **Evidence:** pending.

- [ ] **RES-009 — Scientific writer hanya memakai evidence store** (`P1`)
  - **Masalah:** referensi placeholder/fiktif dan simulasi dapat disebut empiris.
  - **Acceptance:** tidak membuat citation yang tidak ada; simulation/negative
    result/limitations dilabeli; claim tanpa evidence ditolak.
  - **Evidence:** pending.

- [ ] **RES-010 — Provider error bertipe, bukan jawaban normal** (`P1`)
  - **Acceptance:** timeout/auth/quota/network/model error menjadi exception/result
    terstruktur; downstream tidak menyimpan pesan error sebagai pengetahuan.
  - **Evidence:** pending.

- [ ] **RES-011 — Thesis session persisten** (`P1`)
  - **Acceptance:** upload/status/result/revision/journal bertahan restart;
    transaksi aman; raw text tidak hilang; migration dan recovery test lulus.
  - **Evidence:** pending.

- [ ] **RES-012 — Durable job state machine** (`P1`)
  - **Acceptance:** `QUEUED/RUNNING/WAITING_REVIEW/SUCCEEDED/FAILED/CANCELED`,
    progress, idempotency, retry, resume, cancel; restart tidak menggandakan job.
  - **Evidence:** pending.

- [ ] **RES-013 — Hapus duplicate route dan pecah API monolitik** (`P1`)
  - **Acceptance:** OpenAPI tidak memiliki duplicate method+path; router/service/
    repository terpisah; startup tidak menginisialisasi dependency opsional berat.
  - **Evidence:** pending.

- [ ] **RES-014 — Konfigurasi tunggal tervalidasi** (`P1`)
  - **Acceptance:** tidak ada config ganda, port/path/model/threshold/workstation
    hardcode; startup validation menjelaskan field salah tanpa secret.
  - **Evidence:** pending.

- [ ] **RES-015 — LoRA training dan evaluation nyata** (`P2`)
  - **Acceptance:** PEFT training reproducible, dataset provenance, holdout eval,
    base-vs-adapter benchmark, model card, safetensors, license, rollback.
  - **Status:** `BLOCKED_EXTERNAL` untuk gate final sampai model, dataset, compute,
    dan license tersedia.
  - **Evidence:** pending.

---

## 4. JAYA Core — otak yang siap dipakai

- [ ] **CORE-001 — Typed configuration dan secret validation** (`P0`)
  - **Acceptance:** tidak ada password/model/server hardcode; production startup
    gagal jelas saat secret wajib tidak ada; config dapat diuji.
  - **Evidence:** pending.

- [ ] **CORE-002 — Evolution manifest v1 lengkap** (`P0`)
  - **Acceptance:** manifest version, content digest, provenance, license,
    compatibility, evidence receipts, approval, install/rollback plan, signature.
  - **Evidence:** pending.

- [ ] **CORE-003 — Safe artifact verifier/installer** (`P0`)
  - **Acceptance:** verifier read-only; installer hanya target registry/data
    allowlist, tidak source tree; traversal/symlink/overwrite/replay ditolak;
    dry-run dan atomic install tersedia.
  - **Evidence:** pending.

- [ ] **CORE-004 — Hapus fabricated promotion scripts** (`P0`)
  - **Masalah:** adapter/student/auto-teacher membuat evidence true dan resource
    estimate hardcode.
  - **Acceptance:** scripts membaca receipt nyata atau menolak; path/config melalui
    CLI; missing report tidak memakai default score.
  - **Evidence:** pending.

- [ ] **CORE-005 — Reasoning pipeline contract** (`P1`)
  - **Acceptance:** Intent → Lingua Logica → JayaIR → executor memiliki schema
    version, typed error, timeout, deterministic tests, dan compatibility gate.
  - **Evidence:** Phase 1 baseline: 13 test terarah lulus.

- [ ] **CORE-006 — Server/API menunjukkan readiness nyata** (`P1`)
  - **Masalah:** server memiliki import hilang, CORS/auth lemah, status selalu
    stabil, dan route tesis hardcode.
  - **Acceptance:** service factory; `/healthz` liveness dan `/readyz` berdasarkan
    dependency nyata; route belum tersedia mengembalikan 501, bukan sukses palsu.
  - **Evidence:** pending.

- [ ] **CORE-007 — Inference adapter benar-benar menghasilkan output** (`P1`)
  - **Masalah:** jalur native Nano memiliki tokenize kosong dan batch `pass`.
  - **Acceptance:** real model smoke menghasilkan output non-template; missing
    runtime/model fail jelas; resource/latency diukur.
  - **Status:** `BLOCKED_EXTERNAL` untuk model/hardware final.
  - **Evidence:** pending.

- [ ] **CORE-008 — Planning, memory, dan reasoning E2E** (`P1`)
  - **Acceptance:** skenario intent multi-step, memory retrieval, conflict,
    tool-plan tanpa eksekusi liar, restart persistence, dan error recovery lulus.
  - **Evidence:** pending.

- [ ] **CORE-009 — Audit log persisten dan redacted** (`P1`)
  - **Acceptance:** decision/receipt/install/rollback punya correlation ID,
    timestamp, actor, digest; secret/prompt sensitif tidak bocor; restart aman.
  - **Evidence:** pending.

- [ ] **CORE-010 — Perbaiki seluruh syntax/import blocker** (`P1`)
  - **Acceptance:** compile/collection source dan test Core tanpa SyntaxError/
    NameError; khususnya `test_scene.py` dan `features/test_dialog/test_dialog.py`.
  - **Evidence:** baseline audit menemukan dua SyntaxError.

- [ ] **CORE-011 — Pisahkan ownership OS dari Core** (`P2`)
  - **Acceptance:** Core tidak memiliki driver/window/sandbox implementation;
    `JAYA_OS` menyediakan contract adapter; architecture boundary test lulus.
  - **Evidence:** pending.

- [ ] **CORE-012 — Reproducible package dan dependency manifest** (`P1`)
  - **Acceptance:** dependency groups/lock, build artifact checksum/SBOM, clean
    environment install, smoke, backup/restore, rollback runbook.
  - **Evidence:** pending.

- [ ] **CORE-013 — Larang in-process arbitrary code evolution** (`P0`)
  - **Masalah:** twin/morphic menjalankan candidate dengan `exec` dan full
    builtins; rollback hanya menghapus catatan, bukan memulihkan method/state.
  - **Acceptance:** candidate hanya berjalan pada sandbox worker terisolasi dengan
    AST/API allowlist, tanpa network/filesystem, timeout/resource limit; rollback
    memulihkan digest baseline secara atomik.
  - **Evidence:** pending.

- [ ] **CORE-014 — Unsupported JayaIR harus gagal, bukan stub sukses** (`P0`)
  - **Masalah:** intent tak terpetakan menjadi `CALL_STUB` dengan `ok=true`;
    beberapa opcode dideklarasikan tetapi tidak memiliki semantics.
  - **Acceptance:** seluruh opcode memiliki typed contract atau ditolak; stub/
    unsupported/divide-by-zero/invalid CFG menghasilkan typed failure; IR
    immutable dan cache tidak dapat menjalankan mutation setelah validasi.
  - **Evidence:** pending.

- [ ] **CORE-015 — ActionPlan, authorization, dan ExecutionReceipt** (`P0`)
  - **Acceptance:** Core hanya menghasilkan typed ActionPlan dengan risk,
    capability, idempotency key; OS/policy melakukan authorization/confirmation;
    UI tidak menyebut executed tanpa signed receipt.
  - **Evidence:** pending.

- [ ] **CORE-016 — Readiness model tidak boleh berasal dari random/template** (`P0`)
  - **Masalah:** model dapat random-init ketika artifact gagal dan chat memakai
    rule/template tetapi sistem tetap tampak aktif.
  - **Acceptance:** state `UNAVAILABLE/DEGRADED/READY`; production READY hanya jika
    checksum, tokenizer/model load, inference probes, memory, dan policy gate
    lulus; missing/corrupt/random model tidak pernah READY.
  - **Status:** `BLOCKED_EXTERNAL` untuk READY dengan model target final.
  - **Evidence:** pending.

---

## 5. Kontrak lintas ekosistem

- [ ] **INT-001 — Satu artifact contract publik** (`P0`)
  - **Acceptance:** Research outbox → Core inbox melalui package/API/message
    versioned; tidak ada shared DB, copy `.pt`, atau import implementation.
  - **Evidence:** pending.

- [ ] **INT-002 — Consumer compatibility dan revocation** (`P1`)
  - **Acceptance:** setiap consumer memvalidasi version/digest/license/signature;
    incompatible/revoked artifact ditolak; migration test tersedia.
  - **Evidence:** pending.

- [ ] **INT-003 — CI matrix seluruh modul** (`P1`)
  - **Acceptance:** docs/lint/type/unit/contract/security/build gates untuk
    Research, Core, Agent, OS, Android; network/hardware test memakai marker dan
    artifact, bukan diam-diam dilewati.
  - **Evidence:** pending.

- [ ] **INT-004 — UI menampilkan status bukti yang benar** (`P1`)
  - **Acceptance:** hanya `SIMULATION/CANDIDATE/PENDING_REVIEW/APPROVED/INSTALLED/
    REJECTED`; tidak mengklaim signed/deployed/discovery tanpa receipt backend.
  - **Evidence:** pending.

- [ ] **INT-005 — Observability dan operasi** (`P1`)
  - **Acceptance:** structured redacted log, metric, trace, correlation ID,
    persistent audit, health/readiness, backup/restore, incident/rollback drill.
  - **Evidence:** pending.

- [ ] **INT-006 — Deployment reproducible** (`P2`)
  - **Acceptance:** service definitions/container atau installer, environment
    schema, supervisor, migration, health gate, rollback, SBOM.
  - **Evidence:** pending.

- [ ] **INT-007 — Android security truthfulness** (`P2`)
  - **Acceptance:** TLS/authenticated LAN, Keystore secret, encrypted DB,
    non-destructive migrations, no BODY secret logging, no fake PQC label,
    device tests.
  - **Status:** sebagian `BLOCKED_EXTERNAL` sampai perangkat nyata tersedia.
  - **Evidence:** pending.

---

## 6. Gate verifikasi akhir

- [ ] **GATE-001 — Zero unsafe cross-boundary access**
  - Audit menunjukkan nol direct import/write/shared DB lintas modul.

- [ ] **GATE-002 — Research offline unit suite**
  - Seluruh unit test Research lulus tanpa network/credential.

- [ ] **GATE-003 — Research empirical study**
  - Satu studi nyata dari sumber → hipotesis → eksperimen → reproduksi → paper
    dapat dijalankan ulang dan semua claim bercitation.
  - **Status:** `BLOCKED_EXTERNAL` sampai dataset/studi disetujui.

- [ ] **GATE-004 — Core brain smoke**
  - Intent → reasoning → JayaIR → plan/response dengan model nyata, memory
    persistence, failure recovery, dan resource report.
  - **Status:** `BLOCKED_EXTERNAL` untuk model/hardware final.

- [ ] **GATE-005 — Safe promotion drill**
  - Candidate valid melewati receipts+approval+canary+rollback; candidate
    simulation/tampered/traversal/replay selalu ditolak.

- [ ] **GATE-006 — Clean install and restart**
  - Environment baru dapat build/start; restart di tengah job pulih; backup/
    restore serta rollback tervalidasi.

- [ ] **GATE-007 — Human scientific/security approval**
  - Reviewer manusia menyetujui dataset, metode, claim, threat model, dan release.
  - **Status:** `BLOCKED_EXTERNAL`.

## Urutan eksekusi aktif

1. `SAF-001` sampai `SAF-008`.
2. `SEC-001`, lalu `RES-001`.
3. `INT-001`, `CORE-002`, `CORE-003`.
4. `RES-006` sampai `RES-012`.
5. `CORE-013` sampai `CORE-016`, lalu `CORE-005` sampai `CORE-010`.
6. Packaging, CI, observability, UI, dan deployment.
7. Gate eksternal untuk status VERIFIED/PRODUCTION.

## Catatan eksekusi

Bagian ini diperbarui setelah setiap batch:

| Tanggal | Batch | Hasil |
|---|---|---|
| 2026-07-26 | Baseline audit | P0 direct-write/fabricated evidence/random experiment ditemukan; RAG 14 gagal dari 15 test |
