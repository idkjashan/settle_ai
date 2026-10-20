@echo off
REM scripts\train_windows.bat
REM Auto-Settle AI — Stage 2 Model Training Launcher for Windows 11
REM Supports native PyTorch GPU training with CUDA on RTX 4060

setlocal enabledelayedexpansion

REM Resolve repo root
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%.."
cd /d "%REPO_DIR%"

echo ==========================================================
echo    Auto-Settle AI -- Stage 2 Model Training Engine (Windows)
echo ==========================================================

REM Locate Python executable
if exist "%REPO_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_BIN=%REPO_DIR%\.venv\Scripts\python.exe"
) else (
    set "PYTHON_BIN=python"
)

echo Python: %PYTHON_BIN%

REM Query NVIDIA GPU if available
where nvidia-smi >nul 2>nul
if %ERRORLEVEL% equ 0 (
    echo Detected GPU:
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
) else (
    echo WARNING: nvidia-smi not found. Training may run on CPU.
)

REM Default parameters
set "TASK=cardd"
set "BASE_MODEL=weights\yolo11m-seg.pt"
set "EPOCHS=50"
set "BATCH=8"
set "SMOKE=0"

:parse_args
if "%~1"=="" goto run_training
if /i "%~1"=="--task" (
    set "TASK=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--model" (
    set "BASE_MODEL=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--epochs" (
    set "EPOCHS=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--batch" (
    set "BATCH=%~2"
    shift
    shift
    goto parse_args
)
if /i "%~1"=="--smoke" (
    set "SMOKE=1"
    shift
    goto parse_args
)
if /i "%~1"=="--help" (
    echo Usage: scripts\train_windows.bat [--task cardd^|carparts] [--model weights\yolo11m-seg.pt] [--epochs 50] [--batch 8] [--smoke]
    exit /b 0
)
shift
goto parse_args

:run_training
if "%SMOKE%"=="1" (
    echo [INFO] Running Windows Smoke Test on synthetic mini-dataset...
    set "SMOKE_DIR=%TEMP%\autosettle_smoke_data"
    "%PYTHON_BIN%" tools\model_training\prepare_dataset.py --task smoke-dataset --output-dir "!SMOKE_DIR!" --num-samples 5
    if %ERRORLEVEL% neq 0 (
        echo [ERROR] Smoke dataset generation failed!
        exit /b %ERRORLEVEL%
    )
    set "DATA_CONFIG=!SMOKE_DIR!\mini_%TASK%\mini_%TASK%_seg.yaml"
    set "TARGET_OUT=%TEMP%\autosettle_smoke_%TASK%_seg.pt"
    "%PYTHON_BIN%" tools\model_training\train_yolo_seg.py --task "%TASK%" --data "!DATA_CONFIG!" --model "yolo11n-seg.pt" --epochs 1 --batch 2 --output-weights "!TARGET_OUT!" --run-name "smoke_test_%TASK%"
    if %ERRORLEVEL% equ 0 (
        echo [SUCCESS] Windows smoke test passed successfully! Output: !TARGET_OUT!
    ) else (
        echo [ERROR] Smoke test training failed!
    )
    exit /b %ERRORLEVEL%
)

set "DATA_CONFIG=tools\model_training\%TASK%_seg.yaml"
set "TARGET_OUT=weights\yolo11m-%TASK%-seg.pt"

echo [INFO] Launching Windows training: task=%TASK%, model=%BASE_MODEL%, epochs=%EPOCHS%, batch=%BATCH%
"%PYTHON_BIN%" tools\model_training\train_yolo_seg.py --task "%TASK%" --data "%DATA_CONFIG%" --model "%BASE_MODEL%" --epochs %EPOCHS% --batch %BATCH% --output-weights "%TARGET_OUT%"

if %ERRORLEVEL% equ 0 (
    echo [SUCCESS] Training completed and verified: %TARGET_OUT%
) else (
    echo [ERROR] Training failed with exit code %ERRORLEVEL%
)

exit /b %ERRORLEVEL%
