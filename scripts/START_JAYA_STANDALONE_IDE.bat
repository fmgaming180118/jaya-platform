@echo off
title JAYA Standalone IDE Launcher
color 0A
echo =============================================================
echo        MELUNCURKAN APLIKASI DESKTOP STANDALONE JAYA IDE
echo =============================================================
echo.

cd /d "%~dp0\.."
python scripts\run_standalone_jaya_ide.py

pause
