# FaceFlux 🎭

**Privacy-first, local AI face-swap web application.**
Your video and face image never leave your machine.

```
● Local Processing — Your files stay on this device.
```

---

## Features

- Upload a source video + reference face photo
- Detect all faces in the video; select the target person
- Run real AI face swap (InsightFace inswapper_128 + optional GFPGAN enhancement)
- Preserve original audio, FPS, and scene
- Three quality modes: Fast / Balanced / High
- Real-time progress via Server-Sent Events
- CPU + NVIDIA CUDA support
- Zero cloud, zero analytics, zero telemetry

---

## Architecture

```
Browser (localhost:3000)
      │
      ▼
Next.js / React / TypeScript / Tailwind
      │
      ▼  HTTP REST + SSE
FastAPI (localhost:8000)
      │
   ┌──┴─────────────┐
   │                │
Face Detection    Video Pipeline
(InsightFace)     │
                  ├── FFmpeg (probe / audio)
                  ├── FaceSwapper (inswapper_128)
                  ├── FaceEnhancer (GFPGAN)
                  └── FFmpeg (encode + mux)
```

---

## Prerequisites

| Tool | Version | Notes |
|------|---------|-------|
| Python | 3.10+ | 3.11 recommended |
| Node.js | 18+ | 20 LTS recommended |
| FFmpeg | Any recent | `sudo apt install ffmpeg` |
| npm | 9+ | — |

GPU (optional but recommended):
- NVIDIA GPU with CUDA 11.8+
- `nvidia-smi` accessible in PATH

---

## Quick Start (Without Docker)

### 1 — Clone & setup

```bash
git clone <repo>
cd FaceFlux
bash scripts/setup.sh
```

### 2 — Download AI models

> **Internet required for this step only.**

```bash
bash scripts/download-models.sh
```

Models downloaded:
| Model | Size | License |
|-------|------|---------|
| `inswapper_128.onnx` | ~556 MB | Non-commercial (InsightFace) |
| `GFPGANv1.4.pth` | ~348 MB | Apache-2.0 |
| `buffalo_l` (InsightFace) | ~326 MB | Non-commercial (auto-download) |

> ⚠️ **License Notice**: `inswapper_128.onnx` and InsightFace `buffalo_l` are released for
> **non-commercial research / personal use only**. Do not use in commercial products
> without verifying the current license.

### 3 — Start

```bash
bash scripts/start.sh
```

Or manually:

```bash
# Terminal 1 — Backend
cd backend
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open **http://localhost:3000**

---

## Docker

### CPU only

```bash
docker compose up --build
```

### NVIDIA GPU

Install [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) first, then uncomment the `deploy.resources` section in `docker-compose.yml`:

```yaml
deploy:
  resources:
    reservations:
      devices:
        - driver: nvidia
          count: 1
          capabilities: [gpu]
```

```bash
docker compose up --build
```

---

## Privacy & Security

| Requirement | Status |
|-------------|--------|
| No cloud upload | ✅ |
| No external AI API | ✅ |
| No analytics | ✅ |
| Bound to 127.0.0.1 | ✅ |
| Filename sanitization | ✅ |
| Path traversal prevention | ✅ |
| Shell injection prevention | ✅ (no `shell=True`) |

After AI models are downloaded, the application works fully offline.

---

## Processing Pipeline

```
Upload video + face photo
          │
     Validate inputs
          │
   Probe video (ffprobe)
          │
  Detect faces in video
    (InsightFace buffalo_l)
          │
   User selects target face
          │
   Track target face (IoU)
          │
    Swap faces per frame
    (inswapper_128.onnx)
          │
  [Optional] GFPGAN enhance
          │
  FFmpeg encode (H.264)
          │
   Mux with original audio
          │
       output.mp4
```

---

## Job States

```
QUEUED → ANALYZING → DETECTING → TRACKING → SWAPPING → ENHANCING → ENCODING → COMPLETED
                                                                              → FAILED
```

---

## Quality Modes

| Mode | CRF | Preset | Enhancement | Det. Rate |
|------|-----|--------|-------------|-----------|
| Fast | 23 | ultrafast | Off | Every 6 frames |
| Balanced | 18 | medium | On | Every 3 frames |
| High | 15 | slow | On | Every frame |

---

## API Reference

```
GET  /health              — Status check
GET  /system-info         — Hardware info

POST /upload/video        — Upload source video
POST /upload/face         — Upload reference face image

POST /jobs                — Create and start a job
GET  /jobs/{id}           — Full job details
GET  /jobs/{id}/progress  — Lightweight progress poll
GET  /jobs/{id}/stream    — SSE real-time progress
GET  /jobs/{id}/faces     — Detected face thumbnails
GET  /jobs/{id}/output    — Download result MP4
DELETE /jobs/{id}         — Delete job
```

Interactive API docs: http://localhost:8000/docs

---

## Configuration

Copy `.env.example` to `.env` and edit:

```env
GPU_PROVIDER=auto         # auto | cuda | cpu
DEFAULT_QUALITY=balanced
MAX_VIDEO_SIZE_MB=2048
OUTPUT_CRF=18
```

---

## Troubleshooting

### "No face detected in reference photo"
- Ensure the image contains a clearly visible, front-facing face
- Try a higher resolution image
- Lighting should be adequate

### "Failed to load InsightFace"
```bash
pip install insightface onnxruntime
```

### CUDA not detected
```bash
pip install onnxruntime-gpu
nvidia-smi  # Should show GPU
```

### Processing is slow on CPU
- Use **Fast** quality mode
- Lower `DET_SIZE` to 320 in `.env`
- Process shorter clips first

### Out of memory
- Close other applications
- Use **Fast** mode
- Reduce `FRAME_BATCH_SIZE` in `.env`

---

## Ubuntu System Setup

```bash
# Python 3.11
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt-get update
sudo apt-get install python3.11 python3.11-venv python3.11-dev

# FFmpeg
sudo apt-get install ffmpeg

# OpenCV system deps
sudo apt-get install libgl1 libglib2.0-0

# Node.js 20 LTS
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install nodejs
```

---

## Project Structure

```
FaceFlux/
├── frontend/            Next.js + TypeScript + Tailwind
│   ├── app/            App Router pages
│   ├── components/     React components
│   ├── hooks/          Custom hooks
│   ├── lib/            API client, utilities
│   └── types/          TypeScript types
│
├── backend/
│   ├── app/
│   │   ├── api/        FastAPI routers
│   │   ├── core/       Config, security, job store
│   │   ├── models/     Pydantic models
│   │   ├── pipelines/  FaceDetector, FaceSwapper, FaceEnhancer, VideoProcessor
│   │   └── services/   Hardware detection, FFmpeg
│   ├── tests/          pytest test suite
│   └── main.py         Entry point
│
├── data/               All local data (gitignored)
│   ├── models/         AI model weights
│   ├── uploads/        Uploaded files
│   ├── outputs/        Finished videos
│   └── temp/           Intermediate files
│
├── scripts/            setup.sh, start.sh, download-models.sh
└── docker/             Dockerfiles
```

---

## License

Application code: MIT

**AI Model Licenses (must be respected separately):**
- InsightFace `buffalo_l`: Non-commercial research/personal use
- `inswapper_128.onnx`: Non-commercial research/personal use  
- GFPGAN: Apache-2.0

---

## Disclaimer

This software is intended for personal, non-commercial, creative use only.
The user is responsible for ensuring use complies with all applicable laws,
including laws regarding consent, privacy, and deepfake regulations in their jurisdiction.
Do not use this tool to create non-consensual imagery of real people.
