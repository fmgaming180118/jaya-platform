---
applyTo: JAYA_CORE/**
title: JAYA_CORE Instructions
description: Rules and gates for editing the JAYA_CORE runtime, JayaIR, and core tests.
---

# JAYA_CORE Instructions

## Ringkasan
Instruksi ini berlaku khusus untuk semua file di `JAYA_CORE/`. Tujuannya menjaga integritas runtime inti (sovereign), menjamin determinisme, keamanan, dan kinerja yang dapat diaudit.

## Prinsip Utama
- **Boundary-first:** Hindari impor atau dependensi langsung dari `JAYA_RESEARCH` ke `JAYA_CORE`. Semua integrasi riset harus melalui artefak yang diekspor dan di-review.
- **Minimal dependency:** Tambahkan dependensi hanya setelah evaluasi risiko dan manfaat; jelaskan alasan di PR.
- **Determinisme & Reproducibility:** Semua eksperimen yang mempengaruhi runtime harus menyertakan seed, versi dataset, dan konfigurasi yang diperlukan untuk reproduksi.

## Gates & Tes
- Perubahan yang menyentuh JayaIR, opcode, atau schema harus disertai dengan:
  - Tes unit yang memperlihatkan backward-compatibility atau migrasi.
  - Dokumentasi handoff (`JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md` atau file terkait).
  - Evaluasi benchmark jika perubahan berdampak performa.
- Jalankan target tests sebelum merge:
  - `python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v`
  - Gate benchmark: jalankan skrip benchmark yang relevan dan lampirkan snapshot JSON bila perlu.

## Keamanan & Operasional
- Jangan pernah memasukkan secrets, API keys, atau credential kedalam repo. Gunakan secret manager dan environment variables.
- Perubahan yang menambahkan kemampuan runtime baru harus menjelaskan failure modes dan rollback plan.

## Performance Budgets
- Set batasan p50/p95 untuk operasi kritikal yang disusun di benchmark gate. Jika ada regresi performa, perubahan harus mengandung mitigasi atau revert plan.

## Review & Ownership
- Semua PR yang menyentuh `JAYA_CORE` harus direview oleh pemilik domain (core maintainers). Sertakan changelog singkat, compatibility notes, dan langkah rollback.

## Packaging & Release
- Artefak runtime selesai harus dikemas agar konsisten: versi semantik, changelog, dan checksum.

## Promosi Artefak dari `JAYA_RESEARCH`
- Artefak riset yang ingin dipromosikan ke core harus memiliki:
  - Deskripsi kemampuan + kontrak API publik.
  - Tes integrasi minimal yang menjalankan artefak dalam container/sandbox.
  - Audit dependency dan lisensi.
  - Approval dari core maintainers.

## Contoh Checklist PR
- Menambahkan unit tests
- Menambahkan entry pada `JAYA_CORE/docs/` bila perlu
- Menjalankan benchmark gate bila perubahan performa
- Menyebutkan reviewer core maintainers
---
description: "Use when editing JAYA_CORE runtime, brain_v2 modules, JayaIR schema, evolution gate, or core tests. Enforces boundary checks, benchmark policy, and minimal dependency defaults."
name: "JAYA Core Guardrails"
applyTo: "JAYA_CORE/**"
---
# JAYA Core Guardrails

- Keep changes inside JAYA_CORE unless the user explicitly requests cross-folder work.
- Do not import from `JAYA_RESEARCH` in `JAYA_CORE` code.
- Preserve resident and home ownership boundaries:
  - Do not add direct `src/brain_v2` imports of `src/os_kernel`.
  - If boundary rules must change, update architecture docs and tests in the same change.
- Treat JayaIR Phase 1 as frozen (`v0.1`): avoid opcode/schema drift unless the change is explicitly requested and documented.
- Prefer low-resource implementations and avoid heavy new dependencies unless benefit is measurable.
- Put core documentation in `JAYA_CORE/docs/` (except `JAYA_CORE/README.md`).

## Validation Defaults
- Prefer VS Code tasks from `.vscode/tasks.json` when available.
- For JAYA_CORE code changes, run targeted gates:
  1. `python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v`
  2. `python -m pytest JAYA_CORE/tests/test_phase1_ir_benchmark.py JAYA_CORE/tests/test_phase1_benchmark_gate.py JAYA_CORE/tests/test_phase1_architecture_boundary.py -v`
  3. `python -m pytest JAYA_CORE/tests/test_phase2_evolution_gate.py JAYA_CORE/tests/test_phase2_rollback.py JAYA_CORE/tests/test_phase2_manifest.py -v`
  4. `python JAYA_CORE/scripts/benchmark_phase1_ir.py --rounds 40 --gate --fail-on-gate --max-warm-p50-ms 0.05 --max-warm-p95-ms 0.10 --min-hit-rate 0.95`

## Source Of Truth
- `JAYA_CORE/docs/PHASE1_DECISION_LOG.md`
- `JAYA_CORE/docs/PHASE1_TO_PHASE2_HANDOFF.md`
- `JAYA_CORE/docs/PHASE1_EXIT_CHECKLIST.md`
- `JAYA_CORE/tests/test_phase1_architecture_boundary.py`
