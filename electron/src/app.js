// ─────────────────────────────────────────
//  Agent Chat — WebSocket Client
// ─────────────────────────────────────────

let ws = null;
let sessionId = null;
let isThinking = false;
let isFormInputRequired = false;
let formRequestId = null;
let isConnecting = false;

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
  const api_key = document.getElementById("llmApiKey").value.trim();
  const folderPath = document.getElementById("agentDir").value.trim();
  if (!serverRaw) return showError("Please enter a server URL.");

  // 🛑 Prevent duplicate connections
  if (ws) {
    if (ws.readyState === WebSocket.OPEN) {
      console.log("Already connected");
      return;
    }

    if (ws.readyState === WebSocket.CONNECTING) {
      console.log("Connection already in progress");
      return;
    }
  }

  if (isConnecting) return;
  isConnecting = true;

  const server = serverRaw.replace(/\/$/, "");
  sessionId = getSessionId();
  const url = `${server}/ws/${sessionId}`;

  document.getElementById("connectBtn").disabled = true;
  showError("");
  updateBadge("connecting", "Connecting…");

  try {
    ws = new WebSocket(url);
  } catch {
    isConnecting = false;
    showError("Invalid WebSocket URL.");
    document.getElementById("connectBtn").disabled = false;
    return;
  }

  ws.onopen = () => {
    isConnecting = false;
    updateBadge("connected", "Connected");
    ws.send(JSON.stringify({
      type:"llmApiAuth",
      api_key:api_key
    })
  )
    ws.send(JSON.stringify({
      type: "folderPath",
      folder_path:folderPath
    
    }))
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    handleServerMessage(data);
  };

  ws.onerror = () => {
    isConnecting = false;
    updateBadge("error", "Error");
    showError("Could not connect. Is the server running? Please Check you Api key.");
    document.getElementById("connectBtn").disabled = false;
  };

  ws.onclose = () => {
    isConnecting = false;
    console.log("WebSocket closed");
    updateBadge("", "Disconnected");
    setThinking(false);
    setInputEnabled(false);
    disconnect()
    // 🧠 Optional: auto-reconnect with delay (SAFE)
    // setTimeout(() => {
    //   console.log("Reconnecting...");
    //   connectToAgent();
    // }, 2000);
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
      setFormInputRequired(false, null);
      // Only render assistant messages here;
      // user messages are rendered optimistically on send
      if (data.role === "assistant") {
        appendMessage("assistant", data.content, data.timestamp);
      }
      break;
    
    case "form_input":
      setThinking(false);
      setFormInputRequired(true, data.request_id);
      // Only render assistant messages here;
      // user messages are rendered optimistically on send
      if (data.role === "assistant") {
        appendMessage("assistant", data.content, data.timestamp);
      }
      break;

    case "agent_thinking":
      setThinking(true);
      break;

    case "log":
      addLog(data.content);
      break;
    
    case "files":
      renderFiles(data.content);
      break;
    
    case "processing_request":
      disableSendBtn(true)
      break;
    
    case "processing_request_completed":
      disableSendBtn(false)
      break;

    
    case "pong":
      break;

    case "llmApiAuthFailed":
      showError("Invalid Api Key. Please check your Api key and try again.");
      ws = null
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
  const messageType = isFormInputRequired ? "form_response" : "message"
  if (formRequestId !== null) { 
    ws.send(JSON.stringify({ type: messageType, content, request_id: formRequestId }));
  }else{
    ws.send(JSON.stringify({ type: messageType, content }));
  }

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

function setFormInputRequired(required, request_id) {
  isFormInputRequired = required;
  formRequestId = request_id;

}

// -- Processing state

function disableSendBtn(bool){
  document.getElementById("sendBtn").disabled = bool;

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

function togglePanel(id) {
  const panel = document.getElementById(id);
  panel.classList.toggle("collapsed");
}

function addLog(message) {
  const logs = document.getElementById("logsContent");
  if (!logs) return;

  const line = document.createElement("div");
  line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  logs.appendChild(line);

  logs.scrollTop = logs.scrollHeight;
}

// function renderFiles(data) {
//   const container = document.getElementById("filesContent");
//   container.innerHTML = "";

//   if (!data || !data.files) return;

//   // STEP 1: Build tree from flat paths
//   const tree = {};

//   data.files.forEach(file => {
//     const parts = file.project_path.split("/"); // ["files", "folder", "a.txt"]
//     let current = tree;

//     parts.forEach((part, index) => {
//       if (!current[part]) {
//         current[part] = {
//           __children: {},
//           __isFile: index === parts.length - 1,
//           __path: file.path,
//           __project_path: file.project_path
//         };
//       }
//       current = current[part].__children;
//     });
//   });

//   // STEP 2: Render tree
//   function createNode(name, node) {
//     const wrapper = document.createElement("div");

//     const item = document.createElement("div");
//     item.textContent = name;
//     item.style.cursor = "pointer";

//     // Styling
//     item.style.padding = "2px 4px";
//     item.style.borderRadius = "4px";

//     if (node.__isFile) {
//       item.style.color = "#c96a2a"; // accent
//       item.onclick = async () => {
//         console.log(node)
//         const res = await window.electronAPI.openFile(node.__path);

//         if (!res.success) {
//           console.error("Open failed:", res.error);
//         }
//       };
//     } else {
//       item.style.fontWeight = "600";
//     }

//     wrapper.appendChild(item);

//     // Children (folder)
//     const childrenKeys = Object.keys(node.__children);
//     if (childrenKeys.length > 0) {
//       const childWrap = document.createElement("div");
//       childWrap.style.paddingLeft = "12px";
//       childWrap.style.display = "none";

//       item.onclick = () => {
//         childWrap.style.display =
//           childWrap.style.display === "none" ? "block" : "none";
//       };

//       childrenKeys.forEach(childName => {
//         childWrap.appendChild(
//           createNode(childName, node.__children[childName])
//         );
//       });

//       wrapper.appendChild(childWrap);
//     }

//     return wrapper;
//   }

//   // STEP 3: Render root
//   Object.keys(tree).forEach(rootKey => {
//     container.appendChild(createNode(rootKey, tree[rootKey]));
//   });
// }


function renderFiles(data) {
  const container = document.getElementById("filesContent");
  container.innerHTML = "";

  if (!data || !data.nodes) return;

  const tree = {};

  data.nodes.forEach(node => {
    const parts = node.project_path.split("/");
    let current = tree;

    parts.forEach((part, index) => {
      if (!current[part]) {
        current[part] = {
          __children: {},
          __type: index === parts.length - 1 ? node.type : "folder",
          __path: node.path
        };
      }
      current = current[part].__children;
    });
  });

  function createNode(name, node) {
    const wrapper = document.createElement("div");

    const item = document.createElement("div");
    item.style.cursor = "pointer";
    item.style.padding = "2px 4px";
    item.style.borderRadius = "4px";

    const isFile = node.__type === "file";

    item.textContent = isFile ? "📄 " + name : "📁 " + name;

    if (isFile) {
      item.style.color = "#c96a2a";

      item.onclick = async () => {
        await window.electronAPI.openFile(node.__path);
      };

    } else {
      item.style.fontWeight = "600";
    }

    wrapper.appendChild(item);

    const childrenKeys = Object.keys(node.__children);

    if (childrenKeys.length > 0) {
      const childWrap = document.createElement("div");
      childWrap.style.paddingLeft = "12px";
      childWrap.style.display = "none";

      item.onclick = () => {
        childWrap.style.display =
          childWrap.style.display === "none" ? "block" : "none";
      };

      childrenKeys.forEach(child =>
        childWrap.appendChild(createNode(child, node.__children[child]))
      );

      wrapper.appendChild(childWrap);
    }

    return wrapper;
  }

  Object.keys(tree).forEach(root =>
    container.appendChild(createNode(root, tree[root]))
  );
}