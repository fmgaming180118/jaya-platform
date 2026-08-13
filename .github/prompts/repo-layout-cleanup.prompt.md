---
name: "JAYA Repo Layout Cleanup"
description: "Audit and safely tidy files against the canonical root policy."
argument-hint: "Mode: audit-only or audit-and-fix"
agent: "agent"
---

Gunakan `docs/GOVERNANCE.md`, `docs/ARCHITECTURE.md`, dan
`docs/DECISIONS.md` sebagai kebijakan.

Alur:

1. Jalankan:
   - `python .github/tools/repo_layout_audit.py --json-out reports/repo-layout/audit-before.json`
   - `python scripts/validate_docs.py`
2. Untuk `audit-only`, laporkan lalu berhenti.
3. Untuk `audit-and-fix`, hanya lakukan perubahan yang ownership-nya jelas:
   - pindahkan source/test ke modul pemilik;
   - pindahkan seluruh dokumentasi aktif ke `docs/` root;
   - pindahkan report/log generated ke `reports/` atau lokasi runtime yang diabaikan;
   - jangan menghapus arsip, blueprint, data pengguna, atau perubahan yang tidak terkait.
4. Jangan menambah nested `.git` atau direct import antar-modul.
5. Jalankan ulang:
   - `python .github/tools/repo_layout_audit.py --json-out reports/repo-layout/audit-after.json`
   - `python scripts/validate_docs.py`

Laporan:

```text
Mode:
Policy:
Files moved:
Files deleted:
Audit before:
Audit after:
Remaining blockers:
Next actions:
```
