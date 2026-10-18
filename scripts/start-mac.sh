#!/usr/bin/env bash
# FaceFlux — MacBook Air M5 Start Script
# Usage: bash scripts/start-mac.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo ""
echo "  🍎 FaceFlux — MacBook Air M5"
echo "  ──────────────────────────────────────────"
echo ""

# ── .env setup ────────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/.env" ]; then
    echo "  📋 .env not found — copying from .env.mac"
    cp "$ROOT/.env.mac" "$ROOT/.env"
else
    echo "  ✅ .env found"
fi

# ── Sanity checks ─────────────────────────────────────────────────────────────
echo ""
echo "  🔍 Checking dependencies..."

if ! command -v python3.11 &>/dev/null && ! command -v python3 &>/dev/null; then
    echo "  ❌ Python not found. Run: brew install python@3.11"
    exit 1
fi

PYTHON="python3.11"
if ! command -v python3.11 &>/dev/null; then
    PYTHON="python3"
fi
echo "  ✅ Python: $($PYTHON --version)"

if ! command -v node &>/dev/null; then
    echo "  ❌ Node.js not found. Run: brew install node"
    exit 1
fi
echo "  ✅ Node.js: $(node --version)"

if ! command -v ffmpeg &>/dev/null; then
    echo "  ❌ FFmpeg not found. Run: brew install ffmpeg"
    exit 1
fi

# Verify VideoToolbox is available in this FFmpeg build
if ffmpeg -encoders 2>/dev/null | grep -q "h264_videotoolbox"; then
    echo "  ✅ FFmpeg: VideoToolbox hardware encoder available ⚡"
else
    echo "  ⚠️  FFmpeg: VideoToolbox not found — will use libx264 (slower)"
fi

# ── Check venv ────────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/backend/.venv/bin/activate" ]; then
    echo ""
    echo "  🔧 Creating Python venv..."
    cd "$ROOT/backend"
    $PYTHON -m venv .venv
    source .venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo "  ✅ Dependencies installed"
fi

# ── Check models ──────────────────────────────────────────────────────────────
if [ ! -f "$ROOT/data/models/inswapper_128.onnx" ]; then
    echo ""
    echo "  📥 Downloading AI models (one-time, ~1.2GB)..."
    bash "$SCRIPT_DIR/download-models.sh"
fi

# ── Start Backend ─────────────────────────────────────────────────────────────
echo ""
echo "  ▶  Starting Backend (port 8000)..."
cd "$ROOT/backend"
source .venv/bin/activate
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level warning &
BACKEND_PID=$!

# Wait for backend to be ready
echo "  ⏳ Waiting for backend..."
for i in $(seq 1 20); do
    if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "  ✅ Backend ready"
        break
    fi
    sleep 0.5
done

# ── Start Frontend ─────────────────────────────────────────────────────────────
echo "  ▶  Starting Frontend (port 3000)..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo "  📦 Installing frontend dependencies..."
    npm install -q
fi
npm run dev &
FRONTEND_PID=$!

# ── Ready ─────────────────────────────────────────────────────────────────────
echo ""
echo "  ──────────────────────────────────────────"
echo "  ✅ FaceFlux is running!"
echo ""
echo "  🌐 App:     http://localhost:3000"
echo "  📡 API:     http://localhost:8000"
echo "  📖 Docs:    http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop."
echo "  ──────────────────────────────────────────"
echo ""

# Quick system info
echo "  📊 System Info:"
sleep 2
curl -s http://127.0.0.1:8000/system-info 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f\"  CPU:  {d.get('cpu', 'N/A')}\")
    print(f\"  RAM:  {d.get('ram_gb', 'N/A')} GB\")
    print(f\"  GPU:  {d.get('gpu', 'N/A')}\")
    print(f\"  ACCEL: {d.get('acceleration', 'N/A')}\")
except:
    pass
" 2>/dev/null || true
echo ""

trap "echo ''; echo '  🛑 Stopping FaceFlux...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo '  Bye!'" EXIT INT TERM
wait $BACKEND_PID $FRONTEND_PID
