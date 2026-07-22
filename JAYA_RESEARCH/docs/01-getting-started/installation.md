# Instalasi JAYA Research

## Prasyarat

| Komponen | Versi Minimum | Keterangan |
|---|---|---|
| Python | 3.10+ | 3.12 direkomendasikan |
| Node.js | 18+ | Untuk UI React |
| npm | 9+ | Ikut dengan Node.js |
| Git | Terbaru | Untuk clone repo |
| NVIDIA API Key | — | Gratis di [build.nvidia.com](https://build.nvidia.com) |

> [!NOTE]
> JAYA Research menggunakan **NVIDIA NIM** (cloud inference) — tidak butuh GPU lokal. Berjalan di laptop biasa.

---

## 1. Clone Repository

```bash
git clone https://github.com/yourusername/jaya-research.git
cd jaya-research/JAYA_RESEARCH
```

---

## 2. Setup Python Environment

```bash
# Buat virtual environment
python -m venv .venv312

# Aktifkan (Windows)
.venv312\Scripts\activate

# Aktifkan (Linux/Mac)
source .venv312/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Dependency Opsional

```bash
# Untuk ekstraksi PDF (direkomendasikan)
pip install pymupdf

# Fallback PDF jika PyMuPDF tidak tersedia
pip install pdfplumber PyPDF2

# Untuk QLoRA training (opsional, butuh GPU)
pip install -r requirements-qlora.txt

# Untuk Voice Agent (opsional)
pip install pipecat-ai
```

---

## 3. Konfigurasi Environment

```bash
# Copy template
cp .env.example .env

# Edit .env dan isi NVIDIA_API_KEY
```

Isi minimal di `.env`:

```env
NVIDIA_API_KEY=nvapi-xxxxxxxxxxxxxxxxxxxxxxxx
```

Dapatkan key gratis di [build.nvidia.com](https://build.nvidia.com) → Login → API Keys.

Untuk konfigurasi lengkap lihat → [configuration.md](configuration.md)

---

## 4. Setup UI

```bash
cd ui
npm install
cd ..
```

---

## 5. Verifikasi Instalasi

```bash
# Test backend bisa import semua modul
python -c "from src.teacher import Teacher; print('Backend OK')"

# Test API key valid
python -c "
from src.teacher import Teacher
t = Teacher()
print(t.ask('Hello, respond with: OK'))
"
```

Jika output `OK` muncul, instalasi berhasil.

---

## Troubleshooting

### `ModuleNotFoundError: No module named 'src'`
Pastikan kamu menjalankan dari direktori `JAYA_RESEARCH/` (bukan dari dalam `src/`):
```bash
cd JAYA_RESEARCH
python src/network/research_api.py
```

### `NVIDIA API Error: 401 Unauthorized`
API key belum diset atau salah. Periksa file `.env`:
```bash
cat .env | grep NVIDIA_API_KEY
```

### `npm install` gagal
Pastikan Node.js 18+:
```bash
node --version   # harus v18.x.x atau lebih
npm --version
```

### PDF tidak bisa diekstrak
Install PyMuPDF:
```bash
pip install pymupdf
```

---

**Selanjutnya:** [Quick Start →](quick-start.md)
