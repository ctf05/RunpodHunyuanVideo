#!/usr/bin/env bash

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

echo "runpod-worker-hunyuan: Starting ComfyUI"
python /comfyui/main.py --disable-auto-launch --disable-metadata &

echo "runpod-worker-hunyuan: Starting RunPod Handler"
python -u /handler.py