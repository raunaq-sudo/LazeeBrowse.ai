# Contributing

Thanks for taking the time to contribute! LazeeBrowse.ai is a solo-built project opened up for the community — every kind of help is welcome: bug reports, feature ideas, docs, and code.

## Getting started

1. Fork the repository and create a branch from `main`:

   ```bash
   git checkout -b feature/my-change
   ```

2. Set up the project locally — see the [README](README.md#quick-start).

3. Make your change. Keep it focused; small PRs review faster.

4. Run the backend tests before pushing:

   ```bash
   cd fastapi-server
   source .venv/bin/activate
   pip install -r requirements.txt pytest
   python -m pytest tests/ -v
   ```

5. Open a pull request against `main`.

## Guidelines

- **Never commit secrets.** API keys belong in `.env` (gitignored) or the app's settings UI. If you find a leaked key, report it via [SECURITY.md](SECURITY.md) — do not post it in an issue.
- Follow the existing style. Backend uses plain Python with `from x import y` imports; frontend uses vanilla JS/Electron (no framework).
- Add a test when you fix a bug or add a meaningful feature.
- Update the README or docs if your change affects setup, configuration, or the WebSocket protocol.
- Use conventional, descriptive commit messages (e.g. `fix: handle empty session id`, `feat: add per-provider timeout`).

## Branch layout

The `main` branch is the source of truth. Older experimental branches (multi-session, RAG, subagents, etc.) exist for reference but are not maintained.

## Code of Conduct

All participants agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
