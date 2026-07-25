#!/usr/bin/env bash
set -euo pipefail

PYTHON=${PYTHON:-python3.13}

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$ROOT_DIR/fastapi-server"
FRONTEND_DIR="$ROOT_DIR/electron"
VENV_DIR="$BACKEND_DIR/.venv"

BACKEND_PID=""

cleanup() {
    echo ""
    echo "Shutting down..."
    if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
        kill "$BACKEND_PID" 2>/dev/null || true
        wait "$BACKEND_PID" 2>/dev/null || true
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
    playwright install chromium --with-deps 2>/dev/null || playwright install chromium
}

setup_frontend() {
    echo "==> Setting up Electron frontend..."
    if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
        npm install --prefix "$FRONTEND_DIR" --silent
    fi
}

start_backend() {
    echo "==> Starting backend on http://127.0.0.1:8000 ..."
    source "$VENV_DIR/bin/activate"
    cd "$BACKEND_DIR"
    python main.py &
    BACKEND_PID=$!

    echo "    Waiting for backend to be ready..."
    for i in $(seq 1 40); do
        if curl -s http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "    Backend is ready."
            return 0
        fi
        sleep 1
    done
    echo "    Backend failed to start within 40 seconds."
    exit 1
}

start_frontend() {
    echo "==> Starting Electron frontend..."
    cd "$FRONTEND_DIR"
    npm start
}

setup_backend
setup_frontend
start_backend
start_frontend
