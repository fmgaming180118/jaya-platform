@echo off
echo ==========================================
echo    JAYA SOVEREIGN ENTITY - FULL STARTUP
echo ==========================================
echo.

REM Read SLM path
set /p SLM_PATH=<slm_path.txt

echo [1/2] Starting Research API (Port 8000)...
start "Jaya Research API" cmd /c "python src/network/research_api.py"

echo [2/2] Starting UI (Port 5173)...
cd ui
start "Jaya UI" cmd /c "npm run dev"
cd ..

echo.
echo ==========================================
echo   API:  http://localhost:8000
echo   UI:   http://localhost:5173
echo ==========================================
echo.
echo Research mode active.
pause
