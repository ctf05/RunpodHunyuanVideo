#!/usr/bin/env bash

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

echo "runpod-worker-hunyuan: Starting ComfyUI"
python /app/ComfyUI/main.py --disable-auto-launch --disable-metadata &

# Wait for ComfyUI to initialize (10 seconds)
echo "runpod-worker-hunyuan: Waiting for ComfyUI to initialize..."
sleep 10

echo "runpod-worker-hunyuan: Starting RunPod Handler"
python -u /app/handler.py