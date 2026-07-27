# Arsip Dokumentasi JAYA

Folder ini menyimpan dokumen historis. Isinya **bukan sumber kebenaran aktif**
dan tidak perlu dibaca untuk implementasi baru kecuali pengguna meminta audit
riwayat atau penelusuran keputusan lama.

Dokumen aktif selalu dimulai dari [pusat dokumentasi](../README.md).

## Struktur

- `legacy-module-docs/`: dokumentasi lama dari JAYA Core, Research, Agent, OS,
  dan Android. Arsip Research juga menyimpan backup metadata nested Git lama
  dengan nama non-`.git` agar tidak aktif sebagai repository.
- `legacy-root-docs/`: PRD, SRS, masterplan, roadmap, serta catatan root lama.
- `DB_DESIGN.md`, `PROCESS_MODEL.md`, `WORKFLOW_SRS_PRD.md`: rancangan historis.
- `repo_layout_audit_latest.json`: snapshot audit layout lama.
- PDF peraturan akademik: bahan referensi historis.

## Aturan

- Jangan memperbarui arsip untuk mendeskripsikan kondisi aktual.
- Jika informasi arsip masih relevan, tulis ulang secara ringkas pada dokumen
  kanonis dan cantumkan bukti terbaru.
- Jangan menghapus arsip tanpa persetujuan karena mungkin diperlukan untuk audit.
- Isi arsip besar diabaikan Git; README ini tetap dilacak sebagai indeks.
- Backup metadata Git lama dapat dihapus permanen secara manual bila riwayat
  remote dan root repository sudah dipastikan cukup.
