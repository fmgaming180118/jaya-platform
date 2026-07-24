@echo off
TITLE JAYA Research Ecosystem Launcher
echo ========================================================
echo       STARTING JAYA RESEARCH AGI ECOSYSTEM
echo ========================================================
echo.

set ROOT_DIR=%~dp0
cd /d "%ROOT_DIR%"

rem Python executable detection
set PYTHON_EXE=python
if exist "%ROOT_DIR%JAYA_RESEARCH\.venv312\Scripts\python.exe" (
    set PYTHON_EXE="%ROOT_DIR%JAYA_RESEARCH\.venv312\Scripts\python.exe"
) else if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
    set PYTHON_EXE="%ROOT_DIR%.venv\Scripts\python.exe"
)

echo [*] Python Runtime: %PYTHON_EXE%
echo [*] Launching FastAPI Backend (Port 8000)...
start "JAYA Research Backend Server" cmd /k "cd /d "%ROOT_DIR%JAYA_RESEARCH" && set PYTHONPATH=src&& %PYTHON_EXE% src/network/research_api.py"

echo [*] Launching React UI Frontend (Port 5173)...
start "JAYA Research UI Frontend" cmd /k "cd /d "%ROOT_DIR%JAYA_RESEARCH\ui" && npm run dev"

echo.
echo ========================================================
echo   JAYA Research Backend & Frontend launched successfully!
echo   UI Dashboard: http://localhost:5173
echo   Backend API:  http://localhost:8000
echo ========================================================
echo.

timeout /t 3 /nobreak >nul
start http://localhost:5173

exit
