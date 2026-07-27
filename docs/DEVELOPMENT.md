# Panduan Pengembangan

## Prasyarat

- Windows PowerShell atau shell setara.
- Python 3.10+.
- Node.js 18+ dan npm untuk UI Research.
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
npm install
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

## Pengujian

Jalankan tes terarah saat mengubah area terkait:

```powershell
python -m pytest JAYA_RESEARCH\tests\test_research_api_phase_a.py -q
python -m pytest JAYA_RESEARCH\tests\test_hypothesis_generator.py JAYA_RESEARCH\tests\test_experiment_designer.py JAYA_RESEARCH\tests\test_experiment_runner.py JAYA_RESEARCH\tests\test_scientific_writer.py -q
python -m pytest JAYA_CORE\tests\test_phase1_jaya_ir.py -q
```

Karena pernah ada konflik nama/import saat koleksi gabungan, selalu laporkan
apakah tes dijalankan terisolasi atau sebagai seluruh suite. Target roadmap
adalah membuat semua suite dapat dikoleksi bersama di CI.

UI:

```powershell
Set-Location JAYA_RESEARCH\ui
npm run lint
npm run build
```

Android:

```powershell
Set-Location JAYA_ANDROID
.\gradlew.bat test
.\gradlew.bat assembleDebug
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
| API kehilangan sesi setelah restart | Ini gap yang tercatat; persistence belum terintegrasi penuh |
| Tes gabungan gagal saat collection | Cari nama modul tes yang sama dan import top-level |
| Provider inference gagal | Periksa credential, quota, timeout, dan koneksi tanpa mencetak secret |
| UI tidak terhubung API | Periksa base URL, port, CORS, dan status API |
| Hasil discovery berubah setiap run | Pastikan seed/config atau tandai hasil sebagai simulasi |
