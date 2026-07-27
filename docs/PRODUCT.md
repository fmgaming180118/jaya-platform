# Produk dan Visi JAYA

## Ringkasan

JAYA adalah ekosistem asisten AI berdaulat, *offline-first* bila memungkinkan,
yang dapat meneliti, bernalar, menggunakan alat, dan berjalan di beberapa
perangkat tanpa kehilangan kontrol manusia. JAYA Research adalah jalur masuk
pengetahuan: ia mengubah sumber mentah menjadi jawaban bercitation, analisis,
hipotesis, dan paket bukti yang dapat ditinjau.

## Masalah yang diselesaikan

Mahasiswa dan peneliti harus berpindah antara pencarian literatur, pembacaan PDF,
catatan, analisis kebaruan, revisi, dan persiapan sidang. Hasil dari alat-alat
tersebut sering sulit ditelusuri ke sumber awal. Di sisi lain, sistem AI yang
belajar otomatis berisiko memasukkan klaim salah ke komponen inti.

JAYA menargetkan dua hasil:

1. Mempercepat pekerjaan riset sambil mempertahankan sumber, konteks, dan jejak
   bukti.
2. Mengembangkan kemampuan ekosistem hanya melalui gerbang verifikasi yang
   dapat diaudit dan dibatalkan.

## Pengguna utama

- Mahasiswa yang menganalisis dan merevisi tugas akhir.
- Peneliti yang mencari literatur, gap, dan hipotesis.
- Maintainer yang mengevaluasi peningkatan kemampuan JAYA.
- Pengguna perangkat pribadi yang membutuhkan asisten privat dan terkendali.

## Kapabilitas produk

### JAYA Research

- Ingest PDF, halaman web, video/transkrip, dan sumber akademik.
- RAG dengan kutipan dan provenance.
- Analisis metadata tesis, novelty, gap, kritik, revisi, dan simulasi pertahanan.
- Pencarian serta sintesis literatur secara bertahap.
- Knowledge graph dan memori riset.
- Perumusan hipotesis, desain eksperimen, analisis hasil, dan scientific writer.
- Penyusunan paket bukti untuk ditinjau; bukan promosi otomatis ke Core.

### Ekosistem penerima

- **JAYA Core:** penalaran, perencanaan, memori kognitif, dan JayaIR.
- **JAYA Agent:** orkestrasi pekerjaan dan alat dengan izin yang jelas.
- **JAYA OS:** runtime, perangkat, resource, sandbox, dan kebijakan eksekusi.
- **JAYA Android:** antarmuka mobile dan sinkronisasi terkontrol.

## Ruang lingkup saat ini

Prioritas adalah memperkuat JAYA Research: kualitas RAG, ketahanan API,
persistensi pekerjaan, eksperimen yang dapat direproduksi, dan kontrak artefak
antar-modul. Integrasi klien dan runtime mengikuti setelah API serta gerbang
bukti stabil.

## Di luar ruang lingkup saat ini

- Mengklaim penemuan ilmiah tanpa data eksternal dan reproduksi independen.
- Mengubah source code Core langsung dari proses riset produksi.
- Menjalankan loop otonom tanpa batas, *kill switch*, audit, dan persetujuan.
- Menjadikan JAYA Core ensiklopedia; pengetahuan domain tetap berada di lapisan
  retrieval/memory.
- Menjamin semua data sepenuhnya lokal ketika provider inference cloud aktif.

## Prinsip produk

1. **Evidence before promotion:** temuan tidak menjadi kemampuan inti sebelum
   bukti nyata lulus gerbang.
2. **Human authority:** manusia menentukan aktivasi, promosi, dan rollback.
3. **Traceability:** jawaban dan keputusan harus dapat ditelusuri.
4. **Privacy by design:** data minimum dikirim keluar dan secret tidak masuk Git.
5. **Offline degradation:** fungsi lokal tetap berguna ketika provider eksternal
   tidak tersedia.
6. **Honest maturity:** prototipe, simulasi, implemented, dan production adalah
   status berbeda.

## Ukuran keberhasilan

- QA RAG mencapai minimal 85% pada dataset evaluasi yang versioned.
- Tugas panjang bertahan terhadap restart dan dapat dilanjutkan dari state.
- Setiap klaim riset penting memiliki citation/provenance.
- Eksperimen dapat diulang dengan data, konfigurasi, seed, dan hasil tersimpan.
- Tidak ada promosi lintas modul tanpa tes nyata, benchmark, review keamanan,
  persetujuan manusia, serta rencana rollback.
- Pengguna dapat mengetahui status dan kesalahan dari satu dashboard/status.

