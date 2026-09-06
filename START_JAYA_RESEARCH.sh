#!/usr/bin/env bash
# ==============================================================================
# JAYA Research Launcher for Linux / macOS
# ==============================================================================
set -e

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "========================================================"
echo "       STARTING JAYA RESEARCH AGI ECOSYSTEM"
echo "========================================================"
echo ""

PYTHON_EXE="python3"
if [ -f "$ROOT_DIR/.venv/bin/python" ]; then
    PYTHON_EXE="$ROOT_DIR/.venv/bin/python"
elif [ -f "$ROOT_DIR/.venv-research/bin/python" ]; then
    PYTHON_EXE="$ROOT_DIR/.venv-research/bin/python"
fi

echo "[*] Python Runtime: $PYTHON_EXE"
echo "[*] Launching FastAPI Backend (Port 8000)..."
export PYTHONPATH="packages/jaya-research/src"
export JAYA_DATA_DIR="$ROOT_DIR/data/jaya-research"

"$PYTHON_EXE" -m jaya_research.network.research_api &
BACKEND_PID=$!

echo "[*] Launching React UI Frontend (Port 5173)..."
cd "$ROOT_DIR/packages/jaya-research/ui"
npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================================"
echo "  JAYA Research Backend & Frontend launched!"
echo "  UI Dashboard: http://localhost:5173"
echo "  Backend API:  http://localhost:8000"
echo "========================================================"
echo ""

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT INT TERM
wait
