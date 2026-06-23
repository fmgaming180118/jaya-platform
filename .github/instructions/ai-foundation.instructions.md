# Instruksi Dasar: Pondasi Pembangunan AI JAYA

## Tujuan
- Menyediakan seperangkat aturan, batasan, dan konvensi minimal yang menjadi pondasi untuk mengembangkan sistem AI di repositori ini.
- Instruksi ini bersifat dasar dan dapat diperluas menjadi instruksi domain-spesifik (`JAYA_CORE`, `JAYA_RESEARCH`) jika diperlukan.

## Ruang Lingkup (applyTo)
- applyTo: `**` (default: semua file) — gunakan kata ini untuk aturan umum.
- Untuk aturan yang spesifik domain, buat file terpisah: `JAYA_CORE/**` atau `JAYA_RESEARCH/**`.

## Prinsip Utama
- **Isolasi domain:** Jangan membuat ketergantungan kode langsung antara `JAYA_CORE` dan `JAYA_RESEARCH`.
- **Keamanan & Privasi:** Data sensitif harus diidentifikasi, dibatasi aksesnya, dan tidak dikomit ke repo. Gunakan secret manager untuk kredensial.
- **Determinisme eksperimen:** Eksperimen harus dapat direproduksi — simpan seed, versi dataset, dan parameter eksperimen.
- **Minimal dependency:** Pilih dependensi hanya bila ada manfaat jelas; prefer library ringan dan stabil.
- **Tidak ada loop otonom tanpa izin:** Skrip yang berjalan terus-menerus (`--forever`, worker daemons) memerlukan persetujuan eksplisit dan gated tests.

## Arsitektur & Boundary Rules
- `JAYA_CORE` adalah runtime inti (sovereign). Hindari impor balik dari `JAYA_RESEARCH` ke `JAYA_CORE`.
- Mantapkan kontrak JayaIR sebagai schema yang relatif "frozen" untuk Phase 1 — perubahan schema harus disertai dengan dokumen handoff dan tes gate.
- Letakkan utilitas riset, eksperimen, dan sandbox di `JAYA_RESEARCH/`; kode produksi runtime berada di `JAYA_CORE/`.

## Penempatan Spesifik (repo-wide)
- Untuk setiap permintaan pembuatan "otak" (brain) produksi atau runtime utama, implementasi dan artefak final harus ditempatkan di `JAYA_CORE`.
- Untuk kebutuhan riset, eksperimen, iterasi rekursif, atau komponen pendukung pengembangan otak (mis. eksperimen recursive, dataset eksperimental, prototipe iteratif), tempatkan di `JAYA_RESEARCH`.
- Pastikan antarmuka publik antara `JAYA_RESEARCH` -> `JAYA_CORE` bersifat eksplisit dan satu-arah: riset dapat menghasilkan artefak, tetapi impor langsung dari riset ke core harus di-review dan di-gate.

## Pengembangan, Build & Test
- Baseline Python: gunakan versi yang ditetapkan di `pyrightconfig.json` (mis. Python 3.12).
- Jalankan tes bertarget saat membuat perubahan: contoh `python -m pytest JAYA_CORE/tests/test_phase1_jaya_ir.py -v`.
- Untuk perubahan pada kinerja, jalankan benchmark gate yang relevan dan simpan snapshot JSON hasil benchmark.

## Konvensi Kode
- Ikuti style lokal yang ada; hindari mengganti gaya file yang tidak terkait.
- Hindari penggunaan variabel satu-huruf; gunakan nama yang deskriptif.
- Untuk tipe yang ambigu dalam test, jelaskan dengan `Dict[str, Any]` atau cast sebelum mengoper ke API ber-typing ketat.

## Eksperimen & Evolusi
- Semua evolusi desain (phase2) harus melewati gate: manifest verification, rollback test, dan evaluasi signed candidate.
- Skrip evolusi otomatis harus memiliki "kill-switch" yang dapat dipicu oleh operator.

## Keamanan Operasional
- Jangan menaruh API keys atau credential lain di repo; masukkan instruksi menggunakan `secret manager` atau environment variables.
- Untuk scanning secrets, gunakan tool yang ditentukan dalam workflow CI dan beri pengecualian hanya dengan audit.

## Governance & Review
- Perubahan desain inti memerlukan review dari pemilik domain (`JAYA_CORE` maintainers untuk core; `JAYA_RESEARCH` leads untuk riset).
- Sertakan deskripsi perubahan, dampak backward-compatibility, dan langkah roll-back di PR.

## Contoh Prompt Instruksi (untuk agent dan developer)
- "Selalu gunakan dependency versi X.Y.Z untuk library `foo` kecuali ada alasan tertulis."
- "Jangan jalankan loop `--forever` tanpa menambahkan parameter `--dry-run` dan flag persetujuan operator." 

## Template Penggunaan
- Jika menambahkan aturan baru yang spesifik: buat file `.github/instructions/<nama>.instructions.md` dan set `applyTo` yang tepat.

## Iterasi & Klarifikasi
- Instruksi ini adalah pondasi; identifikasi area yang ambigu dan tambahkan blok "Questions" di PR untuk mendiskusikan.

## Catatan Akhir
- Simpan aturan yang ketat untuk boundary dan safety; prefer explicitness daripada implicit behavior.
- Jika ingin, saya bisa membuat varian khusus untuk `JAYA_CORE` dan `JAYA_RESEARCH` berikut contoh PR template.
