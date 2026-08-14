#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export RESOLUTION="${RESOLUTION:-1440x900x24}"
export VNC_PORT="${VNC_PORT:-5900}"
export NOVNC_PORT="${NOVNC_PORT:-6080}"

log() { echo "[entrypoint] $*"; }

# ── Virtual X server ─────────────────────────────────────────────────────
Xvfb "${DISPLAY}" -screen 0 "${RESOLUTION}" -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
log "Xvfb started on ${DISPLAY} (${RESOLUTION})"

sleep 1

# ── Minimal window manager (needed for sane window rendering) ────────────
fluxbox >/tmp/fluxbox.log 2>&1 &

# ── VNC server sharing the virtual display ───────────────────────────────
x11vnc -display "${DISPLAY}" -forever -shared -nopw -rfbport "${VNC_PORT}" \
    -bg -o /tmp/x11vnc.log 2>/dev/null || true
log "VNC server on port ${VNC_PORT}"

# ── noVNC web gateway ────────────────────────────────────────────────────
NOVNC_PROXY=""
if command -v novnc_proxy >/dev/null 2>&1; then
    NOVNC_PROXY="$(command -v novnc_proxy)"
elif [ -f /usr/share/novnc/utils/novnc_proxy ]; then
    NOVNC_PROXY="/usr/share/novnc/utils/novnc_proxy"
fi

if [ -n "${NOVNC_PROXY}" ]; then
    "${NOVNC_PROXY}" --vnc "localhost:${VNC_PORT}" --listen "${NOVNC_PORT}" >/tmp/novnc.log 2>&1 &
    log "noVNC web client: http://localhost:${NOVNC_PORT}/vnc.html"
else
    log "novnc_proxy not found — connect with a VNC client to port ${VNC_PORT}"
fi

sleep 2

log "Starting LazeeBrowse.ai (Electron)..."
cd /app/electron
exec "$@"
