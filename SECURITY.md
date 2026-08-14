# Security Policy

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Email
**rsiraswar@gmail.com** with details instead.

Include, if possible:

- A short description of the vulnerability and its impact
- The affected component and version (commit SHA if known)
- Steps to reproduce or a proof-of-concept (sans live credentials)
- Any suggested fix

You will receive an acknowledgment within 3 business days and a status update
as the issue is triaged. Please give us reasonable time to fix the issue
before disclosing it publicly.

## Secrets and credentials

LazeeBrowse.ai deliberately keeps API keys out of the repository:

- `.env` files are gitignored; use `fastapi-server/.env.example` as a template.
- API keys are entered in the UI and stored in the local SQLite settings DB.
- Never commit keys, passwords, or personal account data.

If you believe a secret has been committed to this repository's history, treat
it as compromised and rotate it immediately, then report it per the policy
above.

## Threat model

This tool is an automation agent — it can run arbitrary JavaScript in the
user's browser, execute shell/agent tool calls, and read/write files. Anyone
running it assumes the associated risk. The threat model assumes a trusted
local user; do not expose the WebSocket server (`127.0.0.1:8000`) to untrusted
networks without adding authentication.
