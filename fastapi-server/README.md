# LazeeBrowse.ai — Backend

FastAPI/WebSocket server for LazeeBrowse.ai. The agent is embedded in the user's live Electron browser, driving it while researching and producing deliverables.

## Run

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py          # http://127.0.0.1:8000
```

## Endpoints

- `GET /health` — health check
- `GET /api/models` — available LLM models
- `WS /ws/{session_id}` — session WebSocket

See the [root README](../README.md) for the full API and setup instructions.
