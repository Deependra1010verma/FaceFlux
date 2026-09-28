#!/usr/bin/env bash
# start-tunnel.sh — Expose local FaceFlux backend to the internet for free
# Works from anywhere (mobile, remote PC, friends) without port-forwarding!

set -e

PORT=${1:-8000}

echo "=========================================================="
echo " 🌐 FaceFlux Free Cloud Tunnel Launcher"
echo " Target: http://127.0.0.1:$PORT"
echo "=========================================================="

# Check if backend is running
if ! curl -s "http://127.0.0.1:$PORT/health" > /dev/null; then
  echo "⚠️  Warning: Backend http://127.0.0.1:$PORT responded with an error or is not running yet."
  echo "   Make sure your backend is running in another terminal:"
  echo "   python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
  echo ""
fi

# 1. Try cloudflared if available
if command -v cloudflared &>/dev/null; then
  echo "🚀 Launching Cloudflare Quick Tunnel..."
  cloudflared tunnel --url "http://127.0.0.1:$PORT"
  exit 0
fi

# 2. Try npx localtunnel
if command -v npx &>/dev/null; then
  echo "🚀 Cloudflared not found, launching localtunnel via npx..."
  echo "👉 Note: Copy the public URL shown below and paste it in FaceFlux Vercel UI!"
  echo ""
  npx localtunnel --port "$PORT"
  exit 0
fi

# 3. Fallback to pinggy (SSH-based free tunnel, zero installation)
if command -v ssh &>/dev/null; then
  echo "🚀 Launching free Pinggy tunnel via SSH..."
  ssh -p 443 -R0:localhost:"$PORT" -o StrictHostKeyChecking=no a.pinggy.io
  exit 0
fi

echo "❌ Error: Could not find cloudflared, npx, or ssh to create a free tunnel."
