# ─────────────────────────────────────────────────────────────────────────────
#  LazeeBrowse.ai — full desktop container
#
#  Runs the FastAPI backend (spawned automatically by the Electron main
#  process) plus the Electron UI inside a virtual display, exposed over VNC:
#
#    * noVNC web client  →  http://localhost:6080/vnc.html
#    * any VNC client    →  localhost:5900
#
#  Backend-only image: fastapi-server/Dockerfile
# ─────────────────────────────────────────────────────────────────────────────

FROM mcr.microsoft.com/playwright/python:v1.58.0-noble

USER root

# ── System packages: VNC/noVNC desktop, venv support, misc tooling ──────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        xvfb \
        x11vnc \
        fluxbox \
        novnc \
        websockify \
        python3.12-venv \
        pandoc \
    && rm -rf /var/lib/apt/lists/*

# ── Electron runtime libraries ───────────────────────────────────────────────
# The playwright base image already ships most Chromium deps; install any that
# are missing. Unknown package names (distro renames such as libasound2t64)
# are skipped harmlessly.
RUN apt-get update && for p in \
        libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libgbm1 libpango-1.0-0 libcairo2 libxshmfence1 libgtk-3-0 \
        libx11-xcb1 libxcursor1 libxtst6 \
        libasound2 libasound2t64; do \
            apt-get install -y --no-install-recommends "$p" >/dev/null 2>&1 || true; \
    done \
    && rm -rf /var/lib/apt/lists/*

# ── Node.js (for the Electron frontend) ──────────────────────────────────────
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python backend ────────────────────────────────────────────────────────────
# The Electron main process spawns the backend from
# ../fastapi-server/.venv/bin/python, so the venv must live at that path.
COPY fastapi-server/ ./fastapi-server/
RUN python3 -m venv /app/fastapi-server/.venv \
    && /app/fastapi-server/.venv/bin/pip install --no-cache-dir --upgrade pip \
    && /app/fastapi-server/.venv/bin/pip install --no-cache-dir -r /app/fastapi-server/requirements.txt

# ── Electron frontend ────────────────────────────────────────────────────────
COPY electron/package.json electron/package-lock.json ./electron/
RUN npm ci --prefix ./electron
COPY electron/src ./electron/src
COPY electron/assets ./electron/assets

# ── Entrypoint ────────────────────────────────────────────────────────────────
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENV DISPLAY=:99
ENV RESOLUTION=1440x900x24
ENV VNC_PORT=5900
ENV NOVNC_PORT=6080

EXPOSE 5900 6080 8000

WORKDIR /app/electron
CMD ["./node_modules/.bin/electron", ".", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
