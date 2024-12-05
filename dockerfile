# Use RunPod PyTorch image as base
FROM runpod/pytorch:2.2.0-py3.10-cuda12.1.1-devel-ubuntu22.04

# Switch to root for installations
USER root

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    CUDA_VISIBLE_DEVICES=all \
    RECOMPUTE=True \
    SAVE_MEMORY=True

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python-is-python3 \
    git \
    wget \
    ffmpeg \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Create necessary directories
RUN mkdir -p /app/ComfyUI \
    /app/custom_nodes \
    /app/models/checkpoints \
    /app/models/clip \
    /app/models/text_encoder \
    /app/models/vae \
    /app/workflows

# Install ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /app/ComfyUI

# Install HunyuanVideo wrapper
RUN git clone https://github.com/kijai/ComfyUI-HunyuanVideoWrapper.git /app/custom_nodes/hunyuan_wrapper

# Copy application files
COPY handler.py requirements.txt /app/
COPY workflows/hyvideo_t2v_example_01.json /app/workflows/

# Download models
RUN wget -O /app/models/checkpoints/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors \
    https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors && \
    wget -O /app/models/vae/hunyuan_video_vae_bf16.safetensors \
    https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_vae_bf16.safetensors && \
    wget -O /app/models/clip/model.safetensors \
    https://huggingface.co/openai/clip-vit-large-patch14/resolve/main/model.safetensors

# Clone text encoder model
RUN git clone https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer \
    /app/models/text_encoder/llava-llama-3-8b-text-encoder-tokenizer

# Install Python dependencies
COPY requirements.txt /app/
RUN cd /app/ComfyUI && pip install -r requirements.txt
RUN cd /app/custom_nodes/hunyuan_wrapper && pip install -r requirements.txt
RUN pip install -r requirements.txt

# Clean up
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Expose port 8080
EXPOSE 8080

# Set the entrypoint
CMD ["python", "handler.py"]