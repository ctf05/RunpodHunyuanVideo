#!/usr/bin/env bash

# Use libtcmalloc for better memory management
TCMALLOC="$(ldconfig -p | grep -Po "libtcmalloc.so.\d" | head -n 1)"
export LD_PRELOAD="${TCMALLOC}"

echo "runpod-worker-hunyuan: Starting ComfyUI"
python3 /comfyui/main.py --disable-auto-launch --disable-metadata &

echo "runpod-worker-hunyuan: Waiting for ComfyUI to start"
sleep 1000

echo "runpod-worker-hunyuan: Starting RunPod Handler"
python3 -u /handler.py