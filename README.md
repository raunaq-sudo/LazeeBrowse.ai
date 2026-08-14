# LazeeBrowse.ai

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/raunaq-sudo/files/actions/workflows/ci.yml/badge.svg)](https://github.com/raunaq-sudo/files/actions/workflows/ci.yml)

Autonomous browser agent built with **Electron** (frontend) and **FastAPI** (WebSocket backend). LazeeBrowse.ai controls your real browser — navigating, clicking, typing, running JS, and capturing network activity — while producing reports, PDFs, DOCX/XLSX files, and more.

> ⚠️ **Security note:** LazeeBrowse.ai can execute arbitrary JavaScript and commands in your real browser. Only run it on pages and systems you trust, and treat it as a powerful automation tool.

## Features

- **Real browser control** — navigate, click, type, scroll, submit forms, press keys via Electron webview.
- **Run JS on the page** — execute arbitrary JavaScript in the live page context.
- **Network capture** — inspect the payloads a site loads (URLs, methods, statuses, request bodies) via Electron `webRequest`.
- **Deep Dive (Tree-of-Thought)** — explores multiple strategies, scores them, backtracks and replans.
- **File generation** — write reports as PDF (HTML/CSS via headless Chromium), DOCX, XLSX, or text/markdown; read back PDF/DOCX/XLSX/PPTX.
- **Hybrid rolling memory** — recent messages kept raw; older context rolled into a summary persisted in SQLite.
- **Multi-provider LLM support** — OpenAI, Anthropic Claude, Google Gemini, DeepSeek, OpenRouter.
- **Frameless window** with light/dark theme, file sidebar, and save-to-PDF overlay.

## Project Structure

```
browser_agent/
├── electron/
│   ├── package.json
│   └── src/
│       ├── main.js           # Electron main process (webRequest capture, JS exec, IPC)
│       ├── preload.js        # Secure IPC bridge
│       ├── index.html        # UI
│       ├── styles.css        # Styling
│       └── app.js            # WebSocket client + browser command handler
├── fastapi-server/
│   ├── main.py               # FastAPI server entrypoint (uvicorn)
│   ├── app.py                # Chat/history manager, agent orchestration, ToT, WebSocket API
│   ├── browser_tools_electron.py  # LangChain tools driving the browser + files
│   ├── tot_agent.py          # Tree-of-Thought agent (deep-dive mode)
│   ├── prompts/              # System prompts
│   ├── config.py             # Model registry + provider clients
│   ├── db.py                 # SQLite settings store
│   ├── .env.example          # Environment template
│   └── requirements.txt      # Python dependencies
├── docker-compose.yml        # backend-only + full desktop (VNC) services
├── Dockerfile                # full desktop image (backend + Electron over VNC)
├── docker/entrypoint.sh      # Xvfb + VNC/noVNC + app launcher
└── run.sh                    # One-command setup + launch
```

## Prerequisites

- **Python 3.13+** (3.10+ may work, tested against 3.13)
- **Node.js 18+** and **npm**
- One or more LLM API keys — [OpenAI](https://platform.openai.com), [Anthropic](https://console.anthropic.com), [Google Gemini](https://aistudio.google.com), [DeepSeek](https://platform.deepseek.com), or [OpenRouter](https://openrouter.ai)

## Quick Start

```bash
# One-command setup and launch (creates venv + installs Electron deps)
./run.sh
```

### Manual

```bash
# 1. Backend
cd fastapi-server
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py                # http://localhost:8000

# 2. Frontend (in a separate terminal)
cd electron
npm install
npm start
```

### Docker (backend only)

```bash
cp fastapi-server/.env.example fastapi-server/.env   # then fill in your keys
docker compose up --build backend
```

### Docker (full app with VNC)

Runs the backend **and** the Electron UI inside a virtual display — no desktop needed. Open the UI in any browser via noVNC:

```bash
docker compose up --build desktop
# then open http://localhost:6080/vnc.html
```

You can also connect a regular VNC client to `localhost:5900`. Tune the display with `RESOLUTION` (default `1440x900x24`). Don't run the `backend` and `desktop` services at the same time — both expose host port `8000`.

## Configuration

API keys are entered in the UI and stored per-provider in the local SQLite settings DB (`fastapi-server/data/settings.db`). No keys are required server-side to get started.

For Docker deployments, copy `fastapi-server/.env.example` to `fastapi-server/.env` and set the variables you need. `docker-compose.yml` mounts `./data/{files,browser_strategy,downloads}` for persistence.

## API

### REST

| Method | Path                      | Description                          |
| ------ | ------------------------- | ------------------------------------ |
| GET    | `/health`                 | Health + active session count        |
| GET    | `/api/models`             | List available LLM models            |
| GET/POST | `/api/settings`         | Read/write app settings              |
| GET/POST/DELETE | `/api/recent-projects` | Recently opened projects         |

### WebSocket

Connect at `ws://localhost:8000/ws/{session_id}`.

- Browser commands flow as `browser_command` messages and return via `browser_result`.
- Configure the session with `{ "provider": "...", "model": "...", "api_key": "..." }`.

## Running Tests

```bash
cd fastapi-server
source .venv/bin/activate
pip install -r requirements.txt pytest
python -m pytest tests/ -v
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please read the [Code of Conduct](CODE_OF_CONDUCT.md).

## Security

Found a vulnerability or accidentally committed a secret? Report it via [SECURITY.md](SECURITY.md) or email **rsiraswar@gmail.com**.

## License

[MIT](LICENSE) © 2026 Raunaq S. (raunaq-sudo)
