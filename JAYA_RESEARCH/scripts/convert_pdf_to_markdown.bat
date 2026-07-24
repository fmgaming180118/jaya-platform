@echo off
REM Convert PDF Peraturan Direktur to Markdown with Images & Tables
REM Konversi PDF Peraturan Direktur ke Markdown dengan Gambar & Tabel

setlocal enabledelayedexpansion

echo.
echo ============================================================
echo     JAYA PDF to Markdown Converter
echo     Konversi PDF ke Markdown + Gambar + Tabel
echo ============================================================
echo.

cd /d "%~dp0.."

REM Check if python is available
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Error: Python not found in PATH
    pause
    exit /b 1
)

REM Install dependencies if needed
echo Installing dependencies...
pip install -q -r requirements.txt

REM Run converter for the specific PDF
echo.
echo Converting PDF: Peraturan Direktur Nomor 02 Tahun 2021...
echo.

python scripts\pdf_to_markdown_converter.py ^
    "docs\Peraturan Direktur Nomor 02 Tahun 2021 tentang Penetapan Pedoman Tugas Akhir Politeknik STMI Jakarta Secure.pdf" ^
    -o "data\pdf_conversions\Peraturan_Direktur_02_2021" ^
    -v

if %errorlevel% equ 0 (
    echo.
    echo ============================================================
    echo ✅ Konversi berhasil!
    echo.
    echo Output tersedia di:
    echo   📁 data\pdf_conversions\Peraturan_Direktur_02_2021\
    echo.
    echo Struktur output:
    echo   📄 Peraturan_Direktur_02_2021.md (Markdown utama)
    echo   📁 images\ (Semua gambar dari PDF)
    echo   📁 tables\ (Semua tabel dalam format Markdown)
    echo   📋 conversion_report.json (Laporan konversi)
    echo ============================================================
) else (
    echo.
    echo ============================================================
    echo ❌ Konversi gagal. Periksa error messages di atas.
    echo ============================================================
)

echo.
pause
