# Use RunPod PyTorch image as base
FROM nvidia/cuda:12.6.3-cudnn-devel-ubuntu20.04

# Switch to root for installations
USER root

# Set environment variables
# TORCH_CUDA_ARCH_LIST supports L4 A5000 RTX3090 RTX 4090 A6000 A40 L40 L40s 6000 Ada, can add more
# Sageattention 1 optimized for 3090 and 4090 only
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_PREFER_BINARY=1 \
    NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics \
    NVIDIA_VISIBLE_DEVICES=0 \
    CUDA_VISIBLE_DEVICES=0 \
    CUDA_DEVICE_ORDER=PCI_BUS_ID \
    DEBIAN_FRONTEND=noninteractive \
    HOST=0.0.0.0 \
    TORCH_CUDA_ARCH_LIST="8.6;8.9" \
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

RUN python --version && \
    python -c "import sys; print(f'Python {sys.version}')"

# Install comfy-cli
RUN pip install comfy-cli

# Install ComfyUI
RUN /usr/bin/yes | comfy --workspace /comfyui install --skip-manager

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

# Download CLIP model and configuration files
RUN cd models/clip/clip-vit-large-patch14 && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/resolve/main/model.safetensors && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/raw/main/config.json && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/raw/main/preprocessor_config.json && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/raw/main/special_tokens_map.json && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/raw/main/tokenizer.json && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/raw/main/tokenizer_config.json && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/raw/main/vocab.json && \
    wget https://huggingface.co/openai/clip-vit-large-patch14/raw/main/merges.txt

# Download LLM text encoder and configuration files
RUN cd models/LLM/llava-llama-3-8b-text-encoder-tokenizer && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/config.json && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/generation_config.json && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/model-00001-of-00004.safetensors && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/model-00002-of-00004.safetensors && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/model-00003-of-00004.safetensors && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/model-00004-of-00004.safetensors && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/model.safetensors.index.json && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/special_tokens_map.json && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/tokenizer.json && \
    wget https://huggingface.co/Kijai/llava-llama-3-8b-text-encoder-tokenizer/resolve/main/tokenizer_config.json

# Go back to root
WORKDIR /

# upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies and custom nodes requirements
COPY requirements.txt /
RUN pip install -r requirements.txt
RUN cd /comfyui/custom_nodes/hunyuan_wrapper && pip install -r requirements.txt
RUN cd /comfyui/custom_nodes/video_helper_suite && pip install -r requirements.txt
RUN git clone https://github.com/juntang-zhuang/sageattention.git && \
    cd sageattention && \
    pip install .

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