# Use RunPod PyTorch image as base
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Switch to root for installations
USER root

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_PREFER_BINARY=1 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    NVIDIA_VISIBLE_DEVICES=0 \
    CUDA_VISIBLE_DEVICES=0 \
    CUDA_DEVICE_ORDER=PCI_BUS_ID \
    DEBIAN_FRONTEND=noninteractive \
    HOST=0.0.0.0 \
    RECOMPUTE=True \
    SAVE_MEMORY=True \
    COMFY_OUTPUT_PATH=/app/ComfyUI/output \
    CMAKE_BUILD_PARALLEL_LEVEL=8

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
    google-perftools \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install comfy-cli
RUN pip install comfy-cli

# Install ComfyUI
RUN /usr/bin/yes | comfy --workspace /comfyui install --cuda-version 11.8 --nvidia --version 0.3.7

# Change to ComfyUI directory
WORKDIR /comfyui

# Install custom nodes
RUN git clone https://github.com/kijai/ComfyUI-HunyuanVideoWrapper.git custom_nodes/hunyuan_wrapper && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git custom_nodes/video_helper_suite

# Create necessary directories
RUN mkdir -p models/diffusion_models \
    models/vae \
    models/clip/clip-vit-large-patch14 \
    models/LLM/llava-llama-3-8b-text-encoder-tokenizer \
    output

# Download HunyuanVideo models
RUN wget -O models/diffusion_models/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors \
    https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors && \
    wget -O models/vae/hunyuan_video_vae_bf16.safetensors \
    https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_vae_bf16.safetensors

# Download CLIP model
RUN wget -O models/clip/clip-vit-large-patch14/model.safetensors \
    https://huggingface.co/openai/clip-vit-large-patch14/resolve/main/model.safetensors

# Clone LLM text encoder
RUN git clone https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer \
    models/LLM/llava-llama-3-8b-text-encoder-tokenizer

# Go back to root
WORKDIR /

# Install Python dependencies and custom nodes requirements
COPY requirements.txt /
RUN pip install -r requirements.txt
RUN cd /comfyui/custom_nodes/hunyuan_wrapper && pip install -r requirements.txt
RUN cd /comfyui/custom_nodes/video_helper_suite && pip install -r requirements.txt

# Copy application files
COPY handler.py start.sh /
COPY workflows/hyvideo_t2v_example_01.json /comfyui/workflows/

# Make start script executable
RUN chmod +x /start.sh

# Clean up
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Expose ports
EXPOSE 8080 8188

# Set the entrypoint
CMD ["/start.sh"]