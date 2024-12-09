# Use RunPod PyTorch base image
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

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
    COMFY_OUTPUT_PATH=/comfyui/output \
    CMAKE_BUILD_PARALLEL_LEVEL=8

# Install system dependencies
RUN apt-get update && apt-get install -y \
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
RUN set +o pipefail && /usr/bin/yes | comfy --workspace /comfyui install --cuda-version 12.1 --nvidia --version 0.3.7 --skip-manager || true

# Change to ComfyUI directory and install custom nodes
WORKDIR /comfyui
RUN git clone https://github.com/kijai/ComfyUI-HunyuanVideoWrapper.git custom_nodes/hunyuan_wrapper && \
    git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git custom_nodes/video_helper_suite

# Create necessary directories
RUN mkdir -p \
    models/diffusion_models \
    models/vae \
    models/clip/clip-vit-large-patch14 \
    models/LLM/llava-llama-3-8b-text-encoder-tokenizer \
    workflows \
    output

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

# Add model selection arguments
ARG USE_SMALL_MODEL=false
ARG USE_BLOCK_SWAPPING=true

# Download HunyuanVideo models based on selection
RUN if [ "$USE_SMALL_MODEL" = "true" ] ; then \
    wget -O models/diffusion_models/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_720_cfgdistill_fp8_e4m3fn.safetensors && \
    wget -O models/vae/hunyuan_video_vae_bf16.safetensors https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_vae_bf16.safetensors; \
    else \
    wget -O models/diffusion_models/hunyuan_video_720_cfgdistill_bf16.safetensors https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_720_cfgdistill_bf16.safetensors && \
    wget -O models/vae/hunyuan_video_vae_fp32.safetensors https://huggingface.co/Kijai/HunyuanVideo_comfy/resolve/main/hunyuan_video_vae_fp32.safetensors; \
    fi

# Return to root directory
WORKDIR /

# Copy requirements and install Python dependencies
COPY requirements.txt /
RUN pip install --no-cache-dir -r requirements.txt
RUN cd /comfyui/custom_nodes/hunyuan_wrapper && pip install --no-cache-dir -r requirements.txt
RUN cd /comfyui/custom_nodes/video_helper_suite && pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY handler.py start.sh /
COPY workflows/*.json /comfyui/workflows/

# Select appropriate workflow
RUN if [ "$USE_SMALL_MODEL" = "true" ] && [ "$USE_BLOCK_SWAPPING" = "true" ]; then \
    mv /comfyui/workflows/small_model_block_swapping.json /comfyui/workflows/workflow.json; \
    elif [ "$USE_SMALL_MODEL" = "true" ] && [ "$USE_BLOCK_SWAPPING" = "false" ]; then \
    mv /comfyui/workflows/small_model_no_block_swapping.json /comfyui/workflows/workflow.json; \
    elif [ "$USE_SMALL_MODEL" = "false" ] && [ "$USE_BLOCK_SWAPPING" = "true" ]; then \
    mv /comfyui/workflows/large_model_block_swapping.json /comfyui/workflows/workflow.json; \
    else \
    mv /comfyui/workflows/large_model_no_block_swapping.json /comfyui/workflows/workflow.json; \
    fi

# Make start script executable
RUN chmod +x /start.sh

# Clean up
RUN apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Expose ports
EXPOSE 8080 8188

# Set the entrypoint
CMD ["/start.sh"]