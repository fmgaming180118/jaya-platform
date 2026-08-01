# JAYA

> **JAYA Research mencari dan memverifikasi pengetahuan atau kemampuan baru untuk menghasilkan
> kandidat peningkatan bagi JAYA Core. Analisis tesis hanyalah salah satu domain adapter,
> bukan tujuan utama sistem.**

JAYA adalah monorepo untuk membangun asisten AI berdaulat yang menghubungkan
riset berbukti, otak AI, orkestrasi agen, runtime kebijakan, dan antarmuka
Android.

Kemampuan setara JARVIS, operasi offline penuh, dan footprint di bawah 200 MB
adalah **visi dan target produk**. Ketiganya belum menjadi kondisi yang telah
dibuktikan. Kondisi implementasi yang terverifikasi, risiko, dan gate eksternal
selalu mengikuti [STATUS](docs/STATUS.md), bukan teks promosi di README.

## Kondisi saat ini

- Phase A telah lulus kontrak software lokal (`PASS_LOCAL`).
- Dataset RAG aktif masih berupa fixture `SMOKE_ONLY`; hasilnya tidak mengukur
  kualitas retrieval produksi.
- Evaluasi representatif, eksperimen empiris nyata, perangkat fisik, model final,
  dan persetujuan manusia masih memiliki gate `BLOCKED_EXTERNAL`.
- Sistem belum boleh disebut JARVIS-complete, production-ready, sepenuhnya
  offline, atau memenuhi batas 200 MB.

Kontrak dan bukti Phase A dijelaskan di
[ACCEPTANCE_CRITERIA](docs/ACCEPTANCE_CRITERIA.md).

## Komponen

| Modul | Tanggung jawab |
|---|---|
| [JAYA_RESEARCH](JAYA_RESEARCH/) | **Laboratorium Evolusi Kognitif (CEL)**: memperoleh sumber, membangun evidence, mendeteksi gap, menguji hipotesis, dan menghasilkan candidate cognitive artifact untuk JAYA Core. Analisis tesis adalah salah satu domain adapter. |
| [JAYA_CORE](JAYA_CORE/) | Otak, model runtime, protokol aksi, serta gate instalasi dan rollback. |
| [JAYA_AGENT](JAYA_AGENT/) | Orkestrasi intent dan pemanggilan capability yang diizinkan. |
| [JAYA_OS](JAYA_OS/) | Sandbox, policy enforcement, dan adapter tindakan sistem. |
| [JAYA_ANDROID](JAYA_ANDROID/) | Antarmuka Android dan runtime lokal yang tersedia. |

JAYA Research tidak mengubah Core secara langsung. Hasil Research tetap berupa
candidate sampai provenance, reproduksi, benchmark, security review,
persetujuan manusia, canary, dan rollback gate lulus.

## Dokumentasi kanonis

- [Pusat dokumentasi](docs/README.md)
- [Visi produk](docs/PRODUCT.md)
- [Arsitektur dan batas modul](docs/ARCHITECTURE.md)
- [Alur operasional](docs/WORKFLOWS.md)
- [Status terverifikasi](docs/STATUS.md)
- [Roadmap](docs/ROADMAP.md)
- [Acceptance criteria Phase A](docs/ACCEPTANCE_CRITERIA.md)
- [Panduan pengembangan](docs/DEVELOPMENT.md)
- [Governance](docs/GOVERNANCE.md)

## Mulai mengembangkan

Prasyarat root tooling adalah Python 3.11 atau lebih baru. Dependency dan
provider berbeda untuk setiap komponen; ikuti
[panduan pengembangan](docs/DEVELOPMENT.md) sebelum menjalankan service.

Quality gate Python offline yang terisolasi per komponen:

```powershell
python scripts/run_test_matrix.py --quiet
```

Validasi dokumentasi dan layout:

```powershell
python scripts/validate_docs.py
python .github/tools/repo_layout_audit.py --fail-on-violations
```

Tes lokal tidak membuktikan provider live, model final, hardware, kualitas
dataset representatif, maupun kelayakan ilmiah.

## Keamanan dan lisensi

Jangan commit credential, `.env`, database runtime, PDF pengguna, model, log,
atau dataset yang belum memiliki izin.

- [Kebijakan keamanan](docs/SECURITY.md)
- [MIT License](docs/LICENSE)
- [Panduan kontribusi](CONTRIBUTING.md)
