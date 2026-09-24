#!/usr/bin/env bash
# install-backend.sh — Install Python backend dependencies
# Run this once after cloning the project
#
# Usage:
#   bash scripts/install-backend.sh

set -e
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$PROJECT_ROOT/backend"

echo "================================================"
echo "  FaceFlux — Backend Dependency Installation"
echo "================================================"
echo ""

# Check Python version
PYTHON=$(command -v python3.11 2>/dev/null || command -v python3 2>/dev/null)
if [ -z "$PYTHON" ]; then
  echo "ERROR: Python 3.10+ required. Install it first."
  exit 1
fi

PY_VER=$($PYTHON --version 2>&1)
echo "Python: $PY_VER"
echo ""

# Try to create venv (may fail on systems without python3-venv)
VENV="$BACKEND/.venv"
VENV_CREATED=false

if $PYTHON -m venv "$VENV" --without-pip 2>/dev/null; then
  echo "Created virtual environment at $VENV"
  # Bootstrap pip inside venv
  if curl -sS https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py 2>/dev/null; then
    "$VENV/bin/python" /tmp/get-pip.py -q
    "$VENV/bin/pip" install -q --upgrade pip
    "$VENV/bin/pip" install -r "$BACKEND/requirements.txt"
    VENV_CREATED=true
    echo ""
    echo "✓ Installed in virtual environment: $VENV"
    echo ""
    echo "To activate: source $VENV/bin/activate"
  else
    echo "Could not bootstrap pip for venv. Falling back to system pip."
  fi
fi

if [ "$VENV_CREATED" = "false" ]; then
  echo "Installing system-wide with pip3..."
  # Ubuntu 24.04+ requires --break-system-packages
  pip3 install --break-system-packages -r "$BACKEND/requirements.txt" 2>/dev/null || \
  pip3 install -r "$BACKEND/requirements.txt"
  echo ""
  echo "✓ Backend packages installed system-wide."
fi

echo ""
echo "================================================"
echo "  Backend installation complete!"
echo ""
echo "  Next: Install frontend deps"
echo "    cd frontend && npm install"
echo ""
echo "  Then download AI models:"
echo "    bash scripts/download-models.sh"
echo "================================================"
