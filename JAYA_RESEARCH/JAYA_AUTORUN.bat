@echo off
chcp 65001 > nul
cd /d "%~dp0"

title JAYA Research - Autorun

echo.
echo  =============================================
echo   JAYA RESEARCH - AUTORUN LAUNCHER
echo   Backend + UI + DigitalTwin Loop
echo  =============================================
echo.

REM Cek virtual environment
if not exist ".venv312\Scripts\python.exe" (
    echo [ERROR] Virtual environment tidak ditemukan!
    echo Jalankan: python -m venv .venv312
    echo Lalu:     .venv312\Scripts\pip install -r requirements.txt
    pause
    exit /b 1
)

REM Jalankan autorun (sekali klik, terus jalan)
.venv312\Scripts\python.exe jaya_autorun.py

echo.
echo [JAYA] Launcher dihentikan.
pause
