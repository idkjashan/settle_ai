# Utility & Training Scripts

This directory contains utility scripts for model training, dataset structuring, visual sample generation, and presentation builds.

| Script | Purpose | Execution |
| :--- | :--- | :--- |
| `train_wsl.sh` | Automated model training & fine-tuning script for Linux / WSL on NVIDIA CUDA GPUs. Supports smoke test mode. | `./scripts/train_wsl.sh --smoke --task cardd` |
| `train_windows.bat` | Model training launcher for native Windows environments with CUDA. | `scripts\train_windows.bat --smoke --task cardd` |
| `extract_and_structure_rtdetr_vd.py` | Extracts and structures MOT Challenge sequence frames and annotations from the RTDETR-VD benchmark. | `uv run python scripts/extract_and_structure_rtdetr_vd.py` |
| `create_stage2_visual_samples.py` | Generates annotated dual-mask and Set-of-Marks visual samples for documentation. | `uv run python scripts/create_stage2_visual_samples.py` |
| `build_presentation.py` | Programmatically compiles the official PowerPoint executive presentation in `docs/presentation/`. | `uv run --with python-pptx python scripts/build_presentation.py` |
