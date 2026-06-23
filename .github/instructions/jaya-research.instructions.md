---
applyTo: JAYA_RESEARCH/**
title: JAYA_RESEARCH Instructions
description: Safe experimentation defaults, workflows, and rules for research artifacts.
---

# JAYA_RESEARCH Instructions

## Ringkasan
Instruksi ini berlaku khusus untuk semua file di `JAYA_RESEARCH/`. Fokus pada kebebasan eksperimen yang aman: isolasi, reproducibility, dan jalur promosi yang jelas menuju `JAYA_CORE`.

## Prinsip Utama
- **Isolated experimentation:** Eksperimen boleh bergantung pada dependensi tambahan, tetapi harus diisolasi ke `JAYA_RESEARCH` (virtualenv/requirements terpisah, container).
- **No autonomous forever loops:** Skrip dengan flag seperti `--forever` harus berlabel jelas, memiliki `--dry-run`, dan memerlukan persetujuan operator sebelum dijalankan di lingkungan produksi.
- **Reproducible runs:** Simpan seeds, parameter, dan snapshot dataset yang dipakai.

## Data & Datasets
- Simpan dataset eksperimen di `JAYA_RESEARCH/data/` dan catat sumber, lisensi, dan versi.
- Hindari memasukkan data sensitif ke repo. Jika perlu, berikan panduan akses eksternal dan placeholder.

## Eksperimen Rekursif (Recursive)
- Implementasi prototipe recursive atau self-improving harus:
  - Dijabarkan dalam dokumen `JAYA_RESEARCH/docs/` dengan failure modes, safety mitigations, dan resource bounds.
  - Dijalankan di sandbox terisolasi; jangan jalankan langsung di mesin developer tanpa pengamanan.

## Promosi ke `JAYA_CORE`
- Untuk mempromosikan artefak riset ke core, sediakan:
  - Kontrak API publik dan spesifikasi input/output.
  - Tes integrasi minimal dan dokumentasi penggunaan.
  - Review oleh tim core dan checklist compliance (security, license, performance).

## CI & Environment
- `JAYA_RESEARCH` boleh memiliki `requirements.txt` atau workflow eksperimen sendiri, tetapi jelaskan step setup di `JAYA_RESEARCH/README.md`.
- Gunakan environment isolation (venv, conda, container) untuk menghindari polusi dependency global.

## Governance
- Eksperimen berisiko tinggi (mis. internet-access agents, automated deployment) harus mendapat persetujuan tertulis dari maintainers dan keamanan.

## Contoh Checklist Eksperimen
- Deskripsi eksperimen di `JAYA_RESEARCH/docs/`
- Parameter dan seed tersimpan
- Data provenance dan lisensi dicatat
- Sandbox dan resource bounds didefinisikan
---
description: "Use when editing JAYA_RESEARCH experiments, research workflows, evolution scripts, or research tests. Enforces safe experimentation defaults, focused tests, environment checks, and no autonomous loops unless explicitly requested."
name: "JAYA Research Safety Defaults"
applyTo: "JAYA_RESEARCH/**"
---
# JAYA Research Safety Defaults

- Keep experiments isolated and reversible.
- Do not import from `JAYA_CORE` in `JAYA_RESEARCH` code.
- Prefer focused test runs over full-suite execution during iteration.
- Check environment dependencies before network workflows (for example `.env` values and API keys).
- Require graceful fallback behavior when external services are unavailable.
- Put research documentation in `JAYA_RESEARCH/docs/` (except `JAYA_RESEARCH/README.md`).

## Safe Execution Policy
- Do not run autonomous self-mutation loops unless the user explicitly asks:
  - `python JAYA_RESEARCH/src/discovery.py --forever`
  - `python JAYA_RESEARCH/src/jit_discovery.py --forever`
- Prefer bounded and auditable commands in normal development flow.

## Validation Defaults
- Install dependencies only when needed: `pip install -r JAYA_RESEARCH/requirements.txt`
- Prefer focused tests for touched area, for example:
  - `python -m pytest JAYA_RESEARCH/tests/test_crucible.py -v`
  - `python -m pytest JAYA_RESEARCH/tests/test_research_memory.py -v`

## Source Of Truth
- `JAYA_RESEARCH/README.md`
- `JAYA_RESEARCH/docs/RESEARCH_ASSISTANT.md`
- `JAYA_RESEARCH/docs/architecture.md`
