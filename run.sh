#!/usr/bin/env bash
set -euo pipefail

PYTHON=${PYTHON:-python3.13}

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/fastapi-server"
FRONTEND_DIR="$ROOT_DIR/electron"
VENV_DIR="$BACKEND_DIR/.venv"

cleanup() {
    echo ""
    echo "Shutting down..."
    # Kill any process on port 8000
    EXISTING_PID=$(lsof -ti:8000 2>/dev/null || true)
    if [[ -n "$EXISTING_PID" ]]; then
        kill "$EXISTING_PID" 2>/dev/null || true
    fi
    echo "Done."
}
trap cleanup EXIT INT TERM

setup_backend() {
    echo "==> Setting up Python backend..."
    if [[ ! -d "$VENV_DIR" ]]; then
        "$PYTHON" -m venv "$VENV_DIR"
    fi
    source "$VENV_DIR/bin/activate"
    pip install -q --upgrade pip
    pip install -q -r "$BACKEND_DIR/requirements.txt"
}

setup_frontend() {
    echo "==> Setting up Electron frontend..."
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        npm install --prefix "$FRONTEND_DIR" --silent
    fi
}

start_frontend() {
    echo "==> Starting Electron frontend..."
    cd "$FRONTEND_DIR"
    npm start
}

setup_backend
setup_frontend
start_frontend
