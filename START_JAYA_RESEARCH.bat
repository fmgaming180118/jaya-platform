@echo off
TITLE JAYA Research Launcher
echo ========================================================
echo       STARTING JAYA RESEARCH AGI ECOSYSTEM
echo ========================================================
echo.

set "ROOT_DIR=%~dp0"
cd /d "%ROOT_DIR%"

set "PYTHON_EXE=python"
if exist "%ROOT_DIR%.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%.venv\Scripts\python.exe"
)
if exist "%ROOT_DIR%.venv-research\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%.venv-research\Scripts\python.exe"
)

echo [*] Python Runtime: %PYTHON_EXE%
echo [*] Launching FastAPI Backend (Port 8000)...
start "Backend" cmd /k "cd /d ""%ROOT_DIR%"" && set ""PYTHONPATH=packages\jaya-research\src"" && set ""JAYA_DATA_DIR=%ROOT_DIR%data\jaya-research"" && ""%PYTHON_EXE%"" -m jaya_research.network.research_api"

echo [*] Launching React UI Frontend (Port 5173)...
start "Frontend" cmd /k "cd /d ""%ROOT_DIR%packages\jaya-research\ui"" && npm run dev"

echo.
echo ========================================================
echo   JAYA Research Backend and Frontend launched!
echo   UI Dashboard: http://localhost:5173
echo   Backend API:  http://localhost:8000
echo ========================================================
echo.

start http://localhost:5173
