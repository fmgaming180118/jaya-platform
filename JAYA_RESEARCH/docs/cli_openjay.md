# OpenJay CLI

`openjay` adalah Command Line Interface (CLI) khusus untuk menjalankan service di dalam lingkungan `JAYA_RESEARCH`. 

## Penggunaan

Anda dapat memanggil CLI ini melalui Terminal, Command Prompt, atau PowerShell asalkan berada di direktori root `JAYA_RESEARCH`. Jika menggunakan PowerShell, gunakan `.\openjay`.

### Menjalankan Backend (Research API)
```bash
openjay run
```
Perintah ini akan memicu `python src/network/research_api.py` dan memulai server API di port 8000.

### Menjalankan Frontend (UI Dashboard)
```bash
openjay dashboard
```
Perintah ini akan menjalankan frontend React/Vite yang berada di dalam folder `ui/` menggunakan perintah `npm run dev` pada port 5173.

## Instalasi Tambahan (Opsional)
Jika Anda ingin memanggil `openjay` dari lokasi manapun di komputer Anda, Anda dapat menambahkan path folder `JAYA_RESEARCH` ke dalam **Environment Variables (PATH)** di Windows Anda.
