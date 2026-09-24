#!/usr/bin/env bash
# setup.sh — One-time environment setup for FaceFlux
# Usage: bash scripts/setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "=========================================="
echo "  FaceFlux — Local Setup"
echo "=========================================="

# ── 1. Check Python ─────────────────────────────────────────────────────────
echo ""
echo "[1/5] Checking Python..."
PYTHON=$(command -v python3.11 2>/dev/null || command -v python3 2>/dev/null || echo "")
if [ -z "$PYTHON" ]; then
  echo "ERROR: Python 3.10+ is required. Install it first."
  exit 1
fi
PY_VER=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "  Python: $PY_VER at $PYTHON"

# ── 2. Check FFmpeg ──────────────────────────────────────────────────────────
echo ""
echo "[2/5] Checking FFmpeg..."
if ! command -v ffmpeg &>/dev/null; then
  echo "  FFmpeg not found."
  echo "  Install with: sudo apt-get install ffmpeg"
  echo "  Continuing anyway — FFmpeg is required at runtime."
else
  echo "  FFmpeg: $(ffmpeg -version 2>&1 | head -1)"
fi

# ── 3. Python dependencies ───────────────────────────────────────────────────
echo ""
echo "[3/5] Installing Python backend dependencies..."
echo "  Installing system-wide (requires --break-system-packages on newer Ubuntu)..."
pip3 install --break-system-packages -r "$PROJECT_ROOT/backend/requirements.txt" \
  || pip3 install -r "$PROJECT_ROOT/backend/requirements.txt"
echo "  Backend dependencies installed."

# ── 4. Node / npm ───────────────────────────────────────────────────────────
echo ""
echo "[4/5] Installing frontend dependencies..."
cd "$PROJECT_ROOT/frontend"
npm install
echo "  Frontend dependencies installed."

# ── 5. Environment file ─────────────────────────────────────────────────────
echo ""
echo "[5/5] Creating .env file..."
cd "$PROJECT_ROOT"
if [ ! -f ".env" ]; then
  cp .env.example .env
  echo "  Created .env from .env.example — review and adjust if needed."
else
  echo "  .env already exists — skipping."
fi

# ── Create data dirs ─────────────────────────────────────────────────────────
mkdir -p data/{uploads,temp,frames,outputs,models,logs}

echo ""
echo "=========================================="
echo "  Setup complete!"
echo ""
echo "  Next step — Download AI models (internet required):"
echo "    bash scripts/download-models.sh"
echo ""
echo "  Then start FaceFlux:"
echo "    bash scripts/start.sh"
echo ""
echo "  Open: http://localhost:3000"
echo "=========================================="
