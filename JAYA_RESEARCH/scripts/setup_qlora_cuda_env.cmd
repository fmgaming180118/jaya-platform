@echo off
setlocal

cd /d %~dp0\..

set "VENV_DIR=.venv312"
set "PYTHON_EXE=%CD%\%VENV_DIR%\Scripts\python.exe"

echo [STEP 1/5] Checking Python 3.12...
py -3.12 --version > nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python 3.12 is not installed.
  echo [HINT] Install Python 3.12, then re-run this script.
  exit /b 1
)

if not exist "%PYTHON_EXE%" (
  echo [STEP 2/5] Creating virtual environment %VENV_DIR%...
  py -3.12 -m venv %VENV_DIR%
  if errorlevel 1 (
    echo [ERROR] Failed to create %VENV_DIR%.
    exit /b 1
  )
) else (
  echo [STEP 2/5] Reusing existing virtual environment %VENV_DIR%.
)

echo [STEP 3/5] Upgrading pip tooling...
"%PYTHON_EXE%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [ERROR] Failed upgrading pip tooling.
  exit /b 1
)

echo [STEP 4/5] Installing QLoRA dependencies...
"%PYTHON_EXE%" -m pip install -r requirements-qlora.txt
if errorlevel 1 (
  echo [ERROR] Failed installing requirements-qlora.txt.
  exit /b 1
)

echo [STEP 5/5] Installing CUDA-enabled PyTorch (cu121 wheels)...
"%PYTHON_EXE%" -m pip install --upgrade --index-url https://download.pytorch.org/whl/cu121 torch torchvision torchaudio
if errorlevel 1 (
  echo [ERROR] Failed installing CUDA-enabled PyTorch wheels.
  exit /b 1
)

echo [VERIFY] Checking CUDA availability...
"%PYTHON_EXE%" -c "import torch,sys;print('torch=' + str(torch.__version__));print('torch_cuda=' + str(torch.version.cuda));print('cuda_available=' + str(torch.cuda.is_available()));print('cuda_device_count=' + str(torch.cuda.device_count()));sys.exit(0 if torch.cuda.is_available() else 2)"
if errorlevel 1 (
  echo [ERROR] CUDA is still unavailable in %VENV_DIR%.
  echo [HINT] Ensure NVIDIA driver is installed and compatible, then rerun this script.
  exit /b 1
)

echo [OK] CUDA-ready QLoRA environment is ready: %PYTHON_EXE%
echo [NEXT] run_qlora_hybrid_loop.cmd will auto-use .venv312\Scripts\python.exe
exit /b 0
