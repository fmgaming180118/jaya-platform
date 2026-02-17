@echo off
cd /d "%~dp0"
echo ==========================================
echo    JAYA SOVEREIGN ENTITY - FULL STARTUP
echo ==========================================
echo.

REM Read SLM path (only if present)
if exist slm_path.txt (
    set /p SLM_PATH=<slm_path.txt
) else (
    echo [!] slm_path.txt not found — continuing without SLM_PATH
)

echo [1/2] Starting Research API (Port 8000)...
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH — API won't start.
) else (
    start "Jaya Research API" cmd /c "python src/network/research_api.py"
)

echo [2/2] Starting UI (Port 5173)...
if exist ui (
    pushd ui
    where npm >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] npm not found in PATH — UI won't start.
    ) else (
        start "Jaya UI" cmd /c "npm run dev"
    )
    popd
) else (
    echo [!] 'ui' folder not found — skipping UI startup.
)

echo.
echo ==========================================
echo   API:  http://localhost:8000
echo   UI:   http://localhost:5173
echo ==========================================
echo.
echo Research mode active.
pause
