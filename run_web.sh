#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

echo ""
echo "============================================================"
echo "  Meraki Config Manager V2 - Local Secure Web Interface"
echo "============================================================"
echo ""

# ── Check Python ──────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "[ERROR] python3 is not installed."
  echo "        Install it from https://python.org or via: brew install python"
  exit 1
fi
PYVER=$(python3 --version 2>&1)
echo "[1/3] $PYVER found."

# ── Virtual environment ────────────────────────────────────────────────────────
VENV=".web_venv"
if [ ! -f "$VENV/bin/activate" ]; then
  echo "[2/3] Creating virtual environment..."
  python3 -m venv "$VENV"
else
  echo "[2/3] Virtual environment ready."
fi
source "$VENV/bin/activate"

# ── Install / update dependencies ─────────────────────────────────────────────
echo "[3/3] Installing dependencies..."
pip install -r requirements-web.txt -q

# ── Launch ─────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Starting local-only server at http://127.0.0.1:8000"
echo "  Press Ctrl+C to stop."
echo "============================================================"
echo ""

# Open browser after a short delay
(sleep 2 && open "http://127.0.0.1:8000") &

python -m uvicorn webapp.app:app --host 127.0.0.1 --port 8000
