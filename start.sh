#!/usr/bin/env bash

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

echo "runpod-worker-hunyuan: Starting ComfyUI"
python3 /app/ComfyUI/main.py --listen --port 8188 --disable-auto-launch &

echo "runpod-worker-hunyuan: Starting RunPod Handler"
python3 -u /app/handler.py