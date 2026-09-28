---
title: FaceFlux Backend
emoji: 🎭
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
---

# FaceFlux AI Backend

High-performance AI Face Swap and Generation API powered by InsightFace, ONNX Runtime, and FastAPI.

## Endpoints
- `GET /health` — Health check & system status
- `POST /upload/video` — Upload target media (Video or Image)
- `POST /upload/face` — Upload reference face photo
- `POST /jobs` — Dispatch face swap job
- `GET /jobs/{id}` — Poll job progress
- `GET /jobs/{id}/output` — Download result media
