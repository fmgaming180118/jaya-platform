---
description: "Unified engineering, repository, safety, and documentation rules for the JAYA monorepo."
applyTo: "**"
---

# JAYA Unified Instructions

## 1. Sumber kebenaran

Dokumentasi aktif hanya berada di `docs/` root. Gunakan:

- `docs/PRODUCT.md` — tujuan, scope, dan ukuran sukses.
- `docs/ARCHITECTURE.md` — ownership dan batas modul.
- `docs/DECISIONS.md` — keputusan arsitektur aktif.
- `docs/WORKFLOWS.md` — state serta alur operasional.
- `docs/STATUS.md` — fakta implementasi dan risiko.
- `docs/ROADMAP.md` — prioritas, dependency, dan exit criteria.
- `docs/GOVERNANCE.md` — evidence, security, autonomy, promotion, approval.
- `docs/DEVELOPMENT.md` — setup, test, dan checklist perubahan.

README module hanya ringkasan. Dilarang membuat `<MODULE>/docs/`. Dokumen lama
di `docs/archive/` tidak menjadi spesifikasi aktif. Report/benchmark generated
masuk `reports/`, bukan folder dokumentasi.

## 2. Repository dan ownership

- Satu monorepo, satu `.git` di root.
- `JAYA_RESEARCH`: ingestion, RAG, thesis, literature, graph, discovery, evidence.
- `JAYA_CORE`: intent, reasoning, planning, memory policy, JayaIR, executor.
- `JAYA_AGENT`: task/tool orchestration dan permission flow.
- `JAYA_OS`: runtime, device/resource policy, sandbox.
- `JAYA_ANDROID`: UI mobile, cache, dan transport.
- Source, tests, dan runtime asset tetap di modul pemilik.
- Jangan membuat scratch, log, test, atau dokumen ad-hoc di root.
- Jangan mengubah blueprint, data pengguna, atau perubahan pengguna lain tanpa scope.

## 3. Boundary dan kontrak

- Tidak ada direct import internal antar-modul.
- Tidak ada shared mutable state atau penulisan source lintas modul.
- Integrasi memakai kontrak publik/versioned melalui API, message, atau artifact.
- Perubahan kontrak membutuhkan schema/version, compatibility test, migration,
  owner review, dan rollback.
- JayaIR Phase 1 v0.1 dibekukan sesuai `docs/DECISIONS.md`.
- Boundary `brain_v2` (resident) dan `os_kernel` (home) harus lulus architecture test.

## 4. Evidence dan promosi

Research tidak mengubah Core. Ia menghasilkan paket artefak berisi manifest,
evidence, payload, tests, benchmark, dan signature.

Promosi wajib melalui:

1. provenance dan reproducibility;
2. schema/hash/license validation;
3. isolated sandbox;
4. test runner serta benchmark aktual;
5. security review;
6. human approval;
7. signed install lewat adapter publik;
8. observability dan rollback.

Boolean dari caller seperti `tests_passed=true` bukan bukti. Direct-write bridge
tidak boleh menjadi jalur produksi.

## 5. Eksperimen dan otonomi

- Simpan seed, dataset/version/license, config, environment, log, dan result.
- Random/mock/synthetic output wajib berstatus `SIMULATION`.
- Jangan menjalankan loop `--forever`, daemon self-mutation, auto-finetune,
  auto-promotion, atau continuous discovery tanpa consent eksplisit.
- Setiap run otonom membutuhkan scope, budget, timeout, quota, audit, checkpoint,
  cancel/kill switch, dan review manusia untuk dampak lintas modul.
- Tool dan eksperimen memakai izin minimum serta sandbox.

## 6. Security dan privacy

- Jangan commit secret, credential, `.env`, data privat, database, PDF, model,
  log, atau artefak runtime.
- Validasi path, MIME, ukuran, checksum, dan input eksternal.
- Network/tool call membutuhkan allowlist, timeout, quota, dan error handling.
- Jangan mencetak secret atau isi sensitif ke log.
- Jelaskan data yang keluar perangkat ketika provider cloud digunakan.

## 7. Engineering workflow

Sebelum edit:

1. Analyze struktur, Git status, dokumen pemilik, code, dan tests.
2. Plan scope, acceptance criteria, boundary, security, dan rollback.
3. Review agar tidak menimpa perubahan pengguna atau melanggar gate.

Saat implementasi:

- Gunakan syntax modern, type hints, modular service/repository.
- Jangan pakai state global untuk job/sesi persisten.
- Jangan buat `try/except` kosong.
- Retry harus idempotent; error harus dapat ditindaklanjuti.
- Feature berisiko default-nya nonaktif.
- Test tidak boleh menulis source production.

Sebelum selesai:

- Jalankan test/linter/benchmark sesuai `docs/DEVELOPMENT.md`.
- Laporkan scope test dan apakah terisolasi atau suite penuh.
- Perbarui `STATUS.md`, `ROADMAP.md`, dan `CHANGELOG.md` bila status berubah.
- Jalankan `python scripts/validate_docs.py`.

## 8. Minimum validation

Core:

```powershell
python -m pytest packages\jaya-core\tests\test_phase1_jaya_ir.py -q
python -m pytest packages\jaya-core\tests\test_phase1_ir_benchmark.py packages\jaya-core\tests\test_phase1_benchmark_gate.py packages\jaya-core\tests\test_phase1_architecture_boundary.py -q
python -m pytest packages\jaya-core\tests\test_phase2_evolution_gate.py packages\jaya-core\tests\test_phase2_rollback.py packages\jaya-core\tests\test_phase2_manifest.py -q
```

Research menggunakan test terarah sesuai area. API baseline:

```powershell
python -m pytest packages\jaya-research\tests\test_research_api_phase_a.py -q
```

Gunakan command benchmark dari `docs/DEVELOPMENT.md`; simpan JSON di
`outputs/reports/benchmarks/`.

## 9. Review

- Perubahan Core reasoning/JayaIR, OS policy, Agent permission, model registry,
  promotion gate, atau security memerlukan review owner terkait.
- PR mencantumkan dampak kompatibilitas, bukti test, risiko, dan rollback.
- Status `VERIFIED`/`PRODUCTION` hanya diberikan jika seluruh bukti pada
  `docs/GOVERNANCE.md` tersedia.
