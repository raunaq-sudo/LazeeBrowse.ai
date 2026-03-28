// ─────────────────────────────────────────
//  Agent Chat — WebSocket Client
// ─────────────────────────────────────────

let ws = null;
let sessionId = null;
let isThinking = false;

// Generate or retrieve a persistent session ID
function getSessionId() {
  let id = localStorage.getItem("agent_session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("agent_session_id", id);
  }
  return id;
}

// ── CONNECTION ─────────────────────────────────
function connectToAgent() {
  const serverRaw = document.getElementById("serverInput").value.trim();
  if (!serverRaw) return showError("Please enter a server URL.");

  const server = serverRaw.replace(/\/$/, "");
  sessionId = getSessionId();
  const url = `${server}/ws/${sessionId}`;

  document.getElementById("connectBtn").disabled = true;
  showError("");
  updateBadge("connecting", "Connecting…");

  try {
    ws = new WebSocket(url);
  } catch {
    showError("Invalid WebSocket URL.");
    document.getElementById("connectBtn").disabled = false;
    return;
  }

  ws.onopen = () => updateBadge("connected", "Connected");

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleServerMessage(data);
  };

  ws.onerror = () => {
    updateBadge("error", "Error");
    showError("Could not connect. Is the server running?");
    document.getElementById("connectBtn").disabled = false;
  };

  ws.onclose = () => {
    updateBadge("", "Disconnected");
    setThinking(false);
    setInputEnabled(false);
  };
}

function handleServerMessage(data) {
  switch (data.type) {
    case "system":
      if (data.event === "connected") {
        switchToChat();
        updateBadge("connected", "Connected");
      } else if (data.event === "history_cleared") {
        clearMessages();
      }
      break;

    case "message":
      setThinking(false);
      // Only render assistant messages here;
      // user messages are rendered optimistically on send
      if (data.role === "assistant") {
        appendMessage("assistant", data.content, data.timestamp);
      }
      break;

    case "agent_thinking":
      setThinking(true);
      break;

    case "pong":
      break;
  }
}

// ── SCREEN SWITCH ──────────────────────────────
function switchToChat() {
  document.getElementById("connectScreen").classList.add("hidden");
  document.getElementById("chatScreen").classList.remove("hidden");
  setInputEnabled(true);
  document.getElementById("messageInput").focus();
}

function disconnect() {
  if (ws) { ws.close(); ws = null; }
  setThinking(false);
  document.getElementById("chatScreen").classList.add("hidden");
  document.getElementById("connectScreen").classList.remove("hidden");
  document.getElementById("connectBtn").disabled = false;
  updateBadge("", "Disconnected");
}

// ── MESSAGES ───────────────────────────────────
function appendMessage(role, content, timestamp) {
  const area = document.getElementById("messagesArea");

  // Hide empty state once first message arrives
  const empty = document.getElementById("emptyState");
  if (empty) empty.remove();

  const wrap = document.createElement("div");
  wrap.className = `msg-wrap ${role}`;

  if (role === "assistant") {
    const avatar = document.createElement("div");
    avatar.className = "msg-avatar-icon";
    avatar.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/>
      <path d="M9 12h6M12 9v6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
    </svg>`;
    wrap.appendChild(avatar);
  }

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble";

  const text = document.createElement("div");
  text.className = "msg-text";
  text.textContent = content;

  const time = document.createElement("div");
  time.className = "msg-time";
  const ts = timestamp ? new Date(timestamp) : new Date();
  time.textContent = ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

  bubble.appendChild(text);
  bubble.appendChild(time);
  wrap.appendChild(bubble);
  area.appendChild(wrap);

  scrollToBottom();
}

function clearMessages() {
  const area = document.getElementById("messagesArea");
  area.innerHTML = `
    <div class="empty-state" id="emptyState">
      <div class="empty-icon">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none">
          <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1"/>
          <path d="M9 12h6M12 9v6" stroke="currentColor" stroke-width="1" stroke-linecap="round"/>
        </svg>
      </div>
      <p class="empty-title">Conversation cleared</p>
      <p class="empty-sub">Send a message to start fresh.</p>
    </div>`;
}

function scrollToBottom() {
  const area = document.getElementById("messagesArea");
  area.scrollTop = area.scrollHeight;
}

// ── SEND ───────────────────────────────────────
function sendMessage() {
  const input = document.getElementById("messageInput");
  const content = input.value.trim();
  if (!content || !ws || ws.readyState !== WebSocket.OPEN || isThinking) return;

  // Render user message immediately
  appendMessage("user", content, new Date().toISOString());

  ws.send(JSON.stringify({ type: "message", content }));

  input.value = "";
  input.style.height = "auto";
  document.getElementById("charCount").textContent = "";
  input.focus();
}

function handleKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

function handleInput() {
  const input = document.getElementById("messageInput");

  // Auto-resize textarea
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 160) + "px";

  // Char count
  const len = input.value.length;
  document.getElementById("charCount").textContent = len > 3500 ? `${len}/4000` : "";
}

// ── CLEAR HISTORY ──────────────────────────────
function clearHistory() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "clear_history" }));
}

// ── THINKING STATE ─────────────────────────────
function setThinking(thinking) {
  isThinking = thinking;
  const bar = document.getElementById("thinkingBar");
  const status = document.getElementById("agentStatus");
  const sendBtn = document.getElementById("sendBtn");

  bar.classList.toggle("visible", thinking);
  status.textContent = thinking ? "Thinking…" : "Ready";
  status.classList.toggle("thinking", thinking);
  sendBtn.disabled = thinking;

  if (thinking) scrollToBottom();
}

// ── UI HELPERS ─────────────────────────────────
function setInputEnabled(enabled) {
  document.getElementById("messageInput").disabled = !enabled;
  document.getElementById("sendBtn").disabled = !enabled;
  document.getElementById("clearBtn").disabled = !enabled;
}

function updateBadge(state, text) {
  const badge = document.getElementById("serverBadge");
  badge.className = "server-badge " + state;
  badge.querySelector(".badge-text").textContent = text;
}

function showError(msg) {
  document.getElementById("connectError").textContent = msg;
}

// ── HEARTBEAT ─────────────────────────────────
setInterval(() => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "ping" }));
  }
}, 30000);