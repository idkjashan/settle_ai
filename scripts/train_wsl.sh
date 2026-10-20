#!/usr/bin/env bash
# scripts/train_wsl.sh
# Auto-Settle AI — Stage 2 Model Training Launcher for WSL2 / Linux
# Targets NVIDIA RTX 4060 GPU with CUDA acceleration

set -eo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"

# 1. Locate Virtualenv Python
if [[ -f "$REPO_DIR/.venv/bin/python" ]]; then
    PYTHON_BIN="$REPO_DIR/.venv/bin/python"
elif [[ -n "$VIRTUAL_ENV" && -f "$VIRTUAL_ENV/bin/python" ]]; then
    PYTHON_BIN="$VIRTUAL_ENV/bin/python"
else
    PYTHON_BIN="$(which python3)"
fi

echo "=========================================================="
echo "🏎️  Auto-Settle AI — Stage 2 Model Training Engine (WSL)"
echo "Repository: $REPO_DIR"
echo "Python:     $PYTHON_BIN"
echo "=========================================================="

# 2. Check NVIDIA GPU
if command -v nvidia-smi &> /dev/null; then
    echo "🔍 NVIDIA Driver & GPU Status:"
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
else
    echo "⚠️  nvidia-smi not found. Training may fall back to CPU."
fi

# 3. Default Configuration
TASK="cardd"
BASE_MODEL="weights/yolo11m-seg.pt"
EPOCHS=50
BATCH=8
SMOKE_TEST=false
EXTRA_ARGS=()

# 4. Parse Arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --task)
            TASK="$2"
            shift 2
            ;;
        --model)
            BASE_MODEL="$2"
            shift 2
            ;;
        --epochs)
            EPOCHS="$2"
            shift 2
            ;;
        --batch)
            BATCH="$2"
            shift 2
            ;;
        --smoke)
            SMOKE_TEST=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./scripts/train_wsl.sh [options]"
            echo "  --task <cardd|carparts>    Target model task (default: cardd)"
            echo "  --model <path>             Base model checkpoint (default: weights/yolo11m-seg.pt)"
            echo "  --epochs <int>             Number of epochs (default: 50)"
            echo "  --batch <int>              Batch size (default: 8 for 8GB VRAM)"
            echo "  --smoke                    Run 1-epoch smoke test on synthetic mini-dataset"
            exit 0
            ;;
        *)
            EXTRA_ARGS+=("$1")
            shift
            ;;
    esac
done

export CUDA_VISIBLE_DEVICES=0
export OMP_NUM_THREADS=4

if [[ "$SMOKE_TEST" == true ]]; then
    echo "🧪 Running Smoke Test (1 epoch on synthetic mini-dataset)..."
    SMOKE_DATA_DIR="/tmp/autosettle_smoke_data"
    "$PYTHON_BIN" "$REPO_DIR/tools/model_training/prepare_dataset.py" --task smoke-dataset --output-dir "$SMOKE_DATA_DIR" --num-samples 5

    DATA_CONFIG="$SMOKE_DATA_DIR/mini_${TASK}/mini_${TASK}_seg.yaml"
    TARGET_OUT="/tmp/autosettle_smoke_${TASK}_seg.pt"

    "$PYTHON_BIN" "$REPO_DIR/tools/model_training/train_yolo_seg.py" \
        --task "$TASK" \
        --data "$DATA_CONFIG" \
        --model "yolo11n-seg.pt" \
        --epochs 1 \
        --batch 2 \
        --output-weights "$TARGET_OUT" \
        --run-name "smoke_test_${TASK}" \
        "${EXTRA_ARGS[@]}"

    echo "✅ Smoke test completed successfully! Verified checkpoint: $TARGET_OUT"
    exit 0
fi

# Standard Training
DATA_CONFIG="$REPO_DIR/tools/model_training/${TASK}_seg.yaml"
TARGET_OUT="$REPO_DIR/weights/yolo11m-${TASK}-seg.pt"

echo "🚀 Launching full training: task=$TASK, model=$BASE_MODEL, epochs=$EPOCHS, batch=$BATCH"

"$PYTHON_BIN" "$REPO_DIR/tools/model_training/train_yolo_seg.py" \
    --task "$TASK" \
    --data "$DATA_CONFIG" \
    --model "$BASE_MODEL" \
    --epochs "$EPOCHS" \
    --batch "$BATCH" \
    --output-weights "$TARGET_OUT" \
    "${EXTRA_ARGS[@]}"
