@echo off
echo ==========================================
echo    JAYA SOVEREIGN ENTITY - FULL STARTUP
echo ==========================================
echo.

REM Read SLM path
set /p SLM_PATH=<slm_path.txt

echo [1/2] Starting Brain API (Port 8000)...
start "Jaya Brain API" cmd /c "python src/brain_v2/brain_api.py --slm %SLM_PATH%"

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
echo Press any key to shutdown...
pause >nul
