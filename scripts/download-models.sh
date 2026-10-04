#!/usr/bin/env bash
# download-models.sh — Download required AI models to data/models/
# Run once before first use. Resumable and corruption-safe.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$PROJECT_ROOT/data/models"
mkdir -p "$MODEL_DIR"

MIN_SIZE_BYTES=1048576  # 1 MB — anything smaller = corrupt/incomplete

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  FaceFlux — AI Model Downloader"
echo "  Models will be saved to: $MODEL_DIR"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# ── Helper: safe download with size check ─────────────────────────────────────
download_file() {
  local url="$1"
  local dest="$2"
  local label="$3"
  local min_size="${4:-$MIN_SIZE_BYTES}"

  # If file exists and is large enough, skip
  if [ -f "$dest" ]; then
    local size
    size=$(stat -c%s "$dest" 2>/dev/null || echo 0)
    if [ "$size" -gt "$min_size" ]; then
      echo "  ✓ $label already exists ($(( size / 1024 / 1024 )) MB) — skipping."
      return 0
    else
      echo "  ✗ $label is incomplete/corrupt (${size} bytes) — re-downloading..."
      rm -f "$dest"
    fi
  fi

  echo "  ↓  Downloading $label..."
  if command -v aria2c &>/dev/null; then
    aria2c -x 16 -s 16 -k 1M --file-allocation=none -q \
      --show-console-readout=true \
      "$url" -d "$(dirname "$dest")" -o "$(basename "$dest")"
  elif command -v wget &>/dev/null; then
    wget -c --progress=bar "$url" -O "$dest"
  elif command -v curl &>/dev/null; then
    curl -L --progress-bar -C - "$url" -o "$dest"
  else
    echo "  ERROR: aria2c, wget, or curl required."
    echo "  Install: sudo apt install aria2"
    exit 1
  fi

  # Verify after download
  local size
  size=$(stat -c%s "$dest" 2>/dev/null || echo 0)
  if [ "$size" -lt "$min_size" ]; then
    echo "  ✗ ERROR: Download failed or incomplete for $label (${size} bytes)."
    rm -f "$dest"
    return 1
  fi
  echo "  ✓ $label downloaded ($(( size / 1024 / 1024 )) MB)."
}

# ── [1] InsightFace buffalo_l ──────────────────────────────────────────────────
echo "[1/4] InsightFace buffalo_l (Face Detector)"
echo "      Auto-downloaded by InsightFace on first run."
echo "      Location: ~/.insightface/models/buffalo_l/"
echo ""

# ── [2] inswapper_128.onnx ────────────────────────────────────────────────────
echo "[2/4] inswapper_128.onnx — Face Swap Engine (~529 MB)"
echo "      License: Non-commercial/research use only (InsightFace)"
download_file \
  "https://github.com/deepinsight/insightface/releases/download/model-zoo/inswapper_128.onnx" \
  "$MODEL_DIR/inswapper_128.onnx" \
  "inswapper_128.onnx" \
  "100000000"
echo ""

# ── [3] GPEN-BFR-512.onnx ────────────────────────────────────────────────────
# GPEN replaces CodeFormer — works on Python 3.14, pure ONNX, better quality
# Source: FaceFusion model assets (harisreedhar/Face-Upscalers-ONNX)
echo "[3/4] GPEN-BFR-512.onnx — Face Enhancer, primary (~330 MB)"
echo "      License: MIT (yangxy/GPEN)"
echo "      Upgrades: 128px inswapper output → 512px sharp, detailed face"

GPEN_512_URL_PRIMARY="https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gpen_bfr_512.onnx"
GPEN_512_URL_FALLBACK="https://huggingface.co/harisreedhar/Face-Upscalers-ONNX/resolve/main/GPEN-BFR-512.onnx"

if ! download_file \
  "$GPEN_512_URL_PRIMARY" \
  "$MODEL_DIR/GPEN-BFR-512.onnx" \
  "GPEN-BFR-512.onnx (primary)" \
  "50000000"; then
  echo "  Primary URL failed — trying fallback..."
  download_file \
    "$GPEN_512_URL_FALLBACK" \
    "$MODEL_DIR/GPEN-BFR-512.onnx" \
    "GPEN-BFR-512.onnx (fallback)" \
    "50000000"
fi
echo ""

# ── [4] GPEN-BFR-256.onnx ────────────────────────────────────────────────────
# Smaller/faster alternative to 512 version — used as automatic fallback
echo "[4/4] GPEN-BFR-256.onnx — Face Enhancer, fallback (~80 MB)"
echo "      Auto-used if GPEN-512 unavailable or on low-VRAM GPU"

GPEN_256_URL_PRIMARY="https://github.com/facefusion/facefusion-assets/releases/download/models-3.0.0/gpen_bfr_256.onnx"
GPEN_256_URL_FALLBACK="https://huggingface.co/harisreedhar/Face-Upscalers-ONNX/resolve/main/GPEN-BFR-256.onnx"

if ! download_file \
  "$GPEN_256_URL_PRIMARY" \
  "$MODEL_DIR/GPEN-BFR-256.onnx" \
  "GPEN-BFR-256.onnx (primary)" \
  "10000000"; then
  echo "  Primary URL failed — trying fallback..."
  download_file \
    "$GPEN_256_URL_FALLBACK" \
    "$MODEL_DIR/GPEN-BFR-256.onnx" \
    "GPEN-BFR-256.onnx (fallback)" \
    "10000000"
fi
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✓ All downloads complete!"
echo ""
echo "  Models in: $MODEL_DIR"
ls -lh "$MODEL_DIR"/*.onnx 2>/dev/null || echo "  (No .onnx files found yet)"
echo ""
echo "  Next: bash scripts/start.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
