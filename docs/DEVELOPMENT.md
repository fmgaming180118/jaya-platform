# Panduan Pengembangan

## Prasyarat

- Windows PowerShell atau shell setara.
- Python 3.11+ untuk tooling root.
- Node.js `^20.19.0` atau `>=22.12.0` dan npm untuk UI Research (requirement
  Vite 8 pada lockfile aktif).
- JDK/Android SDK untuk JAYA Android.
- Kredensial inference opsional sesuai provider yang digunakan.

Jangan commit `.env`, key, database, PDF pengguna, model, log, atau hasil
eksperimen.

## Setup JAYA Research

Dari root repository:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r JAYA_RESEARCH\requirements.txt
Copy-Item JAYA_RESEARCH\.env.example JAYA_RESEARCH\.env
```

Isi credential yang diperlukan di `JAYA_RESEARCH/.env`. Jangan menaruh nilai
secret di dokumentasi atau command history yang dibagikan.

UI:

```powershell
Set-Location JAYA_RESEARCH\ui
npm ci
npm run dev
```

API, dari root:

```powershell
python JAYA_RESEARCH\src\network\research_api.py
```

Default development URL:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`
- UI: `http://localhost:5173`

### Konfigurasi auth Research tanpa membocorkan secret

`JAYA_RESEARCH_API_KEYS` wajib berupa JSON list credential dengan field
`key_id`, `secret`, `subject`, `scopes`, dan `workspace_ids`. Buat nilainya di
secret manager atau konfigurasi environment proses deployment, lalu injeksikan
ke proses API; jangan menaruh nilai literal di repository, dokumentasi, file
build UI, atau command history yang dibagikan.

Setelah API berjalan, buka UI dan masukkan credential yang sesuai pada field
**Research API key**. Gate memverifikasi key dengan operasi baca workspace.
Nilai key hanya hidup di memori tab, tidak ditulis ke `localStorage`,
`sessionStorage`, atau log UI, dan hilang saat halaman dimuat ulang. Jangan
menambahkan key ke variable `VITE_*` karena nilai tersebut akan masuk bundle.

Target proxy lokal untuk production preview/Electron dapat diubah melalui
`JAYA_UI_API_TARGET` (default `http://127.0.0.1:8000`); variable ini hanya berisi
alamat, bukan credential. Jalankan `npm run electron:dev` untuk Vite development
atau `npm run electron:preview` untuk build + preview produksi. Electron menolak
URL non-loopback dan tidak memuat bundle lewat origin `file:`.

`JAYA_ENV=test` bersama `JAYA_HTTP_SECURITY_TEST_MODE=1` adalah bypass khusus
proses tes. Keduanya hanya boleh diaktifkan bersamaan saat menjalankan suite
lokal di bawah dan **tidak pernah** boleh disetel pada development API yang
terhubung pengguna, staging, atau production.

## Pengujian

Test runner utama membuat proses pytest terpisah untuk setiap komponen sehingga
package legacy bernama `src` tidak saling mencemari. Secara default marker
`network`, `hardware`, `manual`, dan `integration` tidak dijalankan.

```powershell
python scripts\run_test_matrix.py --quiet
```

Batasi komponen ketika mengembangkan satu area:

```powershell
python scripts\run_test_matrix.py --component research --quiet
python scripts\run_test_matrix.py --component core --quiet
python scripts\run_test_matrix.py --component agent --component os --quiet
```

Gunakan `--include-external` hanya jika network, provider, hardware, dan
persetujuan manual memang tersedia. Catat environment dan jangan menyamakan
hasil offline dengan validasi eksternal.

### Acceptance suite Phase A

Command ini membuktikan kontrak software Phase A secara offline. Fake provider
di dalam tes hanya menguji fail-closed behavior dan bukan penilai kualitas
ilmiah.

```powershell
$env:PYTHONPATH='JAYA_RESEARCH/src;JAYA_RESEARCH;.'
$env:JAYA_ENV='test'
$env:JAYA_HTTP_SECURITY_TEST_MODE='1'
python -m pytest JAYA_RESEARCH/tests/test_academic_quality_contracts.py JAYA_RESEARCH/tests/test_hypothesis_generator.py JAYA_RESEARCH/tests/test_experiment_designer.py JAYA_RESEARCH/tests/test_experiment_runner.py JAYA_RESEARCH/tests/test_scientific_writer.py JAYA_RESEARCH/tests/test_academic_synthesis_truth.py JAYA_RESEARCH/tests/test_multimodal_pdf.py JAYA_RESEARCH/tests/test_retrieval_evidence_and_eval.py JAYA_RESEARCH/tests/test_grounded_rag_integration.py JAYA_RESEARCH/tests/test_phase_a_rag_contract.py JAYA_RESEARCH/tests/test_research_agent_truth.py JAYA_RESEARCH/tests/test_research_api_phase_a.py JAYA_RESEARCH/tests/test_e2e_api_ui.py -q -p no:cacheprovider --basetemp=JAYA_RESEARCH/.pytest_tmp_phase_a_acceptance
```

Ambang serta gate eksternalnya berada di
[ACCEPTANCE_CRITERIA.md](ACCEPTANCE_CRITERIA.md).

Setelah run selesai, hapus kedua variable bypass dari sesi shell sebelum
menjalankan API non-test:

```powershell
Remove-Item Env:JAYA_ENV -ErrorAction SilentlyContinue
Remove-Item Env:JAYA_HTTP_SECURITY_TEST_MODE -ErrorAction SilentlyContinue
```

### Evaluasi RAG contract smoke

```powershell
$env:PYTHONPATH='JAYA_RESEARCH/src;JAYA_RESEARCH;.'
python -m research.evaluation_cli --dataset JAYA_RESEARCH/evaluation/rag_smoke_v2.json --target 0.85
```

Run yang benar pada fixture aktif harus melaporkan
`status=LOCAL_SMOKE_PASSED`, `representation_status=SMOKE_ONLY`, dan
`production_gate_passed=false`. Metrik tinggi pada fixture sintetis ini hanya
menguji harness, citation contract, dan abstention; bukan kualitas RAG produksi.

UI:

```powershell
Set-Location JAYA_RESEARCH\ui
npm run test:contracts
npm run lint
npm run build
npm audit
Set-Location ..\..
```

Snapshot lokal 1 Agustus 2026: contract test `12 passed`, lint dan production
build lulus, serta audit melaporkan 0 vulnerability. Deep Research UI memakai
service `/research/recursive`, menampilkan status answered/abstain/conflict,
citation/provenance, URI/SHA artefak, dan batas non-promotable. Hasil ini belum
membuktikan browser E2E, deployment, atau provider live.

Android:

```powershell
Set-Location JAYA_ANDROID
.\gradlew.bat testDebugUnitTest lintDebug
Set-Location ..
python scripts\audit_android_security.py
```

Command Android membutuhkan SDK/JDK yang benar. Build yang tidak dijalankan pada
perangkat nyata tidak membuktikan JNI/model runtime end-to-end.

## Validasi dokumentasi

```powershell
python scripts\validate_docs.py
```

Validator memeriksa:

- seluruh dokumen kanonis tersedia;
- tidak ada folder `docs` aktif di dalam modul;
- tidak ada nested `.git` di `JAYA_RESEARCH`;
- tautan file lokal pada dokumentasi aktif dan README tidak rusak.

Audit layout repository:

```powershell
python .github\tools\repo_layout_audit.py --fail-on-violations
```

Audit gagal hanya untuk pelanggaran level error. Warning syntax pada file legacy
tetap harus dicatat, tetapi tidak boleh mendorong perubahan di luar scope.

## Alur perubahan

1. **Analyze:** baca struktur, status Git, dokumen pemilik, code, dan tests.
2. **Plan:** tetapkan scope, acceptance criteria, risiko, dan boundary modul.
3. **Review sebelum edit:** pastikan tidak menimpa perubahan pengguna atau
   melewati security/promotion gate.
4. **Execute:** implementasikan modular, tambahkan error handling dan tests.
5. **Verify:** jalankan linter/test/benchmark yang relevan.
6. **Document:** perbarui status, roadmap, changelog, dan migration/runbook.

## Checklist pull request

- [ ] Perubahan hanya menyentuh scope yang disetujui.
- [ ] Tidak ada secret, data pengguna, model besar, database, atau log.
- [ ] Error handling memberi pesan yang dapat ditindaklanjuti.
- [ ] API/schema yang berubah memiliki versi atau migration.
- [ ] Unit, integration, dan failure tests yang relevan tersedia.
- [ ] Benchmark aktual dilampirkan jika ada klaim performa.
- [ ] Output simulasi tidak diklaim sebagai hasil empiris.
- [ ] Perubahan lintas modul memakai kontrak publik, bukan direct-write/import.
- [ ] `STATUS.md`, `ROADMAP.md`, dan `CHANGELOG.md` telah diselaraskan.
- [ ] `python scripts/validate_docs.py` lulus.

## Aturan implementasi

- Gunakan type hints dan API yang jelas pada Python baru.
- Hindari state global untuk job/sesi persisten.
- Tidak ada `try/except` kosong; log context dan kembalikan error yang aman.
- Operasi retry harus idempotent.
- Modul besar dipecah berdasarkan domain/service/repository.
- Feature flag berbahaya default-nya nonaktif.
- Test tidak boleh menulis source production atau bergantung pada network nyata
  tanpa marker/fixture khusus.

## Troubleshooting singkat

| Gejala | Pemeriksaan |
|---|---|
| Import Python gagal | Jalankan dari root dan periksa environment aktif |
| Sesi tesis tidak pulih setelah restart | Periksa `JAYA_THESIS_SESSION_DB`, izin tulis database beserta file WAL, dan log `recover_interrupted`; repository SQLite sudah terintegrasi sehingga kehilangan sesi adalah kegagalan yang harus didiagnosis |
| Tes gabungan gagal saat collection | Jalankan `scripts/run_test_matrix.py` agar namespace komponen terisolasi, lalu perbaiki import pada komponen yang gagal |
| Provider inference gagal | Periksa credential, quota, timeout, dan koneksi tanpa mencetak secret |
| UI tidak terhubung API | Periksa base URL, port, status API, allowlist CORS, lalu baca `status` dan `code` pada `ApiError` tanpa mencetak key |
| Gate UI menolak credential | Pastikan `JAYA_RESEARCH_API_KEYS` valid pada proses API dan key dimasukkan melalui field runtime; jangan pindahkan key ke `VITE_*` atau storage browser |
| Riset autonomous terduplikasi | Pastikan request autonomous membawa `Idempotency-Key` stabil untuk satu intent dan key baru untuk intent baru |
| Hasil discovery berubah setiap run | Pastikan seed/config atau tandai hasil sebagai simulasi |
