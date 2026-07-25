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

// ── SETTINGS PERSISTENCE ───────────────────────

function getRestBase() {
  const raw = document.getElementById("serverInput").value.trim().replace(/\/$/, "");
  return raw.replace(/^ws/, "http");
}

async function loadModels() {
  try {
    const base = getRestBase();
    const res = await fetch(`${base}/api/models`);
    if (!res.ok) return;
    const data = await res.json();
    const select = document.getElementById("modelName");
    select.innerHTML = "";
    (data.models || []).forEach(m => {
      const opt = document.createElement("option");
      opt.value = m.tag;
      opt.textContent = m.label;
      select.appendChild(opt);
    });
  } catch (e) {
    console.log("Could not load models:", e.message);
  }
}

async function loadSettings() {
  try {
    const base = getRestBase();
    const res = await fetch(`${base}/api/settings`);
    if (!res.ok) return;
    const data = await res.json();
    if (data.api_key) document.getElementById("llmApiKey").value = data.api_key;
    if (data.project_dir) document.getElementById("agentDir").value = data.project_dir;
    if (data.model_name) {
      const select = document.getElementById("modelName");
      if (select.querySelector(`option[value="${data.model_name}"]`)) {
        select.value = data.model_name;
      }
    }
    if (data.headless !== undefined) {
      document.getElementById("headlessToggle").checked = !data.headless;
    }
  } catch (e) {
    console.log("Could not load saved settings:", e.message);
  }
}

async function saveSettings(api_key, model_name, project_dir, headless) {
  try {
    const base = getRestBase();
    await fetch(`${base}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key, model_name, project_dir, headless }),
    });
  } catch (e) {
    console.log("Could not save settings:", e.message);
  }
}

// Load models and settings on startup
loadModels().then(() => loadSettings());

// ── CONNECTION ─────────────────────────────────


function connectToAgent() {
  const serverRaw = document.getElementById("serverInput").value.trim();
  const api_key = document.getElementById("llmApiKey").value.trim();
  const model_name = document.getElementById("modelName").value;
  const folderPath = document.getElementById("agentDir").value.trim();
  const headless = !document.getElementById("headlessToggle").checked;
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
      api_key:api_key,
      model_name:model_name
    })
  )
    ws.send(JSON.stringify({
      type: "folderPath",
      folder_path:folderPath
    
    }))

    ws.send(JSON.stringify({
      type: "headless",
      headless: headless
    }))

    saveSettings(api_key, model_name, folderPath, headless);
  };
  
  setFormInputRequired(false, null)

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
      // Render the appropriate UI based on input_type
      renderFormInput(data);
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

// ── FORM INPUT RENDERING ────────────────────────
function renderFormInput(data) {
  const area = document.getElementById("messagesArea");
  const empty = document.getElementById("emptyState");
  if (empty) empty.remove();

  const wrap = document.createElement("div");
  wrap.className = "msg-wrap assistant";

  const avatar = document.createElement("div");
  avatar.className = "msg-avatar-icon";
  avatar.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="9" stroke="currentColor" stroke-width="1.6"/>
    <path d="M9 12h6M12 9v6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
  </svg>`;
  wrap.appendChild(avatar);

  const bubble = document.createElement("div");
  bubble.className = "msg-bubble form-bubble";

  const text = document.createElement("div");
  text.className = "msg-text";
  text.textContent = data.content;
  bubble.appendChild(text);

  const inputType = data.input_type || "text";

  if (inputType === "confirmation") {
    const btnRow = document.createElement("div");
    btnRow.className = "form-btn-row";

    const yesBtn = document.createElement("button");
    yesBtn.className = "form-btn form-btn-yes";
    yesBtn.textContent = "Yes";
    yesBtn.onclick = () => submitFormResponse(data.request_id, "yes", wrap);

    const noBtn = document.createElement("button");
    noBtn.className = "form-btn form-btn-no";
    noBtn.textContent = "No";
    noBtn.onclick = () => submitFormResponse(data.request_id, "no", wrap);

    btnRow.appendChild(yesBtn);
    btnRow.appendChild(noBtn);
    bubble.appendChild(btnRow);

  } else if (inputType === "options") {
    const optList = document.createElement("div");
    optList.className = "form-options";

    (data.options || []).forEach((opt, i) => {
      const optBtn = document.createElement("button");
      optBtn.className = "form-option-btn";
      optBtn.textContent = opt;
      optBtn.onclick = () => submitFormResponse(data.request_id, opt, wrap);
      optList.appendChild(optBtn);
    });
    bubble.appendChild(optList);

  } else if (inputType === "form") {
    const form = document.createElement("div");
    form.className = "form-fields";

    (data.fields || []).forEach((field, i) => {
      const group = document.createElement("div");
      group.className = "form-field-group";

      const label = document.createElement("label");
      label.className = "form-field-label";
      label.textContent = field.label;
      group.appendChild(label);

      const input = document.createElement("input");
      input.type = "text";
      input.className = "form-field-input";
      input.placeholder = field.placeholder || "";
      input.value = field.value || "";
      input.dataset.index = i;
      group.appendChild(input);

      form.appendChild(group);
    });

    const submitRow = document.createElement("div");
    submitRow.className = "form-btn-row";

    const submitBtn = document.createElement("button");
    submitBtn.className = "form-btn form-btn-submit";
    submitBtn.textContent = "Submit";
    submitBtn.onclick = () => {
      const inputs = form.querySelectorAll(".form-field-input");
      const values = Array.from(inputs).map(inp => inp.value);
      submitFormResponse(data.request_id, JSON.stringify(values), wrap);
    };

    submitRow.appendChild(submitBtn);
    form.appendChild(submitRow);
    bubble.appendChild(form);

  } else {
    // Free text — keep existing behavior (user types in main input)
  }

  const time = document.createElement("div");
  time.className = "msg-time";
  const ts = data.timestamp ? new Date(data.timestamp) : new Date();
  time.textContent = ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  bubble.appendChild(time);

  wrap.appendChild(bubble);
  area.appendChild(wrap);
  scrollToBottom();
}

function submitFormResponse(requestId, content, msgWrap) {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;

  // Render the user's response as a message
  appendMessage("user", content, new Date().toISOString());

  // Disable the form buttons
  const btns = msgWrap.querySelectorAll("button");
  btns.forEach(btn => {
    btn.disabled = true;
    btn.classList.add("disabled");
  });

  // Send response
  ws.send(JSON.stringify({ type: "form_response", content, request_id: requestId }));

  // Reset form input state
  setFormInputRequired(false, null);
}

// ── SEND ───────────────────────────────────────
async function sendMessage() {
  const input = document.getElementById("messageInput");
  const content = input.value.trim();
  if ((!content && !pendingAttachments.length) || !ws || ws.readyState !== WebSocket.OPEN || isThinking) return;

  // Send attachments first
  if (pendingAttachments.length) {
    await sendAttachments();
  }

  if (!content) return;

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

// ── FILE ATTACHMENTS ────────────────────────────
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const ALLOWED_EXTENSIONS = [
  "pdf","txt","csv","json","xml","html","md",
  "doc","docx","xls","xlsx","ppt","pptx",
  "log","yaml","yml","toml","cfg","conf","ini"
];
let pendingAttachments = [];

function handleFileSelect(event) {
  const files = Array.from(event.target.files);
  if (!files.length) return;

  files.forEach(file => {
    const ext = file.name.split(".").pop().toLowerCase();
    if (!ALLOWED_EXTENSIONS.includes(ext)) {
      addLog(`Skipped "${file.name}": file type not allowed`);
      return;
    }
    if (file.size > MAX_FILE_SIZE) {
      addLog(`Skipped "${file.name}": exceeds 10MB limit`);
      return;
    }
    pendingAttachments.push(file);
  });

  renderAttachmentBar();
  event.target.value = "";
}

function renderAttachmentBar() {
  const bar = document.getElementById("attachmentBar");
  bar.innerHTML = "";

  if (!pendingAttachments.length) {
    bar.classList.remove("visible");
    return;
  }
  bar.classList.add("visible");

  pendingAttachments.forEach((file, i) => {
    const chip = document.createElement("span");
    chip.className = "attachment-chip";
    chip.textContent = file.name;
    const removeBtn = document.createElement("button");
    removeBtn.className = "attachment-remove";
    removeBtn.innerHTML = "&#x2715;";
    removeBtn.onclick = () => {
      pendingAttachments.splice(i, 1);
      renderAttachmentBar();
    };
    chip.appendChild(removeBtn);
    bar.appendChild(chip);
  });
}

function removeAttachment(index) {
  pendingAttachments.splice(index, 1);
  renderAttachmentBar();
}

async function sendAttachments() {
  if (!pendingAttachments.length || !ws || ws.readyState !== WebSocket.OPEN) return;

  for (const file of pendingAttachments) {
    const base64 = await readFileAsBase64(file);
    ws.send(JSON.stringify({
      type: "file_upload",
      filename: file.name,
      size: file.size,
      mime: file.type || "application/octet-stream",
      data: base64
    }));
    addLog(`Uploaded: ${file.name} (${formatFileSize(file.size)})`);
  }

  pendingAttachments = [];
  renderAttachmentBar();
}

function readFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result.split(",")[1]);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function formatFileSize(bytes) {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}