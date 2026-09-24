#!/usr/bin/env bash
# download-models.sh — Download required AI models to data/models/
# Run once before first use.
set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODEL_DIR="$PROJECT_ROOT/data/models"
mkdir -p "$MODEL_DIR"

echo "Downloading FaceFlux AI models to: $MODEL_DIR"
echo ""

# ── InsightFace buffalo_l ──────────────────────────────────────────────────────
# The InsightFace FaceAnalysis class downloads this automatically on first use.
# However you can pre-download here:
echo "[1/2] InsightFace buffalo_l model"
echo "  Will be auto-downloaded by InsightFace on first use."
echo "  Download location: ~/.insightface/models/buffalo_l/"

# ── inswapper_128.onnx ────────────────────────────────────────────────────────
INSWAPPER="$MODEL_DIR/inswapper_128.onnx"
if [ -f "$INSWAPPER" ]; then
  echo "[2/2] inswapper_128.onnx already exists — skipping."
else
  echo "[2/2] Downloading inswapper_128.onnx..."
  echo "  License: Non-commercial/research use only (InsightFace)"
  echo "  Source: HuggingFace deepinsight/inswapper"
  echo ""
  echo "  Attempting download (requires internet access)..."
  if command -v wget &>/dev/null; then
    wget -q --show-progress \
      "https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx" \
      -O "$INSWAPPER"
  elif command -v curl &>/dev/null; then
    curl -L --progress-bar \
      "https://huggingface.co/deepinsight/inswapper/resolve/main/inswapper_128.onnx" \
      -o "$INSWAPPER"
  else
    echo "  ERROR: wget or curl required. Install one and retry."
    echo "  Or manually download to: $INSWAPPER"
    exit 1
  fi
  echo "  inswapper_128.onnx downloaded."
fi

# ── GFPGAN (optional) ─────────────────────────────────────────────────────────
GFPGAN="$MODEL_DIR/GFPGANv1.4.pth"
if [ -f "$GFPGAN" ]; then
  echo "[Optional] GFPGANv1.4.pth already exists — skipping."
else
  echo "[Optional] Downloading GFPGANv1.4.pth (face enhancement)..."
  echo "  License: Apache-2.0"
  if command -v wget &>/dev/null; then
    wget -q --show-progress \
      "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth" \
      -O "$GFPGAN"
  elif command -v curl &>/dev/null; then
    curl -L --progress-bar \
      "https://github.com/TencentARC/GFPGAN/releases/download/v1.3.4/GFPGANv1.4.pth" \
      -o "$GFPGAN"
  fi
  echo "  GFPGANv1.4.pth downloaded."
fi

echo ""
echo "Model download complete!"
echo "Models are stored in: $MODEL_DIR"
