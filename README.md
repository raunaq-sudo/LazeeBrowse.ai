# LazeeBrowse.ai

Autonomous browser agent built with **Electron** (frontend) and **FastAPI** (WebSocket backend). LazeeBrowse.ai controls your real browser — navigating, clicking, typing, running JS, and capturing network activity — while producing reports, PDFs, DOCX/XLSX files, and more.

## Project Structure

```
lazee-browser/
├── electron/
│   ├── package.json
│   └── src/
│       ├── main.js           # Electron main process (webRequest capture, JS exec, IPC)
│       ├── preload.js        # Secure IPC bridge
│       ├── index.html        # UI
│       ├── styles.css        # Styling
│       └── app.js            # WebSocket client + browser command handler
├── fastapi-server/
│   ├── main.py               # FastAPI WebSocket server
│   ├── app.py                # Chat/history manager, agent orchestration, ToT
│   ├── browser_tools_electron.py  # LangChain tools driving the browser + files
│   ├── tot_agent.py          # Tree-of-Thought agent (deep-dive mode)
│   ├── prompts/              # System prompts
│   └── requirements.txt      # Python dependencies
└── run.sh                    # One-command setup + launch
```

## Setup & Run

```bash
# One-command setup and launch (Python 3.13 venv + Electron)
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

# 2. Frontend
cd electron
npm install
npm start
```

## Features

- **Real browser control** — navigate, click, type, scroll, submit forms, press keys via Electron webview.
- **Run JS on the page** — execute arbitrary JavaScript in the live page context.
- **Network capture** — inspect the payloads a site loads (URLs, methods, statuses, request bodies) via Electron `webRequest`.
- **Deep Dive (Tree-of-Thought)** — explores multiple strategies, scores them, backtracks and replans.
- **File generation** — write reports as PDF (HTML/CSS via headless Chromium), DOCX, XLSX, or text/markdown; read back PDF/DOCX/XLSX/PPTX.
- **Hybrid rolling memory** — recent messages kept raw; older context rolled into a summary persisted in SQLite.
- **Frameless window** with light/dark theme, file sidebar, and save-to-PDF overlay.

## WebSocket

- Connect at `ws://localhost:8000/ws/{session_id}`.
- Browser commands flow as `browser_command` messages and return via `browser_result`.
