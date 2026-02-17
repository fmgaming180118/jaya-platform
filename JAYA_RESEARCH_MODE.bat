@echo off
title JAYA - RESEARCH MODE
cls
echo ==================================================
echo           J A Y A   R E S E A R C H
echo           Initializing UI and API...
echo ==================================================
REM Pastikan berpindah ke direktori script (termasuk pergantian drive)
pushd "%~dp0JAYA_RESEARCH"

REM Launch tray launcher (no console). Prefer .venv pythonw if available.
if exist .venv\Scripts\pythonw.exe (
    start "" .venv\Scripts\pythonw.exe src\tray_launcher.py
) else (
    where pythonw >nul 2>&1
    if errorlevel 1 (
        echo [WARNING] pythonw not found — launching tray with regular python (console may appear).
        start "" python src\tray_launcher.py
    ) else (
        start "" pythonw src\tray_launcher.py
    )
)

popd
exit /b 0
