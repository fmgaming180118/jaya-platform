@echo off
setlocal EnableDelayedExpansion

cd /d %~dp0\..

set "PYTHON_EXE=%QLORA_PYTHON%"
if "%PYTHON_EXE%"=="" (
  if exist .venv312\Scripts\python.exe (
    set "PYTHON_EXE=.venv312\Scripts\python.exe"
  ) else if exist .venv\Scripts\python.exe (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
  ) else (
    set "PYTHON_EXE=python"
  )
)

if not exist data\qlora mkdir data\qlora
if not exist data\qlora\logs mkdir data\qlora\logs

set LOG=data\qlora\logs\qlora_hybrid_loop.log
set DATASET=data\qlora\language_policy_qlora_dataset.jsonl
set ADAPTER=data\qlora\adapter-qwen3-4b-language
set REPORT=data\qlora\eval_report.json
set OLLAMA_PORT=11434
set OLLAMA_WAIT_RETRIES=20
set DATASET_VARIANTS=3
set DATASET_NUM_PREDICT=120
set DATASET_TIMEOUT=60
set DATASET_RETRIES=2
set DATASET_NUM_CTX=2048

set OLLAMA_MODEL=%~1
if "%OLLAMA_MODEL%"=="" set OLLAMA_MODEL=qwen3:4b

echo [START] Hybrid QLoRA loop with model %OLLAMA_MODEL% >> %LOG%
echo [PYTHON] Using interpreter: %PYTHON_EXE% >> %LOG%
"%PYTHON_EXE%" --version >> %LOG% 2>&1
if errorlevel 1 (
  echo [FATAL] Python interpreter failed: %PYTHON_EXE% >> %LOG%
  exit /b 1
)

call :ensure_cuda_ready
if errorlevel 1 (
  echo [FATAL] CUDA preflight failed. Training loop cannot continue. >> %LOG%
  exit /b 1
)

echo [CONFIG] variants=%DATASET_VARIANTS% num_predict=%DATASET_NUM_PREDICT% timeout=%DATASET_TIMEOUT%s retries=%DATASET_RETRIES% num_ctx=%DATASET_NUM_CTX% no_thinking=1 >> %LOG%

echo [INFO] Running forever. Press Ctrl+C if running in foreground. >> %LOG%

call :ensure_ollama
if errorlevel 1 (
  echo [FATAL] Ollama preflight failed. Cannot start loop. >> %LOG%
  exit /b 1
)

:loop
echo [CYCLE !date! !time!] START >> %LOG%

call :ensure_ollama
if errorlevel 1 (
  echo [WARN] Ollama unavailable. Retry next cycle. >> %LOG%
  echo [CYCLE !date! !time!] END >> %LOG%
  timeout /t 60 > nul
  goto loop
)

echo [STEP] DATASET_BUILD START !date! !time! >> %LOG%
"%PYTHON_EXE%" -u src\training\build_qlora_dataset_from_ollama.py --model %OLLAMA_MODEL% --variants-per-key %DATASET_VARIANTS% --num-predict %DATASET_NUM_PREDICT% --request-timeout %DATASET_TIMEOUT% --retries %DATASET_RETRIES% --num-ctx %DATASET_NUM_CTX% --disable-thinking --out %DATASET% >> %LOG% 2>&1
set DATASET_RC=!errorlevel!
echo [STEP] DATASET_BUILD END !date! !time! code=!DATASET_RC! >> %LOG%
if not "!DATASET_RC!"=="0" (
  echo [WARN] Dataset build failed. Skip train/eval this cycle. >> %LOG%
  echo [CYCLE !date! !time!] END >> %LOG%
  timeout /t 60 > nul
  goto loop
)

echo [STEP] TRAIN_QLORA START !date! !time! >> %LOG%
"%PYTHON_EXE%" -u src\training\train_qlora_language_adapter.py --base-model Qwen/Qwen3-4B-Instruct-2507 --dataset %DATASET% --output-dir %ADAPTER% --epochs 1 --batch-size 1 --grad-accum 16 --max-seq-length 512 >> %LOG% 2>&1
set TRAIN_RC=!errorlevel!
echo [STEP] TRAIN_QLORA END !date! !time! code=!TRAIN_RC! >> %LOG%
if not "!TRAIN_RC!"=="0" (
  echo [WARN] Training failed. Skip eval this cycle. >> %LOG%
  echo [CYCLE !date! !time!] END >> %LOG%
  timeout /t 60 > nul
  goto loop
)

echo [STEP] EVAL START !date! !time! >> %LOG%
"%PYTHON_EXE%" -u src\training\evaluate_qlora_language_adapter.py --base-model Qwen/Qwen3-4B-Instruct-2507 --adapter-dir %ADAPTER% --dataset %DATASET% --sample-count 24 --gate-metric avg_weighted_score --min-delta 0.03 --fail-on-gate --out %REPORT% >> %LOG% 2>&1
set EVAL_RC=!errorlevel!
echo [STEP] EVAL END !date! !time! code=!EVAL_RC! >> %LOG%

if "!EVAL_RC!"=="2" (
  echo [GATE] FAIL !date! !time! >> %LOG%
) else if not "!EVAL_RC!"=="0" (
  echo [EVAL] ERROR !date! !time! code=!EVAL_RC! >> %LOG%
) else (
  echo [GATE] PASS !date! !time! >> %LOG%
)

echo [CYCLE !date! !time!] END >> %LOG%
timeout /t 300 > nul
goto loop


:ensure_ollama
powershell -NoProfile -Command "$listener = Get-NetTCPConnection -LocalPort %OLLAMA_PORT% -State Listen -ErrorAction SilentlyContinue; if ($null -ne $listener) { exit 0 } else { exit 1 }"
if "!errorlevel!"=="0" goto ensure_model

echo [OLLAMA] Port %OLLAMA_PORT% not listening. Starting ollama serve... >> %LOG%
start "OLLAMA-SERVE" /min cmd /c "ollama serve"

for /l %%I in (1,1,%OLLAMA_WAIT_RETRIES%) do (
  timeout /t 2 > nul
  powershell -NoProfile -Command "$listener = Get-NetTCPConnection -LocalPort %OLLAMA_PORT% -State Listen -ErrorAction SilentlyContinue; if ($null -ne $listener) { exit 0 } else { exit 1 }"
  if "!errorlevel!"=="0" goto ensure_model
)

echo [OLLAMA] Failed to bring up API on port %OLLAMA_PORT%. >> %LOG%
exit /b 1


:ensure_model
ollama list | findstr /I /C:"%OLLAMA_MODEL%" > nul 2>&1
if "!errorlevel!"=="0" exit /b 0

echo [OLLAMA] Model %OLLAMA_MODEL% not found locally. Pulling... >> %LOG%
ollama pull %OLLAMA_MODEL% >> %LOG% 2>&1
if not "!errorlevel!"=="0" (
  echo [OLLAMA] Failed pulling model %OLLAMA_MODEL%. >> %LOG%
  exit /b 1
)
echo [OLLAMA] Model %OLLAMA_MODEL% is ready. >> %LOG%
exit /b 0


:ensure_cuda_ready
"%PYTHON_EXE%" -c "import importlib.util,sys;sys.exit(0 if importlib.util.find_spec('torch') else 3)" > nul 2>&1
if not "!errorlevel!"=="0" (
  echo [PYTORCH] torch is missing in selected interpreter. >> %LOG%
  echo [PYTORCH] Run scripts\setup_qlora_cuda_env.cmd or set QLORA_PYTHON to CUDA-ready Python. >> %LOG%
  exit /b 1
)

"%PYTHON_EXE%" -c "import torch,sys;print('torch=' + str(torch.__version__));print('torch_cuda=' + str(torch.version.cuda));print('cuda_available=' + str(torch.cuda.is_available()));print('cuda_device_count=' + str(torch.cuda.device_count()));sys.exit(0 if torch.cuda.is_available() else 2)" >> %LOG% 2>&1
if "!errorlevel!"=="0" exit /b 0

echo [PYTORCH] CUDA unavailable in selected interpreter. >> %LOG%
echo [PYTORCH] Run scripts\setup_qlora_cuda_env.cmd then restart loop. >> %LOG%
exit /b 1
