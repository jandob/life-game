# RunPod Serverless worker for artgen's remote runner (Qwen-Image 2.1 base).
# Built by RunPod's GitHub integration (Dockerfile path: remote/runpod/Dockerfile, build context: repo root).
# No weights in the image: the endpoint's model cache provides Qwen/Qwen-Image-2.1.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1

RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Same versions as the verified local setup (tools/artgen README): torch 2.14.1, diffusers at the pinned commit.
# The CUDA 13.0 wheel needs a host driver for CUDA >= 13.0 (set the endpoint's allowed CUDA versions accordingly).
RUN pip install torch==2.14.1 --index-url https://download.pytorch.org/whl/cu130
COPY remote/runpod/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt

COPY rp_handler.py /app/rp_handler.py
WORKDIR /app
CMD ["python", "-u", "rp_handler.py"]
