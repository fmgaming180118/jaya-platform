# Thesis Analyzer — Panduan Lengkap

Fitur utama JAYA Research untuk mahasiswa: upload PDF skripsi/TA dan dapatkan analisis akademis menyeluruh.

---

## Alur Penggunaan

```
Upload PDF  →  Analisis (5 step)  →  Revisi  →  Cari Jurnal  →  Export Laporan
```

---

## Tab 1: Analisis

### Cara Pakai
1. Buka halaman **Thesis** di UI (`http://localhost:5173/thesis`)
2. Drag & drop file PDF atau klik zona upload
3. Klik **"Mulai Analisis Komprehensif"**
4. Tunggu 2–10 menit (tergantung panjang dokumen dan kecepatan internet)

### 5 Step Analisis

| Step | Modul | Output |
|---|---|---|
| **1. Metadata** | LLM (NIM) | Judul, penulis, topik, abstrak, keywords |
| **2. Novelty** | `NoveltyChecker` | Novel/Kurang Novel + confidence % + reasoning |
| **3. Research Gap** | `GapFinder` | Gap analysis Markdown — celah yang belum diteliti |
| **4. Critique** | `ReviewerAgent` | Kritik akademis gaya peer review |
| **5. Defense** | LLM (NIM) | Daftar pertanyaan sidang yang mungkin muncul |

### Contoh Output Novelty
```
Status: ✅ NOVEL (Confidence: 78%)

Reasoning: Penelitian ini mengkombinasikan federated learning dengan
differential privacy untuk data kesehatan, kombinasi yang belum banyak
dieksplorasi dalam literatur. Dari 12 paper terkait yang ditemukan,
tidak ada yang membahas aspek [...]
```

---

## Tab 2: Revisi

Paste bagian teks TA yang ingin diperbaiki, pilih tipe revisi, dan JAYA akan menulis ulang.

### Tipe Revisi

| Tipe | Kapan Digunakan |
|---|---|
| **Umum** | Keseluruhan — perbaiki alur, kejelasan, dan kualitas akademis |
| **Formalitas** | Teks terlalu kasual — ubah ke bahasa ilmiah formal |
| **Sitasi** | Klaim tanpa referensi — tambahkan `[Citation Needed]` |
| **Metodologi** | Bab metode lemah — perkuat step penelitian |

### Tips
- Paste satu paragraf atau satu sub-bab sekaligus, bukan seluruh bab
- Gunakan instruksi yang spesifik: *"Perbaiki kalimat kedua di paragraf ketiga"* lebih baik dari *"Perbaiki semua"*
- Hasil revisi bisa di-copy langsung dengan tombol **Salin**

---

## Tab 3: Jurnal

Cari paper akademis yang relevan berdasarkan topik dan keywords TA kamu.

### Cara Kerja
1. Klik **"Cari Jurnal Relevan"**
2. JAYA otomatis menggunakan topik dari analisis (step 1) sebagai query
3. Cari di ArXiv + Semantic Scholar secara paralel
4. Hasil muncul dengan judul, tahun, sumber, dan abstrak

### Filter
Gunakan kotak filter untuk menyaring berdasarkan judul atau abstrak.

> [!TIP]
> Jurnal yang ditemukan di sini bisa dijadikan referensi tambahan untuk TA kamu. Klik ikon link eksternal untuk buka paper asli.

---

## Tab 4: Chat

Tanya apa saja tentang isi dokumen TA kamu — JAYA menjawab berdasarkan teks yang sudah diupload.

**Contoh pertanyaan yang berguna:**
- *"Apa kontribusi utama penelitian ini?"*
- *"Sebutkan keterbatasan metodologi yang disebutkan di bab 3"*
- *"Bagaimana cara memperkuat bab pembahasan?"*
- *"Referensi apa yang paling sering dikutip?"*

---

## Tab 5: Ekspor

Download laporan analisis lengkap dalam format Markdown (`.md`).

**Isi laporan:**
- Metadata dokumen (tabel)
- Status novelty + reasoning
- Research gap analysis
- Kritik peer review
- Pertanyaan sidang
- Daftar jurnal relevan
- Riwayat revisi yang dilakukan

**Cara buka laporan:**
- **Obsidian** — tampilan paling rapi dengan navigasi antar bagian
- **VS Code** — dengan ekstensi Markdown Preview
- **Pandoc** — konversi ke PDF: `pandoc laporan.md -o laporan.pdf`

---

## API Langsung (tanpa UI)

```bash
# 1. Upload PDF
curl -X POST "http://localhost:8000/thesis/upload" \
  -F "file=@/path/to/thesis.pdf" \
  -F "workspace_id=default"
# → {"session_id": "abc123", "file_name": "thesis.pdf", "char_count": 45000}

# 2. Mulai analisis
curl -X POST "http://localhost:8000/thesis/analyze/abc123"

# 3. Poll status
curl "http://localhost:8000/thesis/status/abc123"

# 4. Download laporan
curl "http://localhost:8000/thesis/export/abc123" -o laporan.md
```

---

**Lihat juga:** [API Reference](../02-architecture/api-reference.md) | [Research Agent](research-agent.md)
