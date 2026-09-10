# ============================================================
# Pramaan / ECI Qwen-VL OCR service
# Qwen2.5-VL-7B-Instruct — requires an NVIDIA GPU with >= 24 GB VRAM
# ============================================================
#
# No secrets are baked into this image. HF_TOKEN and OCR_SHARED_SECRET
# are supplied at run time via the environment.

FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ------------------------------------------------------------
# Python 3.11 (Ubuntu 22.04 ships 3.10, so use the deadsnakes PPA)
# ------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        software-properties-common ca-certificates gnupg \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y --no-install-recommends \
        python3.11 python3.11-dev python3.11-venv \
        libglib2.0-0 libgomp1 util-linux \
    && ln -sf /usr/bin/python3.11 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

# Bootstrap pip for 3.11 itself via ensurepip (python3.11-venv ships the
# bundled wheels). Ubuntu's python3-pip would install 3.10's pip, which
# `python -m pip` may not resolve at all.
RUN python -m ensurepip --upgrade \
    && python -m pip install --upgrade pip setuptools wheel

# ------------------------------------------------------------
# Hugging Face cache
# ------------------------------------------------------------
# Mount a persistent volume at /models so the ~16 GB of weights survive
# container restarts:  -v /srv/pramaan-models:/models
ENV HF_HOME=/models \
    HF_HUB_CACHE=/models/hub

RUN mkdir -p /models

# ------------------------------------------------------------
# Dependencies (own layer, so code edits do not re-resolve wheels)
# ------------------------------------------------------------
WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install -r /app/requirements.txt

# ------------------------------------------------------------
# Application
# ------------------------------------------------------------
COPY main.py /app/main.py

# The service runs as this non-root user. Privileges are dropped by the
# entrypoint rather than with USER, because the entrypoint must first
# repair ownership of a mounted cache volume, which arrives root-owned
# and would otherwise be unwritable.
RUN useradd --create-home --uid 10001 ocr && chown -R ocr:ocr /app /models
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod 0755 /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

EXPOSE 8000

# One worker only: a single Qwen2.5-VL instance owns the GPU. Scale by
# adding replicas on more GPUs, never by raising --workers.
CMD ["python", "-m", "uvicorn", "main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--log-level", "info"]
