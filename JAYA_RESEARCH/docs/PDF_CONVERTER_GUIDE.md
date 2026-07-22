# PDF to Markdown Converter - Dokumentasi

## 📄 Tentang PDF yang Dikonversi

**Nama File:** `Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf`

**Lokasi:** `docs/` (di root workspace)

**Output Directory:** `JAYA_RESEARCH/data/pdf_conversions/Peraturan_Direktur_02_2021/`

---

## 🚀 Cara Menjalankan Konversi

### Opsi 1: Double-click Batch File (Paling Mudah)

Di folder `JAYA_RESEARCH/`, double-click:
```
convert_pdf_to_markdown.bat
```

Sistem akan:
1. ✅ Mengecek Python installation
2. ✅ Install/update dependencies
3. ✅ Menjalankan konversi
4. ✅ Menampilkan hasil

### Opsi 2: Command Line Manual

```powershell
cd JAYA_RESEARCH
python scripts/pdf_to_markdown_converter.py `
    "..\docs\Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf" `
    -o "data\pdf_conversions\Peraturan_Direktur_02_2021" `
    -v
```

### Opsi 3: Batch Processing (Multiple PDFs)

```powershell
python scripts/pdf_to_markdown_converter.py "..\docs\*.pdf" -v
```

---

## 📁 Struktur Output

Setelah konversi, struktur folder akan seperti:

```
JAYA_RESEARCH/
└── data/
    └── pdf_conversions/
        └── Peraturan_Direktur_02_2021/
            ├── Peraturan_Direktur_02_2021.md   (✅ Main Markdown)
            ├── conversion_report.json           (📋 Metadata & Statistics)
            ├── images/                          (📁 All extracted images)
            │   ├── page_001_image_00.png
            │   ├── page_002_image_00.png
            │   ├── page_003_pymupdf_00.png
            │   └── ...
            └── tables/                          (📁 All extracted tables)
                ├── page_001_table_00.md
                ├── page_002_table_00.md
                ├── page_003_table_01.md
                └── ...
```

---

## 📊 Format Output

### 1. Main Markdown File

Berisi:
- **Header dengan metadata** (judul, tanggal konversi, jumlah halaman, dll)
- **Table of Contents** (Daftar isi gambar dan tabel)
- **Konten per halaman** dengan struktur jelas
- **Embedded gambar** dengan reference relatif
- **Embedded tabel** dalam format Markdown dengan reference file terpisah

### 2. Images (`images/` folder)

Semua gambar dari PDF di-ekstrak sebagai PNG dengan penamaan:
- `page_001_image_00.png` - Gambar pertama dari halaman 1
- `page_002_image_01.png` - Gambar kedua dari halaman 2
- `page_003_pymupdf_00.png` - Ekstraksi alternatif dari PyMuPDF

### 3. Tables (`tables/` folder)

Setiap tabel di-ekstrak ke file Markdown terpisah dengan format GitHub:
- `page_001_table_00.md` - Tabel pertama dari halaman 1
- `page_005_table_02.md` - Tabel ketiga dari halaman 5

Format tabel di-standardisasi dengan GitHub markdown style.

### 4. Conversion Report (`conversion_report.json`)

JSON dengan statistik lengkap konversi, termasuk metadata PDF dan inventory semua gambar/tabel.

---

## 🛠️ Requirements & Dependencies

Semua dependencies sudah ditambahkan ke `JAYA_RESEARCH/requirements.txt`:

```
pdfplumber>=0.11.0     # PDF parsing & text extraction
pymupdf>=1.24.0        # Alternative PDF processing + image extraction
pdf2image>=1.16.0      # PDF to image conversion
Pillow                 # Image processing
tabulate>=0.9.0        # Table formatting
```

---

## ✅ Fitur Utama Script

1. **Ekstraksi Lengkap**: Text, images, dan tables dari PDF
2. **Dual-Method Image Extraction**: Pdfplumber + PyMuPDF untuk coverage maksimal
3. **Smart Table Parsing**: Ekstraksi dengan format GitHub markdown
4. **Metadata Handling**: PDF properties dan conversion metadata
5. **Error Handling**: Graceful fallback untuk ekstraksi gagal
6. **UTF-8 Support**: Nama file Indonesian tanpa issues

---

## 📝 Quick Start

```powershell
# 1. Navigate ke JAYA_RESEARCH
cd JAYA_RESEARCH

# 2. Run batch file
./convert_pdf_to_markdown.bat

# ATAU manual run:
python scripts/pdf_to_markdown_converter.py "..\docs\Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf" -o "data\pdf_conversions\Peraturan_Direktur_02_2021" -v

# 3. Hasil tersedia di:
# JAYA_RESEARCH/data/pdf_conversions/Peraturan_Direktur_02_2021/
```

---

## 📋 Workflow

1. **Konversi Awal**: Run batch file atau script
2. **Review Output**: Check gambar, tabel, dan text di output folder
3. **Post-Processing**: Optional cleanup/edit jika diperlukan
4. **Integration**: Gunakan hasil untuk dokumentasi atau processing lebih lanjut

---

## 🐛 Troubleshooting

| Problem | Solution |
|---------|----------|
| Missing dependency | `pip install pdfplumber pymupdf pdf2image pillow tabulate` |
| PDF not found | Verify path benar dan file exists di docs/ |
| Images tidak ter-ekstrak | Check conversion_report.json, beberapa PDF punya embedded images kompleks |
| Tables tidak ter-format baik | Edit manual file di tables/ folder |
| Performance lambat | Normal untuk PDF besar (100+ pages), tunggu proses selesai |

---

**Created for:** JAYA_RESEARCH PDF Processing Pipeline  
**Script Location:** `JAYA_RESEARCH/scripts/pdf_to_markdown_converter.py`  
**Batch File:** `JAYA_RESEARCH/convert_pdf_to_markdown.bat`
