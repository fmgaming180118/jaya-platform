# JAYA Repository Guidelines

## Source of truth

Semua dokumentasi aktif berada di `docs/` root:

- `docs/STATUS.md` untuk kondisi aktual.
- `docs/ROADMAP.md` untuk prioritas dan exit criteria.
- `docs/ARCHITECTURE.md` untuk ownership/boundary.
- `docs/DECISIONS.md` untuk keputusan arsitektur aktif.
- `docs/GOVERNANCE.md` untuk keamanan, otonomi, dan promosi.
- `docs/DEVELOPMENT.md` untuk command serta checklist.

README modul hanya pintu masuk. Jangan membuat `<MODULE>/docs/` atau roadmap
baru. Laporan/benchmark generated masuk `reports/`, bukan `docs/`.

## Repository layout

- Repository adalah monorepo dengan satu `.git` di root.
- Source/test tetap berada pada modul pemilik:
  `JAYA_RESEARCH`, `JAYA_CORE`, `JAYA_AGENT`, `JAYA_OS`, atau `JAYA_ANDROID`.
- Hindari file scratch/log/test ad-hoc di root.
- Jangan mengubah snapshot blueprint atau data pengguna tanpa permintaan eksplisit.
- Jangan menyentuh perubahan pengguna yang tidak berkaitan.

## Architecture

- Modul tidak boleh saling import internal atau menulis source modul lain.
- Integrasi memakai API/message/artifact contract yang versioned.
- Research hanya menghasilkan evidence artifact; promosi wajib melewati seluruh
  gate pada `docs/GOVERNANCE.md`.
- JayaIR Phase 1 v0.1 dibekukan sesuai `docs/DECISIONS.md`.
- Boundary resident `JAYA_CORE/src/brain_v2` dan home
  `JAYA_CORE/src/os_kernel` harus dipertahankan.

## Safety

- Jangan commit secret, `.env`, data privat, database, model, log, atau artefak runtime.
- Jangan menjalankan `--forever`, daemon self-mutation, atau continuous discovery
  tanpa persetujuan eksplisit operator, batas, audit, dan kill switch.
- Output random/mock/sintetis wajib dilabeli `SIMULATION`.
- Test tidak boleh menulis source production.

## Build and test

Gunakan test terarah dari `docs/DEVELOPMENT.md`. Untuk Core:

```powershell
python -m pytest JAYA_CORE\tests\test_phase1_jaya_ir.py -q
python JAYA_CORE\scripts\benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate
```

Untuk Research:

```powershell
python -m pytest JAYA_RESEARCH\tests\test_research_api_phase_a.py -q
```

Sebelum selesai:

```powershell
python scripts\validate_docs.py
```

Perubahan status fitur harus memperbarui `docs/STATUS.md`,
`docs/ROADMAP.md`, dan `docs/CHANGELOG.md` dalam perubahan yang sama.
