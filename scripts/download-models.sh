#!/usr/bin/env bash
# download-models.sh — Download required AI models to data/models/
# Run once before first use. Resumable and corruption-safe.

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}')/.." && pwd)"
MODEL_DIR="$PROJECT_ROOT/data/models"
mkdir -p "$MODEL_DIR"

MIN_SIZE_BYTES=1048576  # 1 MB — anything smaller = corrupt/incomplete

echo "Downloading FaceFlux AI models to: $MODEL_DIR"
echo ""

# ── Helper: safe download with size check ─────────────────────────────────────
download_file() {
  local url="$1"
  local dest="$2"
  local label="$3"

  # If file exists and is large enough, skip
  if [ -f "$dest" ]; then
    local size
    size=$(stat -c%s "$dest" 2>/dev/null || echo 0)
    if [ "$size" -gt "$MIN_SIZE_BYTES" ]; then
      echo "  ✓ $label already exists ($(( size / 1024 / 1024 )) MB) — skipping."
      return 0
    else
      echo "  ✗ $label is incomplete/corrupt (${size} bytes) — re-downloading..."
      rm -f "$dest"
    fi
  fi

  echo "  Downloading $label..."
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
    echo "  Install aria2c for best experience: sudo apt install aria2"
    exit 1
  fi

  # Verify after download
  local size
  size=$(stat -c%s "$dest" 2>/dev/null || echo 0)
  if [ "$size" -lt "$MIN_SIZE_BYTES" ]; then
    echo "  ERROR: Download failed or incomplete for $label (${size} bytes)."
    rm -f "$dest"
    return 1
  fi
  echo "  ✓ $label downloaded ($(( size / 1024 / 1024 )) MB)."
}

# ── InsightFace buffalo_l ──────────────────────────────────────────────────────
echo "[1/3] InsightFace buffalo_l model"
echo "  Will be auto-downloaded by InsightFace on first use."
echo "  Download location: ~/.insightface/models/buffalo_l/"
echo ""

# ── inswapper_128.onnx ────────────────────────────────────────────────────────
echo "[2/3] inswapper_128.onnx (Face Swap model, ~529 MB)"
echo "  License: Non-commercial/research use only (InsightFace)"
download_file \
  "https://github.com/deepinsight/insightface/releases/download/model-zoo/inswapper_128.onnx" \
  "$MODEL_DIR/inswapper_128.onnx" \
  "inswapper_128.onnx"
echo ""

# ── CodeFormer (replaces GFPGAN — Python 3.14 compatible) ────────────────────
echo "[3/3] CodeFormer weights (Face Enhancement model, ~330 MB)"
echo "  License: Apache-2.0"
echo "  Note: Replaces GFPGAN — better quality + Python 3.14 compatible"
download_file \
  "https://github.com/sczhou/CodeFormer/releases/download/v0.1.0/codeformer.pth" \
  "$MODEL_DIR/codeformer.pth" \
  "codeformer.pth"
echo ""

echo "✓ All model downloads complete!"
echo "  Models stored in: $MODEL_DIR"
echo ""
echo "  Tip: Run 'bash scripts/start.sh' to launch FaceFlux."
