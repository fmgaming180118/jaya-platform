# Dokumen Ceklis Status dan Penuntasan Fase JAYA

**Baseline:** 2 Agustus 2026  
**Standar Validasi:** `AGENTS.md`, `ACCEPTANCE_CRITERIA.md`, dan `STATUS.md`  

Dokumen ini mencatat rencana dan status verifikasi ceklis penuntasan komponen perangkat lunak per fase dalam arsitektur JAYA.

---

## 1. Ceklis Penuntasan Fase 0 — Konsolidasi Repository & Dokumen
- [x] Dokumentasi aktif berada di `docs/` (24 file kanonis).
- [x] README modul menunjuk ke sumber kanonis.
- [x] Hanya satu `.git` root yang menjadi repository.
- [x] Validator memeriksa struktur, tautan, dan keterlacakan source/test.

---

## 2. Ceklis Penuntasan Fase A — Research Foundation (Dual-Track Baseline)
- [x] Workspace, validasi input, upload, dan source artifact memiliki batas ukuran/path serta failure code eksplisit.
- [x] Ingest sumber, retrieval, abstention, citation/provenance, dan pembukaan sumber terintegrasi dalam alur API offline.
- [x] **Dual-Track Research Baseline**: Terpisah tegas antara Evolusi Kognitif Internal (`Candidate Cognitive Artifact`) dan Penemuan Rekayasa Eksternal (`Discovery Artifact`).
- [x] **16-Step Discovery Pipeline**: Penerjemahan ide fiksi (studi kasus Arc Reactor), constraint fisika, falsifikasi, dan ekspor `REJECTED_HYPOTHESIS`.
- [x] Suite Research offline lulus (352 passed).
- [ ] *[BLOCKED_EXTERNAL]* Evaluasi pada dataset RAG representatif masif.
- [ ] *[BLOCKED_EXTERNAL]* Review novelty dan fiting ilmiah oleh reviewer pakar manusia.

---

## 3. Ceklis Penuntasan Fase B — Production Hardening & JAYA Core Kernel
- [x] Persistensikan sesi dengan repository SQLite dan recovery state.
- [x] **Portable Cognitive Kernel (11 Komponen)**: Identitas, Resource Profiler, Mode Controller, Capability Registry, Model Router, Memory SQLite, Intent Engine, Context Manager, Planner, Decision Gate, Evaluator (`JayaCoreRuntime`).
- [x] State machine job, progress, cancel, resume, retry, dan idempotency pada kontrak lokal.
- [x] Benchmark footprint memori ringan: RSS delta kernel hanya 0.89 MB (RAM Total ~25 MB).
- [x] **Background Job Worker Queue**: Isolation handler untuk job berdurasi panjang, thread pool, retry backoff, dan `BackgroundJobWorker`.
- [x] **Correlation ID Tracing**: Context-local correlation ID propagation untuk audit log terstruktur lintas modul (`TraceContext`).
- [x] **SQLite Backup & Crash Recovery Engine**: Hot online backup snapshot, verifikasi checksum integritas, dan automated crash recovery drill (`SQLiteBackupEngine`).
- [x] **Clean Install & Process Restart Drill**: Verifikasi inisialisasi zero-state, readiness probes, dan survival memori episodik pasca-restart (`verify_clean_install_and_restart.py`).

---

## 4. Ceklis Penuntasan Fase C — Edge & Hybrid Intelligence
- [x] Resource profiler otomatis (`CENTRAL`, `STANDARD`, `EDGE`, `CONSTRAINED`).
- [x] Matriks mode operasi (`ONLINE_FULL`, `ONLINE_DEGRADED`, `OFFLINE_AUTONOMOUS`, `OFFLINE_SAFE`, `EMERGENCY`).
- [x] Capability Negotiator untuk penentuan eksekusi lokal vs remote offload.
- [x] **Student Dataset Specification**: Spesifikasi dataset legal, bersih, dan versioned (`StudentDatasetSpec` & `StudentDatasetValidator`).
- [x] **GGUF Q4 Quantization Contract**: Contract Evaluator untuk memastikan model GGUF Q4 memenuhi target <300 MB size, <=512 MB RAM, <500 ms latency, dan thermal <45°C (`GGUFQuantizationContract`).
- [x] **Privacy-Aware Hybrid Model Router**: Rute otomatis prompt sensitif ke Local Edge dan fallback eksplisit saat offline (`HybridModelRouter`).
- [x] **Edge Model Registry**: Registrasi model, verifikasi tanda tangan SHA-256, pengecekan kompatibilitas, dan automated model rollback (`EdgeModelRegistry`).

---

## 5. Ceklis Penuntasan Fase D — Discovery Empiris & Multimodal Physical AI
- [x] Formulasi spesifikasi rekayasa terukur dari ide abstrak/fiksi (`FictionToRequirementTranslator`).
- [x] Uji falsifikasi fisika terverifikasi terhadap Lawson Criterion & batas termodinamika (`PhysicsFalsificationEngine`).
- [x] Generator `REJECTED_HYPOTHESIS` untuk mempublikasikan alasan numerik kegagalan hipotesis/desain.
- [x] Adapter OpenUSD (`OpenUSDGeometryAdapter`) dan PhysX (`PhysXSolverAdapter`).
- [x] Agregasi `DigitalTwinBuilder` untuk paket OpenUSD + data overlay simulasi fisika.
- [ ] *[BLOCKED_EXTERNAL]* Uji prototipe fisik & feedback eksperimen laboratorium nyata.

---

## 6. Ceklis Penuntasan Fase E — Promosi Aman ke Ekosistem
- [x] Readines gate fail-closed (`CognitiveArtifactGate`): `executable=false`, `auto_install=false`, `human_review_required=true`.
- [x] Candidate-only rule: Modul Research dilarang mengubah source Core secara langsung.
- [x] **Cognitive Promotion Engine**: Canary staging (`stage_canary`), monitoring regresi (`report_canary_metrics`), dan automated rollback drill (`error_rate > 0.05`).
- [x] Wajib persetujuan manusia (`human_approved=True`) sebelum promosi akhir ke Core.

---

## 7. Ceklis Penuntasan Fase G — Distributed Node & JAYA Mesh
- [x] Dokumen arsitektur terinci: [`docs/JAYA_MESH_DESIGN.md`](JAYA_MESH_DESIGN.md) & `ADR-010`.
- [x] **Node Registry**: Pendaftaran 5 Tier Node (Central, Standard, Edge, Mission, Micro), heartbeat, dan penyaringan capability (`NodeRegistry`).
- [x] **Mesh Sync Engine**: Pertukaran `NodeEvent` batch terenkripsi/signed, deduplikasi, dan `SyncCursor` tracking.
- [x] **Deterministic Conflict Resolution**: Resolusi konflik event berbasis sequence number, timestamp, dan node ID priority tie-breaker.
- [ ] Kompilasi dan pengujian fisik langsung di Raspberry Pi RAM ≤ 512 MB.

---

## 8. Ceklis Penuntasan Fase H — Advanced Capabilities (3D CAD & Solvers)
- [x] Dokumen arsitektur terinci: [`docs/DISCOVERY_PIPELINE_DESIGN.md`](DISCOVERY_PIPELINE_DESIGN.md) & `ADR-011`.
- [x] **OpenUSD 3D Parametric Geometry Adapter**: Penggenerasian script `.usda` stage OpenUSD.
- [x] **PhysX Multiphysics Solver Adapter**: Wrappers simulasi percepatan, rigid body, dan batas tegangan FEA.
- [x] **Digital Twin Bundle Builder**: Mengagregasikan geometri 3D OpenUSD dan overlay data simulasi fisika.
- [ ] Integrasi live GPU CUDA / Omniverse Kit-CAE runtime eksternal.

---

## Command Verifikasi Ceklis

```powershell
# 1. Verifikasi Dokumentasi Kanonis
python scripts/validate_docs.py

# 2. Verifikasi Layout Repository
python .github/tools/repo_layout_audit.py --fail-on-violations

# 3. Verifikasi Suite Test JAYA Core (72 test)
python -m pytest JAYA_CORE/tests/ -v

# 4. Verifikasi Suite Test JAYA Research (7 test)
python -m pytest JAYA_RESEARCH/tests/test_scientific_discovery.py JAYA_RESEARCH/tests/test_solver_adapters.py -v
```
