# Changelog

Perubahan penting pada arah, status, arsitektur, dan dokumentasi dicatat di sini.
Format tanggal menggunakan `YYYY-MM-DD`. Klaim status harus memiliki bukti yang
dapat dijalankan ulang.

## 2026-08-10 - P15 Ethical Heart mencapai 90 persen

### Added

- Menambahkan policy schema/versioning deterministic, risk class, tiga hasil
  keputusan, approval Ed25519 satu-kali, expiry, payload binding, dan typed
  failure code.
- Menambahkan decision receipt persisten berbentuk hash-chain dengan DNA
  attestation, gate planner dan `CALL_CAPABILITY`, demo nyata, serta auditor
  berbobot.

### Changed

- Menghapus keyword/regex sebagai sumber otorisasi; text-only self-modification
  kini gagal tertutup tanpa konteks policy terstruktur.
- Menaikkan P15 menjadi `INTEGRATED` (90%) dan progres Fondasi Kedaulatan
  menjadi 45%; fokus berikutnya P20 Sovereign Privacy.

### Verification

- Auditor Fondasi Kedaulatan: `18 passed`; P11 90%; P15 90%; kedua demo lulus.
- P15 membuktikan allow, deny, approval-required, approval sah, replay/expiry,
  planner gate, non-bypass capability gate, restart, conflict, dan tamper.

---

## 2026-08-10 - Fondasi Kedaulatan dimulai, P11 mencapai 90 persen

### Added

- Menambahkan DNA Anchor portabel dengan explicit enrollment, Ed25519 identity
  dan signed audit receipt, encrypted injected keystore, challenge nonce/expiry,
  replay protection, rotation, revocation, restart, serta migration evidence.
- Menambahkan boot gate runtime berotoritas dan konfigurasi
  `JAYA_REQUIRE_IDENTITY`, `JAYA_IDENTITY_KEY_SECRET`, serta
  `JAYA_IDENTITY_DIR` yang tervalidasi.
- Menambahkan CLI owner operation, demo nyata, auditor persentase, 10 evidence
  test, dan checkpoint checklist Fondasi Kedaulatan.

### Changed

- Menghapus hardware fingerprint sebagai identitas otak dan menghapus
  `jaya-master`, `owner`, serta timestamp identity yang hardcode dari runtime.
- Menaikkan P11 dari `PROTOTYPE` menjadi `INTEGRATED` (90%); progres Tahap 2
  menjadi 23%.

### Verification

- Auditor Fondasi Kedaulatan: `11 passed`; P11 90%; demo migration dan signed
  audit chain lulus.
- Regression P11 + config + Pondasi Logika/JayaIR: `87 passed`.

---

## 2026-08-10 - Pondasi Logika 95 persen dan arsitektur puzzle Core

### Added

- Menambahkan registry puzzle detachable dengan auto-discovery dari direktori
  tepercaya, verifikasi containment dan SHA-256, health check, permission,
  payload bound, timeout, detach, dan invocation receipt.
- Menambahkan pembatas RSS proses solver, probe node/thermal/power/accelerator,
  integrity/recovery ledger homeostasis, metrics terautentikasi, serta snapshot
  dan rollback SQLite milik Core.
- Menambahkan drill proses nyata untuk production config, HTTP, auth, readiness,
  logic, monitoring, backup, rollback, restart, dan continuity.

### Changed

- Mengganti fallback `CALL_STUB` dengan `CALL_CAPABILITY` yang fail-closed.
- Menjadikan model dan capability luar sebagai puzzle opsional; Agent, OS, dan
  Research tidak lagi dihitung sebagai dependency wajib Pondasi Logika.
- Menaikkan P1, P21, P2, dan P5 ke `VERIFIED` (95%) berdasarkan auditor.

### Verification

- Audit Pondasi Logika: `29 passed`, seluruh pilar 95%.
- Suite terfokus Core: `75 passed` setelah penambahan boundary test.
- Deployment drill: 9 check `PASS`, status `VERIFIED_LOCAL_PROCESS`.
- Suite JAYA Core penuh: `606 passed, 12 failed, 10 skipped`; kegagalan legacy
  di luar Pondasi Logika tetap dicatat dan tidak disembunyikan.

---

## 2026-08-10 - Pondasi Logika terukur 73 persen

### Added

- Menambahkan Pure Logic solver deterministik, typed truth state, proof trace,
  SQLite digest/idempotency, API terautentikasi, dan opcode JayaIR nyata.
- Menambahkan ResourceProfile fail-closed, Logical Homeostasis persisten,
  demo degrade/recover, 18 evidence test, serta auditor persentase berbobot.
- Menambahkan [dashboard Pondasi Logika](LOGICAL_FOUNDATION_PROGRESS.md).

### Changed

- Menaikkan P1 dan P5 ke `INTEGRATED`, P2 ke `IMPLEMENTED_LOCAL`, dan menjaga
  P21 pada `IMPLEMENTED_LOCAL` sampai Agent/OS capability nyata tersedia.
- Memperbaiki kontrak runtime yang hilang dan thread-safety SQLite saat dipakai
  melalui FastAPI.

### Verification

- Audit Pondasi Logika: `19 passed`, 73% keseluruhan.
- Regression Core service, JayaIR, dan memory restart: `42 passed`.

---

## 2026-08-10 - Urutan konstruksi dan dokumentasi pembangunan 40 pilar

### Added

- Menambahkan [pusat pembangunan 40 pilar](pillars/README.md) dengan sepuluh
  tahap dependency: pondasi, kedaulatan, keamanan, mesin, memori, regulasi,
  evolusi, sensor/reasoning, ruang kendali, dan distribusi.
- Menambahkan tepat 40 dokumen pembangunan—satu untuk setiap pilar—yang memuat
  tujuan, dependency, kontrak integrasi, checklist implementasi, exit criteria,
  dan larangan prototype tersembunyi.

### Changed

- Memisahkan nomor ID pilar dari urutan konstruksi agar binary compatibility
  tidak berubah.
- Mengoreksi klaim `production-ready` dan menampilkan snapshot aktual: 2 pilar
  `IMPLEMENTED_LOCAL`, 6 `PROTOTYPE`, dan 32 `NOT_IMPLEMENTED`.
- Memperluas validator dokumentasi untuk memeriksa jumlah, urutan, ID, struktur,
  dan tautan lokal seluruh dokumen pilar.

### Removed

- Menghapus enam dokumen duplikat atau usang: `NEXT_STEPS.md`,
  `COMPLETED_PHASES_CHECKLIST.md`, `PHASE2_LEVEL2_IMPLEMENTATION.md`,
  `REMEDIATION_PLAN.md`, `ARCHITECTURE_JARVIS.md`, dan
  `JAYA_NATIVE_LIBRARIAN_MODEL.md`.
- Mengalihkan test kontrak dari dokumen JARVIS duplikat ke entrypoint kanonis
  `docs/README.md` dan `docs/pillars/README.md`.

---

## 2026-08-02 - Restorasi Misi JAYA Core dan Arsitektur Distributed Sovereign Intelligence

### Added

- Menetapkan **ADR-009**: JAYA Research adalah Cognitive Evolution Laboratory (CEL); analisis tesis adalah domain adapter opsional; direct Core mutation dilarang tanpa exception.
- Menetapkan **ADR-010**: JAYA adalah *Distributed Sovereign Intelligence* — satu kecerdasan dengan banyak manifestasi node (Central, Standard, Edge, Mission Node, Micro Node).
- Menetapkan **ADR-011**: JAYA Research menganut *Dual-Track Architecture* — Track 1: Cognitive Evolution Research (Internal) & Track 2: Scientific and Engineering Discovery (External/3D/Physical AI/Digital Twin).
- Menambahkan **[DISCOVERY_PIPELINE_DESIGN.md](DISCOVERY_PIPELINE_DESIGN.md)**: desain 16-step Scientific & Engineering Discovery Pipeline, Omniverse/OpenUSD/Solvers integration, dan contoh riset Arc Reactor.
- Menambahkan **[JAYA_CORE_DESIGN.md](JAYA_CORE_DESIGN.md)**: desain internal JAYA Core mencakup 11 komponen Cognitive Kernel (portabel), Capability Packs (modular), Model Router, Budget-Aware Reasoning, spesifikasi JayaIR, memori per node, dan Capability Negotiation.
- Menambahkan **[JAYA_MESH_DESIGN.md](JAYA_MESH_DESIGN.md)**: desain JAYA Mesh mencakup 5 Node Tiers, Event Sync Protocol terenkripsi/signed, matriks mode operasi offline/online, conflict resolution policy, dan strategi Knowledge Cache.
- Menambahkan modul `JAYA_RESEARCH/src/discovery/` (`contracts.py`, `requirement_engine.py`, `falsification_engine.py`) dan unit test `JAYA_RESEARCH/tests/test_scientific_discovery.py` (4 test, PASS).
- Menambahkan **Fase G (Distributed Node & JAYA Mesh)** dan **Fase H (Advanced Capabilities: 3D/CAD, Coding, Robotika, AR, Sensor Fusion)** ke roadmap kanonis.
- Menambahkan file pengujian batas misi: `JAYA_CORE/tests/test_agentic_jarvis_mission_boundary.py` (23 test, PASS).

### Changed

- Mengubah `ArXivPatchEngine` menjadi `KnowledgeDeltaBuilder` di `agentic_jarvis.py`. Mengganti status pengembalian kandidat dari `"applied"` menjadi `"INDEXED_IN_RESEARCH_STORE"`.
- Memindahkan template BAB I-IV skripsi dari `HierarchicalTaskPlanner` ke `ThesisGoalDecompositionStrategy` terpisah via Strategy Pattern. Core planner sekarang domain-neutral secara default.
- Mengubah `ProactiveEngine.check_proactive_nudge` agar menggunakan `active_contexts: dict` yang domain-neutral alih-alih parameter spesifik `thesis_topic`/`current_chapter`.
- Mengubah deskripsi UI `ProjectListPage.jsx` untuk menampilkan JAYA Research sebagai CEL dan thesis sebagai domain adapter.
- Memperbarui `PRODUCT.md`, `ARCHITECTURE.md`, `GOVERNANCE.md`, `WORKFLOWS.md`, `STATUS.md`, dan `README.md` agar selaras dengan visi CEL dan Distributed Sovereign Intelligence.
- Menambahkan field `domain_context: Dict[str, str]` pada `UserProfile` di `episodic_memory.py` serta menandai field `thesis_topic`/`current_chapter` sebagai DEPRECATED.

---

## 2026-08-01 - Phase A lulus lokal, gate ilmiah tetap eksternal

### Added

- Menetapkan [kontrak penerimaan Phase A](ACCEPTANCE_CRITERIA.md) dengan status
  `PASS_LOCAL`, `PASS_REPRESENTATIVE`, `BLOCKED_EXTERNAL`, dan `FAIL`.
- Menambahkan dataset RAG v2 berlisensi dan terikat digest untuk contract smoke.
  Dataset aktif berstatus `SMOKE_ONLY`, bukan representatif.
- Menambahkan acceptance test deterministik untuk novelty/gap, grounded RAG,
  PDF ingestion, hypothesis/experiment, scientific synthesis, dan batas
  deep-research agent.
- Menambahkan workflow quality gate monorepo, dependency CI per komponen, audit
  keamanan Android, serta test runner yang mengisolasi namespace legacy.
- Menambahkan kontrak Deep Research UI untuk `/research/recursive`, termasuk
  status answered/abstain/conflict, citation/provenance, URI/SHA artefak, dan
  presentasi hasil non-promotable tanpa klaim mutasi Core.

### Changed

- Novelty dan gap gagal tertutup saat provider/corpus tidak cukup; graph yang
  terputus hanya menjadi candidate yang memerlukan review.
- PDF ingestion memakai status/error bertipe, provenance per halaman, batas
  file/halaman, dan provider OCR/table/figure yang eksplisit.
- RAG menghasilkan claim extractive bercitation, abstain pada bukti kosong atau
  lemah, melaporkan konflik, dan menolak digest yang berubah.
- Deep-research mengganti hasil retry per query, memisahkan draft model dari
  evidence, meneruskan hasil extractive ketika provider opsional gagal, serta
  menyimpan report write-once dengan run ID dan checksum.
- Label adapter/file tanpa lokasi sumber eksplisit tidak lagi dapat lolos
  sebagai complete provenance; blok chat generatif lama yang unreachable telah
  dihapus dari API.
- Hipotesis tanpa corpus tetap ungrounded; simulasi selalu non-empiris dan tidak
  promotable; empirical review eligibility memerlukan receipt reproduksi yang
  independen.
- Scientific writer, drafter, reviewer, dan editor menolak citation asing,
  tidak membuat bibliografi, menandai claim unsupported, dan tidak pernah
  memberi publication approval.
- Research hanya menghasilkan candidate/evidence artifact. Verifikasi,
  persetujuan manusia, canary, instalasi atomik, replay protection, dan rollback
  menjadi gate terpisah sebelum Core berubah.
- Konfigurasi Research/Core, API security, capability sandbox Agent/OS, model
  readiness, Android secret storage, dan jalur promosi diperketat agar gagal
  secara eksplisit ketika dependency atau bukti belum tersedia.
- Thesis session memakai repository SQLite WAL dengan revision tracking dan
  recovery untuk state yang terinterupsi.
- Auth UI kini menyimpan API key hanya di memori runtime dan memverifikasinya
  melalui operasi baca; transport memakai `ApiError` terstruktur,
  `Idempotency-Key`, dan kontrak CORS.
- Preview/download dokumen serta export tesis memakai transport Bearer yang
  sama; status index tesis yang unavailable tidak lagi disebut berhasil masuk
  RAG. Monitor evolution legacy diganti boundary `BLOCKED` tanpa request
  mutasi dan feature flag-nya nonaktif secara default.
- Persistence transcript chat tanpa consent di `localStorage` dihapus; chat
  sekarang memory-only sampai kontrak enkripsi, retention, dan deletion ada.
- Dependency `react-router` yang terkena advisory diganti router internal
  tervalidasi; toolchain UI dinaikkan ke Vite 8 dan halaman dipecah menjadi lazy
  chunks.
- Dependency UI langsung yang tidak dipakai dihapus, runner Electron dipindah
  ke dependency pengembangan, dan renderer Electron hanya menerima URL HTTP
  loopback dengan context isolation serta sandbox tanpa Node integration.

### Verified

- `python scripts/run_test_matrix.py --component research --quiet` menghasilkan
  **352 passed, 11 deselected** pada suite offline Research.
- Acceptance suite Phase A terarah menghasilkan 194 passed.
- Suite kontrak UI menghasilkan 12 passed; lint dan production build lulus;
  `npm audit` melaporkan 0 vulnerability.
- RAG contract fixture menghasilkan `LOCAL_SMOKE_PASSED` dengan
  `production_gate_passed=false` dan run default tidak terattestasi.
- Validator dokumentasi, repository layout audit, Ruff blocker, dan compile
  lulus pada run lokal yang dicatat selama hardening.

### Not completed

- Dataset dan run RAG representatif belum tersedia.
- Review domain/etik, eksperimen empiris nyata, model target final, benchmark
  hardware, dan perangkat Android fisik tetap `BLOCKED_EXTERNAL`.
- Browser E2E terhadap API ter-deploy, target deployment, dan provider live
  belum dibuktikan.
- Phase A belum production-ready atau publication-ready meskipun gate lokal
  lulus.

## 2026-07-30 - RETRACTED / SUPERSEDED

Entri sebelumnya menyebut `rag_representative_v1.json` berisi 11 kasus dan
menyatakan recall@5/MRR 90,9% sebagai hasil dataset representatif. Klaim itu
**ditarik** karena artefak tersebut tidak menjadi dataset evaluasi aktif yang
dapat diverifikasi. Klaim penyelesaian roadmap yang bergantung pada angka itu
juga tidak berlaku.

Penggantinya adalah `JAYA_RESEARCH/evaluation/rag_smoke_v2.json`, yang secara
eksplisit berstatus `SMOKE_ONLY`. Nilai smoke hanya membuktikan kontrak harness;
ia tidak boleh dipakai sebagai bukti mutu retrieval produksi. Gate yang benar
sekarang didefinisikan oleh [ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md).

Bagian thesis-session persistence dari pekerjaan tanggal tersebut telah diuji
ulang dalam hardening 1 Agustus dan dicatat pada entri terbaru di atas.

## 2026-07-26 - Program Research Truth dan Core Readiness

### Added

- Menambahkan `REMEDIATION_CHECKLIST.md` sebagai daftar kerja kanonis berbasis
  audit untuk menghapus hardcode, simulasi palsu, unsafe promotion, dan boundary
  yang tidak sesuai kegunaan modul.
- Menetapkan acceptance criteria serta gate eksternal yang wajib dipenuhi sebelum
  Research/Core dapat disebut verified atau production-ready.

## 2026-07-26 - Konsolidasi dokumentasi

### Changed

- Menetapkan `docs/` di root sebagai satu-satunya sumber dokumentasi aktif.
- Mengganti roadmap yang saling bertentangan dengan `ROADMAP.md` kanonis.
- Menambahkan definisi kematangan dan dashboard berbasis bukti di `STATUS.md`.
- Menyatukan visi, batas modul, alur discovery, dan target ekosistem.
- Menetapkan gerbang promosi Research ke Core yang membutuhkan tes/benchmark
  aktual, reproduksi, security review, persetujuan manusia, dan rollback.
- Mengubah README root/modul menjadi navigasi yang sejalan dengan dokumen
  kanonis.

### Archived

- Memindahkan dokumentasi modul lama ke `docs/archive/legacy-module-docs/`.
- Memindahkan PRD, SRS, masterplan, roadmap, dan catatan root lama ke
  `docs/archive/legacy-root-docs/`.
- Arsip dipertahankan untuk audit, tetapi tidak lagi menjadi spesifikasi aktif.

### Repository

- Menonaktifkan repository Git bersarang dari `JAYA_RESEARCH`; seluruh file kini
  dikelola repository Git di root monorepo.
- Memperbarui `.gitignore` agar dokumentasi aktif terlacak sementara referensi
  vendor dan arsip besar tetap lokal.

### Verification

- Menambahkan `scripts/validate_docs.py` untuk memeriksa struktur repository dan
  tautan dokumentasi.
- Menyelaraskan hook, instruksi agent, audit layout, dan workflow benchmark agar
  tidak membuat kembali dokumentasi modul.
