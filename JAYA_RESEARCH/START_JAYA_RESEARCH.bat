@echo off
TITLE JAYA Research Launcher
echo ========================================================
echo       STARTING JAYA RESEARCH AGI ECOSYSTEM
echo ========================================================
echo.

set "MODULE_DIR=%~dp0"
cd /d "%MODULE_DIR%"

set "PYTHON_EXE=python"
if exist "%MODULE_DIR%.venv312\Scripts\python.exe" (
    set "PYTHON_EXE=%MODULE_DIR%.venv312\Scripts\python.exe"
)

echo [*] Python Runtime: %PYTHON_EXE%
echo [*] Launching FastAPI Backend (Port 8000)...
start "Backend" cmd /k "cd /d "%MODULE_DIR%" && set PYTHONPATH=src && %PYTHON_EXE% src/network/research_api.py"

echo [*] Launching React UI Frontend (Port 5173)...
start "Frontend" cmd /k "cd /d "%MODULE_DIR%ui" && npm run dev"

echo.
echo ========================================================
echo   JAYA Research Backend and Frontend launched!
echo   UI Dashboard: http://localhost:5173
echo   Backend API:  http://localhost:8000
echo ========================================================
echo.

start http://localhost:5173
