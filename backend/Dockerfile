# FaceFlux Backend — Dockerfile for Hugging Face Spaces (or any cloud Docker host)
FROM python:3.11-slim

# Prevent Python from writing .pyc files and buffer output
ENV PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

# Install system dependencies including FFmpeg and OpenCV requirements
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    wget \
    ffmpeg \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces requires a user with UID 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    BASE_DIR=/home/user/app \
    PORT=7860 \
    HOST=0.0.0.0

WORKDIR /home/user/app

# Install Python requirements
COPY --chown=user:user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Create necessary runtime directories
RUN mkdir -p /home/user/app/data/models \
             /home/user/app/data/uploads \
             /home/user/app/data/outputs \
             /home/user/app/data/temp \
             /home/user/app/data/frames \
             /home/user/app/data/logs

# Pre-download inswapper model during build for fast startup
RUN wget -q -c https://github.com/deepinsight/insightface/releases/download/model-zoo/inswapper_128.onnx \
    -O /home/user/app/data/models/inswapper_128.onnx || true

# Pre-download insightface buffalo_l model during build
RUN python3 -c "import insightface; insightface.app.FaceAnalysis(name='buffalo_l')" || true

# Copy backend source code
COPY --chown=user:user . /home/user/app

# Hugging Face Spaces listens on port 7860
EXPOSE 7860

# Start FastAPI server
CMD ["python", "main.py"]
