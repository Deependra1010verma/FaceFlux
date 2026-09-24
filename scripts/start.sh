#!/usr/bin/env bash
# start.sh — Start both frontend and backend
set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting FaceFlux..."
echo "Backend:  http://127.0.0.1:8000"
echo "Frontend: http://127.0.0.1:3000"
echo "Press Ctrl+C to stop both."
echo ""

# Activate venv if it exists
VENV="$PROJECT_ROOT/backend/.venv"
if [ -d "$VENV" ]; then
  source "$VENV/bin/activate"
fi

# Start backend in background
(cd "$PROJECT_ROOT/backend" && \
  python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload) &
BACKEND_PID=$!

# Start frontend in background
(cd "$PROJECT_ROOT/frontend" && \
  npm run dev -- --port 3000) &
FRONTEND_PID=$!

cleanup() {
  echo ""
  echo "Stopping FaceFlux..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  wait $BACKEND_PID $FRONTEND_PID 2>/dev/null || true
  echo "Done."
}
trap cleanup EXIT INT TERM

wait
