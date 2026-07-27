# JAYA Sovereign AI Ecosystem

JAYA adalah monorepo untuk membangun asisten AI berdaulat yang memisahkan riset,
penalaran inti, orkestrasi agen, runtime sistem, dan klien Android. Fokus aktif
saat ini adalah menjadikan **JAYA Research** fondasi pengetahuan berbasis bukti
sebelum hasilnya dapat dipromosikan secara aman ke komponen lain.

> Status proyek: prototipe aktif. Istilah *implemented* tidak otomatis berarti
> siap produksi. Lihat [status terverifikasi](docs/STATUS.md) untuk kondisi aktual.

## Dokumentasi

Semua dokumentasi aktif berada di satu tempat:

- [Pusat dokumentasi](docs/README.md)
- [Visi dan ruang lingkup produk](docs/PRODUCT.md)
- [Arsitektur ekosistem](docs/ARCHITECTURE.md)
- [Keputusan arsitektur aktif](docs/DECISIONS.md)
- [Alur sistem](docs/WORKFLOWS.md)
- [Status implementasi](docs/STATUS.md)
- [Roadmap kanonis](docs/ROADMAP.md)
- [Checklist pemulihan](docs/REMEDIATION_CHECKLIST.md)
- [Tata kelola dan gerbang promosi](docs/GOVERNANCE.md)
- [Panduan pengembangan](docs/DEVELOPMENT.md)

Dokumentasi di `docs/archive/` hanya menyimpan riwayat dan tidak boleh dipakai
sebagai spesifikasi aktif.

## Modul

| Modul | Tanggung jawab | Kematangan saat ini |
|---|---|---|
| `JAYA_RESEARCH` | RAG, analisis tesis, pencarian literatur, graph, dan discovery | Prototipe terintegrasi |
| `JAYA_CORE` | Penalaran, perencanaan, memori, dan eksekusi JayaIR | Implemented, verifikasi menyeluruh belum selesai |
| `JAYA_AGENT` | Orkestrasi tugas dan penggunaan alat | Prototipe |
| `JAYA_OS` | Runtime, kebijakan, perangkat, dan sandbox | Prototipe awal |
| `JAYA_ANDROID` | Klien perangkat bergerak | Prototipe |

## Mulai cepat JAYA Research

Prasyarat utama: Python 3.10+, Node.js 18+, dan kredensial provider model yang
disimpan di `.env`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r JAYA_RESEARCH\requirements.txt
python JAYA_RESEARCH\src\network\research_api.py
```

Di terminal lain:

```powershell
Set-Location JAYA_RESEARCH\ui
npm install
npm run dev
```

API tersedia secara default di `http://localhost:8000` dan UI Vite di
`http://localhost:5173`. Detail pengujian dan konfigurasi ada di
[panduan pengembangan](docs/DEVELOPMENT.md).

## Aturan repositori

- Hanya ada satu Git repository, yaitu `.git` di root monorepo.
- Dokumentasi aktif hanya berada di `docs/`.
- Data pengguna, secret, model, database, log, dan artefak runtime tidak di-commit.
- Perubahan status fitur wajib memperbarui `docs/STATUS.md`, `docs/ROADMAP.md`,
  dan `docs/CHANGELOG.md` dalam perubahan yang sama.
