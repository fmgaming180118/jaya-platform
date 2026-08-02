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
| ADR-009 | JAYA Research adalah Cognitive Evolution Laboratory; thesis adalah domain adapter; Core mutation langsung dilarang | Accepted |
| ADR-010 | JAYA adalah Distributed Sovereign Intelligence; JAYA Core terdiri dari Cognitive Kernel portabel dan Capability Packs; JAYA Mesh adalah lapisan sinkronisasi resmi | Accepted |
| ADR-011 | JAYA Research menganut Dual-Track Architecture: Cognitive Evolution Research (Internal) dan Scientific & Engineering Discovery (External/3D/Physical AI); Omniverse/Solvers adalah optional capability providers | Accepted |

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

## ADR-009 — JAYA Research adalah Cognitive Evolution Laboratory

**Status:** Accepted
**Tanggal:** 2 Agustus 2026

### Konteks

Repository mengalami mission drift di beberapa titik:

1. Dokumentasi produk terlalu berpusat pada mahasiswa dan tugas akhir.
2. Contoh dan default di `AgenticJarvis` terlalu berpusat pada BAB skripsi.
3. Proactive engine memiliki parameter spesifik domain tesis.
4. `ArXivPatchEngine.apply_micro_patch` mengembalikan `status: "applied"` yang
   menyiratkan aktivasi tanpa promotion gate.
5. UI menampilkan thesis sebagai identitas utama sistem.

### Keputusan

**JAYA Research adalah Cognitive Evolution Laboratory (CEL) — bukan aplikasi tesis.**

1. Research menghasilkan candidate cognitive artifact, bukan perubahan aktif.
2. Thesis adalah domain adapter opsional, bukan tujuan utama sistem.
3. Core mutation langsung dari Research dilarang tanpa exception.
4. Self-improvement berarti candidate generation dan gated promotion, bukan auto-apply.
5. Activation tetap memerlukan: evidence, gate, approval, canary, observability, rollback.
6. Core planner bersifat domain-neutral. Domain template didaftarkan via strategy pattern.
7. Proactive engine menggunakan `active_contexts` (dict generic), bukan `thesis_topic`.
8. Status knowledge candidate adalah `INDEXED_IN_RESEARCH_STORE`, bukan `applied`.

### Konsekuensi

- `HierarchicalTaskPlanner` menggunakan `GoalDecompositionStrategy` registry.
- `ThesisGoalDecompositionStrategy` ada sebagai optional strategy, bukan hardcoded Core.
- `ArXivPatchEngine` diubah namanya menjadi `KnowledgeDeltaBuilder`;
  `apply_micro_patch` deprecated dan dikembalikan dengan `INDEXED_IN_RESEARCH_STORE`.
- `ProactiveEngine.check_proactive_nudge` tidak menerima `thesis_topic`/`current_chapter`.
- Terminologi `applied`, `deployed`, `installed` dilarang untuk kandidat yang belum
  melewati promotion gate.
- UI tidak boleh menampilkan deskripsi yang menyiratkan Core mutation.

## ADR-010 — JAYA sebagai Distributed Sovereign Intelligence

**Status:** Accepted
**Tanggal:** 2 Agustus 2026

### Konteks

Visi JAYA sebagai asisten seperti JARVIS (Iron Man) memerlukan kemampuan untuk:

1. Hadir di banyak perangkat secara bersamaan dalam satu identitas.
2. Tetap berfungsi secara terbatas saat koneksi terputus.
3. Menyatukan kembali pengalaman dan memori saat tersambung.
4. Berjalan di perangkat dengan resource sangat kecil (ESP32, Raspberry Pi, ponsel).
5. Menggunakan kemampuan berat dari node yang lebih kuat melalui delegasi.

Arsitektur sebelumnya mendefinisikan JAYA sebagai sistem monolith tunggal dengan
tiga mode deployment (local, hybrid, edge/offline) tetapi tidak mendefinisikan
bagaimana node berinteraksi, bagaimana sinkronisasi terjadi, dan bagaimana Core
dapat berjalan di perangkat kecil.

### Keputusan

1. **JAYA adalah Distributed Sovereign Intelligence** — satu identitas kognitif
   dengan banyak manifestasi node.
2. **Setiap node** adalah manifestasi JAYA, bukan instansi AI yang berbeda.
3. **JAYA Core terdiri dari dua lapisan:**
   - Cognitive Kernel: bagian minimum yang portabel ke semua node
   - Capability Packs: modul yang dipasang sesuai resource perangkat
4. **Lima tier node** didefinisikan: Central, Standard, Edge, Mission Node, Micro Node.
5. **JAYA Mesh** adalah lapisan sinkronisasi resmi antarnode:
   - Event-based (bukan database copy)
   - Offline-first
   - Signed everything
   - Zero implicit trust
6. **Model bahasa adalah mesin, bukan identitas** — mengganti model tidak mengganti
   JAYA.
7. **Budget-aware reasoning** — Core memilih strategi berdasarkan resource tersedia.
8. **Capability Negotiation** — node mendelegasikan tugas ke node yang memiliki
   capability yang dibutuhkan.

### Konsekuensi

- `JAYA_CORE/` akan mengembangkan `cognitive_kernel/` sebagai komponen portabel.
- Capability Packs akan dipasang sebagai modul opsional, bukan dependency wajib.
- JAYA Mesh akan dikembangkan sebagai modul terpisah (mulai Fase B).
- Dokumen desain dibuat: `JAYA_CORE_DESIGN.md` dan `JAYA_MESH_DESIGN.md`.
- Semua komponen JAYA harus mendefinisikan perilaku offline dan sinkronisasi.
- Dokumentasi tidak boleh mengklaim implementasi yang belum ada — semua fitur
  distribusi saat ini berstatus IDEA.

### Status implementasi

| Komponen | Status |
|---|---|
| Cognitive Kernel (portabel) | IDEA |
| Capability Packs | IDEA (beberapa PROTOTYPE) |
| JAYA Mesh | IDEA |
| Node Identity Protocol | IDEA |
| Event Sync Protocol | IDEA |
| Offline Behavior Modes | IDEA |
| Budget-Aware Reasoning | PROTOTYPE |
| Capability Negotiation | IDEA |

## ADR-011 — Dual-Track JAYA Research Architecture (Cognitive Evolution & Scientific Discovery)

**Status:** Accepted  
**Tanggal:** 2 Agustus 2026  

### Konteks

Definisi JAYA Research sebelumnya terlalu sempit karena seluruh output diarahkan kembali untuk memperbarui JAYA Core. Pengguna memerlukan JAYA Research untuk tidak hanya meneliti perbaikan internal JAYA, tetapi juga **meneliti masalah rekayasa dan fenomena ilmiah di dunia nyata** (seperti penerjemahan konsep reaktor portabel, material baru, 3D CAD, simulasi fisika, dan digital twin).

### Keputusan

1. **JAYA Research menganut Dual-Track Architecture:**
   - **Track 1: Cognitive Evolution Research (Internal)**: Meneliti cara memperbaiki JAYA sendiri $\rightarrow$ `Candidate Cognitive Artifact`.
   - **Track 2: Scientific and Engineering Discovery (External / Physical AI / 3D)**: Meneliti dunia luar, rekayasa 3D CAD, fisika, material, dan digital twin $\rightarrow$ `Discovery Artifact` / `REJECTED_HYPOTHESIS`.
2. **16-Step Scientific & Engineering Discovery Pipeline** ditetapkan sebagai standar alur riset eksternal (Fiction-to-Requirement → Physics Constraints → Falsification → 3D Parametric → Multiphysics → Digital Twin → Discovery Artifact).
3. **Pemberlakuan Rejection / Falsification First**: Eksperimen yang membuktikan desain atau hipotesis gagal diterbitkan sebagai **`REJECTED_HYPOTHESIS`** yang bernilai ilmiah.
4. **NVIDIA Omniverse, OpenUSD, dan Solver Domain** (PhysX, FEA, CFD, EM, Modulus) berkedudukan sebagai **Optional / Remote Capability Providers**. Tidak ada dependency GPU/CUDA/Omniverse yang diwajibkan dalam base installation JAYA Core.
5. **Dokumen Desain**: Dibuat [`docs/DISCOVERY_PIPELINE_DESIGN.md`](DISCOVERY_PIPELINE_DESIGN.md).

### Konsekuensi

- Module `JAYA_RESEARCH` menambahkan paket `src/discovery/` untuk menangani requirement translation, physics falsification, dan discovery contracts.
- Jenis artefak baru ditambahkan: `DISCOVERY_CANDIDATE`, `PARAMETRIC_GEOMETRY`, `DIGITAL_TWIN`, `REJECTED_HYPOTHESIS`, `SIMULATION_RESULT`, `ENGINEERING_REQUIREMENTS`, `SCIENTIFIC_HYPOTHESIS`.
- Penemuan ilmiah fiksi (seperti Arc Reactor) diterjemahkan secara jujur menjadi spesifikasi rekayasa terukur, faktor penolak (blockers), dan sub-masalah penelitian terisolasi.

## Proses keputusan baru

1. Tambahkan baris ADR dengan ID berikutnya dan status `Proposed`.
2. Jelaskan konteks, opsi, trade-off, dampak keamanan, dan migration.
3. Dapatkan review owner terdampak.
4. Ubah menjadi `Accepted` atau `Rejected`.
5. Selaraskan Architecture, Status, Roadmap, dan Changelog.

Keputusan `Accepted` tidak diubah diam-diam. Penggantinya mendapat ID baru dan
keputusan lama ditandai `Superseded by ADR-xxx`.

