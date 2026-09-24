#!/usr/bin/env bash
# install-packages.sh — Python 3.14 compatible installation
# Run karo: bash scripts/install-packages.sh

set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "============================================="
echo "  FaceFlux — Package Installation (Py 3.14)"
echo "============================================="
echo ""

cd "$PROJECT_ROOT/backend"

echo "[1/3] Core packages install ho raha hai..."
pip3 install --break-system-packages \
  "fastapi>=0.115.0" \
  "uvicorn[standard]>=0.32.0" \
  "python-multipart>=0.0.20" \
  "pydantic>=2.10.0" \
  "pydantic-settings>=2.7.0" \
  "aiofiles>=24.1.0" \
  "httpx>=0.28.0" \
  "websockets>=14.0" \
  "psutil>=6.0.0" \
  "python-dotenv>=1.0.0" \
  "structlog>=24.0.0" \
  "Pillow>=10.0.0"

echo ""
echo "[2/3] Computer Vision packages..."
pip3 install --break-system-packages \
  "numpy>=1.26.0" \
  "opencv-python-headless>=4.8.0" \
  "onnxruntime>=1.24.0"

echo ""
echo "[3/3] AI / Face packages..."

# InsightFace
pip3 install --break-system-packages "insightface>=0.7.3" || {
  echo "  ⚠ insightface install fail hua. Manually try karo:"
  echo "     pip3 install --break-system-packages insightface"
}

# GFPGAN (optional - face enhancement ke liye)
pip3 install --break-system-packages "gfpgan>=1.3.8" || {
  echo "  ⚠ gfpgan install fail hua."
  echo "  Gfpgan optional hai — bina iske bhi face swap chalega."
  echo "  Manually try: pip3 install --break-system-packages gfpgan"
}

echo ""
echo "============================================="
echo "  Installation complete!"
echo ""
echo "  Test karo:"
echo "    python3 -c \"import fastapi, uvicorn, onnxruntime, cv2; print('OK')\""
echo "============================================="
