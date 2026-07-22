# Quick Start — 5 Menit Pertama

Panduan ini mengasumsikan kamu sudah selesai [instalasi](installation.md).

---

## Langkah 1: Jalankan Backend

```bash
# Dari direktori JAYA_RESEARCH/
python src/network/research_api.py
```

Backend berjalan di `http://localhost:8000`.

Swagger API docs tersedia di: `http://localhost:8000/docs`

---

## Langkah 2: Jalankan UI Dashboard

Buka terminal baru:

```bash
cd ui
npm run dev
```

UI berjalan di `http://localhost:5173`.

---

## Langkah 3: Buat Workspace Pertama

1. Buka `http://localhost:5173`
2. Klik **"New Workspace"**
3. Beri nama (misal: `tugas-akhir-saya`)
4. Klik **Create**

---

## Langkah 4: Pilih Fitur yang Ingin Digunakan

### A. Bedah Tugas Akhir (Recommended untuk mahasiswa)
1. Klik menu **Thesis** di sidebar
2. Drag & drop file PDF skripsi kamu
3. Klik **"Mulai Analisis Komprehensif"**
4. Tunggu 2–5 menit → hasil muncul di 5 tab

→ Panduan lengkap: [Thesis Analyzer](../03-features/thesis-analyzer.md)

### B. Autonomous Research
1. Klik menu **Research**
2. Ketik topik (misal: `"Federated Learning for Healthcare"`)
3. Klik **Start**
4. JAYA akan mencari paper, mensintesis temuan, dan menghasilkan laporan

→ Panduan lengkap: [Research Agent](../03-features/research-agent.md)

### C. Chat dengan Knowledge Base
1. Klik menu **Chat**
2. Upload dokumen lewat `/ingest` atau tanya langsung
3. JAYA menjawab berdasarkan dokumen yang ada

---

## Menggunakan `openjay` CLI (Alternatif)

File `openjay.bat` (Windows) menyediakan shortcut:

```bash
# Jalankan backend
openjay run

# Jalankan dashboard UI
openjay dashboard
```

Tambahkan folder `JAYA_RESEARCH/` ke PATH agar bisa dipanggil dari mana saja.

---

## Cek Status Sistem

```bash
# Via terminal
curl http://localhost:8000/

# Seharusnya mengembalikan:
# {"status": "online", "service": "JAYA Research API"}
```

---

**Selanjutnya:** [Konfigurasi Lanjutan →](configuration.md) | [Fitur Thesis Analyzer →](../03-features/thesis-analyzer.md)
