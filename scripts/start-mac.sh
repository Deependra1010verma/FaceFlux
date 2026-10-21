#!/usr/bin/env bash
# FaceFlux — MacBook Air M5 Start Script
# Usage: bash scripts/start-mac.sh
#
# Fixes applied vs generic start.sh:
#   ✓ onnxruntime-silicon auto-installed (CoreML + Metal, NOT standard onnxruntime)
#   ✓ insightface macOS build flags set (prevents arm64 compile failures)
#   ✓ hevc_videotoolbox encoder checked
#   ✓ BiSeNet models verified
#   ✓ .coreml_cache/ created early (prevents first-run permission errors)

# NOTE: Intentionally NOT using "set -e" here — we want explicit error handling
# so the script shows clear messages rather than silently exiting mid-way.

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

# Python
PYTHON=""
if command -v python3.11 >/dev/null 2>&1; then
    PYTHON="python3.11"
else
    echo "  ❌ Python 3.11 is required for InsightFace on Apple Silicon."
    echo "     Fix: brew install python@3.11"
    exit 1
fi
echo "  ✅ Python: $($PYTHON --version)"

# Node
if ! command -v node >/dev/null 2>&1; then
    echo "  ❌ Node.js not found."
    echo "     Fix: brew install node"
    exit 1
fi
echo "  ✅ Node.js: $(node --version)"

# FFmpeg
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "  ❌ FFmpeg not found."
    echo "     Fix: brew install ffmpeg"
    exit 1
fi

# Check VideoToolbox (HEVC)
if ffmpeg -encoders 2>/dev/null | grep -q "hevc_videotoolbox"; then
    echo "  ✅ FFmpeg: HEVC VideoToolbox hardware encoder available ⚡"
elif ffmpeg -encoders 2>/dev/null | grep -q "h264_videotoolbox"; then
    echo "  ✅ FFmpeg: H.264 VideoToolbox available (HEVC not found — update FFmpeg for HEVC)"
else
    echo "  ⚠️  FFmpeg: VideoToolbox not found — will use libx264 (slower, still works)"
fi

# ── Python venv + dependencies ────────────────────────────────────────────────
VENV="$ROOT/backend/.venv"

if [ ! -f "$VENV/bin/activate" ]; then
    echo ""
    echo "  🔧 Creating Python venv..."
    "$PYTHON" -m venv "$VENV"
    if [ $? -ne 0 ]; then
        echo "  ❌ venv creation failed."
        exit 1
    fi

    source "$VENV/bin/activate"
    pip install --upgrade pip -q

    echo "  📦 Installing Python dependencies..."
    # InsightFace needs CFLAGS for arm64 native compilation on macOS.
    # Without this flag, pip may try to build an x86_64 wheel that crashes on M-series.
    CFLAGS="-arch arm64" pip install -r "$ROOT/backend/requirements.txt" -q
    if [ $? -ne 0 ]; then
        echo "  ❌ pip install failed. Try running manually:"
        echo "     cd backend && CFLAGS=\"-arch arm64\" pip install -r requirements.txt"
        exit 1
    fi

    # Official macOS ONNX Runtime wheels may already include CoreML. Keep that
    # working installation when possible; use the silicon wheel only as fallback.
    if "$VENV/bin/python" -c "import onnxruntime as ort; raise SystemExit(0 if 'CoreMLExecutionProvider' in ort.get_available_providers() else 1)" 2>/dev/null; then
        echo "  ✅ Official ONNX Runtime CoreML provider available"
    else
        echo "  🔄 CoreML provider not found — trying onnxruntime-silicon fallback..."
        pip uninstall onnxruntime onnxruntime-gpu -y -q 2>/dev/null || true
        pip install onnxruntime-silicon -q
        if [ $? -ne 0 ]; then
            echo "  ⚠️  CoreML package install failed — app will use CPU fallback"
            pip install onnxruntime -q
        else
            echo "  ✅ onnxruntime-silicon fallback installed"
        fi
    fi

    echo "  ✅ All dependencies installed"
else
    source "$VENV/bin/activate"

    if ! "$VENV/bin/python" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)' 2>/dev/null; then
        echo "  ❌ Existing backend/.venv is not Python 3.11."
        echo "     Remove backend/.venv on the new Mac and rerun this script."
        exit 1
    fi

    # Check if onnxruntime-silicon is already installed (might have been skipped)
    if ! "$VENV/bin/python" -c "import onnxruntime; p = onnxruntime.get_available_providers(); exit(0 if 'CoreMLExecutionProvider' in p else 1)" 2>/dev/null; then
        echo ""
        echo "  🔄 CoreML not available — trying onnxruntime-silicon fallback..."
        pip uninstall onnxruntime onnxruntime-gpu -y -q 2>/dev/null || true
        pip install onnxruntime-silicon -q && echo "  ✅ onnxruntime-silicon installed" || \
            echo "  ⚠️  onnxruntime-silicon install failed — running on CPU only"
    fi
fi

if ! "$VENV/bin/python" -c "import onnxruntime as ort; p=ort.get_available_providers(); print('  ONNX providers:', ', '.join(p)); raise SystemExit(0 if 'CoreMLExecutionProvider' in p else 1)"; then
    echo "  ⚠️  CoreMLExecutionProvider unavailable — FaceFlux will run on CPU fallback."
fi

# ── Create CoreML cache dirs early (avoids permission errors on first run) ────
mkdir -p "$ROOT/.coreml_cache/swapper"
mkdir -p "$ROOT/.coreml_cache/enhancer"
mkdir -p "$ROOT/.coreml_cache/bisenet"
echo "  ✅ CoreML cache dirs ready (.coreml_cache/)"

# ── Check/download models ─────────────────────────────────────────────────────
echo ""
MISSING_MODELS=0
[ ! -f "$ROOT/data/models/inswapper_128.onnx" ] && MISSING_MODELS=$((MISSING_MODELS + 1))
[ ! -f "$ROOT/data/models/GPEN-BFR-512.onnx" ] && [ ! -f "$ROOT/data/models/GPEN-BFR-256.onnx" ] && \
    MISSING_MODELS=$((MISSING_MODELS + 1))

if [ "$MISSING_MODELS" -gt 0 ]; then
    echo "  📥 Downloading AI models (one-time, ~1 GB)..."
    bash "$SCRIPT_DIR/download-models.sh"
else
    echo "  ✅ Core AI models found"
    # BiSeNet optional — show status but don't block
    if [ -f "$ROOT/data/models/bisenet_resnet_34.onnx" ] || [ -f "$ROOT/data/models/bisenet_resnet_18.onnx" ]; then
        echo "  ✅ BiSeNet face parser found (Phase 2 quality enabled ✨)"
    else
        echo "  ℹ️  BiSeNet not found — run 'bash scripts/download-models.sh' for best quality"
        echo "     (App works without it — blending will use fallback mode)"
    fi
fi

# ── Start Backend ─────────────────────────────────────────────────────────────
echo ""
echo "  ▶  Starting Backend (port 8000)..."
cd "$ROOT/backend"
"$VENV/bin/python" -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level warning &
BACKEND_PID=$!

# Wait for backend to be ready (up to 30 seconds)
echo "  ⏳ Waiting for backend..."
BACKEND_READY=0
for i in $(seq 1 60); do
    if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
        BACKEND_READY=1
        echo "  ✅ Backend ready"
        break
    fi
    sleep 0.5
done

if [ "$BACKEND_READY" -eq 0 ]; then
    echo "  ⚠️  Backend didn't respond in 30s — check logs for errors."
    echo "     Common fix: check that all pip packages installed correctly."
fi

# ── Start Frontend ─────────────────────────────────────────────────────────────
echo "  ▶  Starting Frontend (port 3000)..."
cd "$ROOT/frontend"
if [ ! -d "node_modules" ]; then
    echo "  📦 Installing frontend dependencies..."
    npm install -q
fi
npm run dev >/dev/null 2>&1 &
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
echo "  ℹ️  First video job: CoreML compiles models to Metal (~6-7 min one-time)"
echo "     Subsequent runs: instant load from .coreml_cache/"
echo ""
echo "  Press Ctrl+C to stop."
echo "  ──────────────────────────────────────────"
echo ""

# System info
sleep 2
curl -s http://127.0.0.1:8000/system-info 2>/dev/null | "$VENV/bin/python" -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(f\"  📊 System Info:\")
    print(f\"     CPU:   {d.get('cpu', 'N/A')}\")
    print(f\"     RAM:   {d.get('ram_gb', 'N/A')} GB\")
    print(f\"     Accel: {d.get('acceleration', 'N/A')}\")
except:
    pass
" 2>/dev/null || true
echo ""

# ── Mac Sleep Prevention (caffeinate) ─────────────────────────────────────────
CAFFEINATE_PID=""
if command -v caffeinate >/dev/null 2>&1; then
    caffeinate -dis -w $$ &
    CAFFEINATE_PID=$!
    echo "  ☕ Sleep prevention active (caffeinate) — Mac won't sleep during render"
fi

trap "echo ''; echo '  🛑 Stopping FaceFlux...'; kill $BACKEND_PID $FRONTEND_PID $CAFFEINATE_PID 2>/dev/null; echo '  Bye!';" EXIT INT TERM
wait $BACKEND_PID $FRONTEND_PID
