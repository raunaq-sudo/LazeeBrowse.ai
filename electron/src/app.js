// ─────────────────────────────────────────
//  AI Browser — WebSocket Client
// ─────────────────────────────────────────

let ws = null;
let sessionId = null;
let isThinking = false;
let isConnecting = false;
let browserView = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
const MAX_RECONNECT_ATTEMPTS = 10;
const BASE_RECONNECT_DELAY = 1000;

// ── SESSION ID ──────────────────────────────────
function getSessionId() {
  let id = localStorage.getItem("ai_browser_session_id");
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("ai_browser_session_id", id);
  }
  return id;
}

// ── SETTINGS ────────────────────────────────────
function getRestBase() {
  const raw = document.getElementById("serverInput").value.trim().replace(/\/$/, "");
  return raw.replace(/^ws/, "http");
}

let savedProjectDir = "";

async function selectFolder() {
  const folder = await window.electronAPI.selectFolder();
  if (folder) {
    document.getElementById("projectDir").value = folder;
    savedProjectDir = folder;
  }
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
    if (data.model_name) {
      const select = document.getElementById("modelName");
      if (select.querySelector(`option[value="${data.model_name}"]`)) {
        select.value = data.model_name;
      }
    }
    if (data.project_dir) {
      document.getElementById("projectDir").value = data.project_dir;
      savedProjectDir = data.project_dir;
    }
  } catch (e) {
    console.log("Could not load saved settings:", e.message);
  }
}

async function saveSettings(api_key, model_name, project_dir) {
  try {
    const base = getRestBase();
    await fetch(`${base}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ api_key, model_name, project_dir }),
    });
  } catch (e) {
    console.log("Could not save settings:", e.message);
  }
}

loadModels().then(() => loadSettings());

// ── WEBVIEW SETUP ───────────────────────────────
function getBrowserView() {
  if (!browserView) {
    browserView = document.getElementById("browserView");
  }
  return browserView;
}

async function webviewExecute(js) {
  const wv = getBrowserView();
  if (!wv) return { error: "Webview not initialized" };
  try {
    return await wv.executeJavaScript(js);
  } catch (e) {
    return { error: e.message };
  }
}

// ── JS ESCAPE HELPER ─────────────────────────────
function escapeJsString(str) {
  if (typeof str !== "string") return "";
  return str
    .replace(/\\/g, "\\\\")
    .replace(/'/g, "\\'")
    .replace(/"/g, '\\"')
    .replace(/\n/g, "\\n")
    .replace(/\r/g, "\\r")
    .replace(/\t/g, "\\t")
    .replace(/</g, "\\x3c")
    .replace(/>/g, "\\x3e");
}

// ── CONNECTION ──────────────────────────────────
let projectDirPath = "";

function connectToAgent() {
  const serverRaw = document.getElementById("serverInput").value.trim();
  const api_key = document.getElementById("llmApiKey").value.trim();
  const model_name = document.getElementById("modelName").value;
  const project_dir = document.getElementById("projectDir").value.trim();
  if (!serverRaw) return showError("Please enter a server URL.");
  if (!project_dir) return showError("Please select a project directory.");

  if (ws) {
    if (ws.readyState === WebSocket.OPEN) return;
    if (ws.readyState === WebSocket.CONNECTING) return;
  }
  if (isConnecting) return;
  isConnecting = true;

  const server = serverRaw.replace(/\/$/, "");
  sessionId = getSessionId();
  const url = `${server}/ws/${sessionId}`;

  document.getElementById("connectBtn").disabled = true;
  showError("");
  updateBadge("connecting", "Connecting...");

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
    reconnectAttempts = 0;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    updateBadge("connected", "Connected");

    const project_dir = document.getElementById("projectDir").value.trim();
    const folder_path = project_dir || savedProjectDir;

    // Send auth
    ws.send(JSON.stringify({
      type: "llmApiAuth",
      api_key: api_key,
      model_name: model_name,
    }));

    // Tell backend this is a browser-control session
    ws.send(JSON.stringify({
      type: "session_mode",
      mode: "browser_control",
    }));

    // Send project directory
    if (folder_path) {
      ws.send(JSON.stringify({
        type: "folderPath",
        folder_path: folder_path,
      }));
    }

    saveSettings(api_key, model_name, folder_path);
    projectDirPath = folder_path;
    hideConnectOverlay();
    loadFileTree().then(() => updateSidebarTogglePosition());
    startHeartbeat();
  };

  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      handleServerMessage(data);
    } catch (e) {
      console.error("Failed to parse WebSocket message:", e);
    }
  };

  ws.onerror = () => {
    isConnecting = false;
    updateBadge("error", "Error");
    showError("Could not connect. Is the server running?");
    document.getElementById("connectBtn").disabled = false;
  };

  ws.onclose = () => {
    isConnecting = false;
    stopHeartbeat();
    updateBadge("", "Disconnected");
    setThinking(false);
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      const delay = BASE_RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
      reconnectAttempts++;
      updateBadge("connecting", `Reconnecting (${reconnectAttempts})...`);
      reconnectTimer = setTimeout(() => connectToAgent(), delay);
    } else {
      showConnectOverlay();
    }
  };
}

// ── MESSAGE HANDLER ─────────────────────────────
function handleServerMessage(data) {
  switch (data.type) {
    case "system":
      if (data.event === "connected") {
        updateBadge("connected", "Connected");
      }
      break;

    case "agent_thinking":
      setThinking(true);
      break;

    case "log":
      addLog(data.content);
      break;

    case "browser_command":
      handleBrowserCommand(data);
      break;

    case "message":
      setThinking(false);
      addLog(`AI: ${data.content}`);
      expandLogPanel();
      break;

    case "form_input":
      handleFormInput(data);
      break;

    case "pong":
      break;

    case "llmApiAuthFailed":
      showError("Invalid API Key.");
      isConnecting = false;
      document.getElementById("connectBtn").disabled = false;
      break;

    case "error":
      addLog(`Error: ${data.content}`);
      setThinking(false);
      expandLogPanel();
      break;
  }
}

// ── BROWSER COMMAND HANDLER (webview) ───────────
async function handleBrowserCommand(data) {
  const { command, params, request_id } = data;
  let result;

  try {
    switch (command) {
      case "navigate": {
        const wv = getBrowserView();
        wv.src = params.url;
        await new Promise((resolve) => {
          wv.addEventListener("did-finish-load", resolve, { once: true });
          setTimeout(resolve, 15000);
        });
        result = { ok: true, url: wv.getURL() };
        break;
      }
      case "get_url":
        result = getBrowserView().getURL();
        break;
      case "get_title":
        result = getBrowserView().getTitle();
        break;
      case "click":
        result = await webviewExecute(`
          (() => {
            const el = document.querySelector('${escapeJsString(params.selector)}');
            if (!el) return { error: 'Element not found: ${escapeJsString(params.selector)}' };
            el.scrollIntoView({ behavior: 'smooth', block: 'center' });
            el.click();
            return { ok: true };
          })()
        `);
        break;
      case "type":
        result = await webviewExecute(`
          (() => {
            const el = document.querySelector('${escapeJsString(params.selector)}');
            if (!el) return { error: 'Element not found: ${escapeJsString(params.selector)}' };
            el.focus();
            el.value = '${escapeJsString(params.text)}';
            el.dispatchEvent(new Event('input', { bubbles: true }));
            el.dispatchEvent(new Event('change', { bubbles: true }));
            return { ok: true };
          })()
        `);
        break;
      case "scroll":
        result = await webviewExecute(`window.scrollBy(0, ${params.amount})`);
        result = { ok: true };
        break;
      case "get_text":
        result = await webviewExecute(`
          (() => {
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script, style, noscript').forEach(el => el.remove());
            return clone.innerText;
          })()
        `);
        break;
      case "get_links":
        result = await webviewExecute(`
          Array.from(document.querySelectorAll('a[href]')).map(a => ({
            text: a.innerText.trim().slice(0, 100),
            href: a.href
          })).filter(a => a.href && a.href.startsWith('http'))
        `);
        break;
      case "get_headings":
        result = await webviewExecute(`
          Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6'))
            .map(h => ({ tag: h.tagName.toLowerCase(), text: h.innerText.trim() }))
        `);
        break;
      case "get_schema":
        result = await webviewExecute(`
          (() => {
            const mode = '${params.mode || 'visible'}';
            const elements = document.querySelectorAll('input, textarea, select, button, a[href]');
            return Array.from(elements).map(el => {
              const rect = el.getBoundingClientRect();
              const isVisible = rect.width > 0 && rect.height > 0 &&
                window.getComputedStyle(el).visibility !== 'hidden' &&
                window.getComputedStyle(el).display !== 'none';
              if (mode !== 'full' && !isVisible) return null;
              let selector = '';
              if (el.id) selector = '#' + el.id;
              else if (el.name) selector = '[name="' + el.name + '"]';
              else {
                let path = [];
                let current = el;
                while (current && current !== document.body) {
                  let seg = current.tagName.toLowerCase();
                  if (current.id) { seg = '#' + current.id; path.unshift(seg); break; }
                  if (current.className && typeof current.className === 'string') {
                    const cls = current.className.split(/\\s+/).filter(Boolean).slice(0, 2).join('.');
                    if (cls) seg += '.' + cls;
                  }
                  path.unshift(seg);
                  current = current.parentElement;
                }
                selector = path.join(' > ');
              }
              return {
                tag: el.tagName.toLowerCase(),
                selector: selector,
                text: (el.innerText || el.placeholder || '').trim().slice(0, 100),
                type: el.type || null,
                href: el.href || null,
                visible: isVisible,
                rect: { x: rect.x, y: rect.y, w: rect.width, h: rect.height }
              };
            }).filter(Boolean);
          })()
        `);
        break;
      case "get_page_content":
        result = await webviewExecute(`
          (() => {
            const clone = document.body.cloneNode(true);
            clone.querySelectorAll('script, style, noscript, nav, footer, aside').forEach(el => el.remove());
            return clone.innerHTML;
          })()
        `);
        break;
      case "submit_form":
        result = await webviewExecute(`
          (() => {
            const active = document.activeElement;
            if (active && active.form) { active.form.submit(); return { ok: true }; }
            const event = new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, bubbles: true });
            document.activeElement.dispatchEvent(event);
            return { ok: true };
          })()
        `);
        break;
      case "press_key":
        result = await webviewExecute(`
          (() => {
            const keyMap = {
              'Enter': 13, 'Tab': 9, 'Escape': 27, 'Backspace': 8, 'Delete': 46,
              'ArrowUp': 38, 'ArrowDown': 40, 'ArrowLeft': 37, 'ArrowRight': 39,
              ' ': 32, 'Home': 36, 'End': 35, 'PageUp': 33, 'PageDown': 34
            };
            const keyCode = keyMap['${escapeJsString(params.key)}'] || 0;
            const event = new KeyboardEvent('keydown', {
              key: '${escapeJsString(params.key)}',
              code: '${escapeJsString(params.key)}',
              keyCode: keyCode,
              bubbles: true
            });
            document.activeElement.dispatchEvent(event);
            return { ok: true };
          })()
        `);
        break;
      case "go_back":
        getBrowserView().goBack();
        result = { ok: true };
        break;
      case "go_forward":
        getBrowserView().goForward();
        result = { ok: true };
        break;
      case "screenshot":
        result = { error: "Screenshot not supported in webview mode" };
        break;
      default:
        result = { error: `Unknown command: ${command}` };
    }
  } catch (e) {
    result = { error: e.message };
  }

  // Send result back to backend
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "browser_result",
      request_id: request_id,
      result: result,
    }));
  }
}

// ── URL BAR ─────────────────────────────────────
document.getElementById("urlInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    const url = e.target.value.trim();
    if (url) {
      getBrowserView().src = url;
    }
  }
});

// ── NAV BUTTONS ─────────────────────────────────
document.getElementById("backBtn").addEventListener("click", () => {
  getBrowserView().goBack();
});

document.getElementById("forwardBtn").addEventListener("click", () => {
  getBrowserView().goForward();
});

document.getElementById("refreshBtn").addEventListener("click", () => {
  getBrowserView().reload();
});

// ── INSTRUCTION INPUT ───────────────────────────
document.getElementById("instructionInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendInstruction();
  }
});

document.getElementById("instructionInput").addEventListener("input", (e) => {
  const input = e.target;
  input.style.height = "auto";
  input.style.height = Math.min(input.scrollHeight, 80) + "px";
  const len = input.value.length;
  document.getElementById("charCount").textContent = len > 1800 ? `${len}/2000` : "";
});

async function sendInstruction() {
  const input = document.getElementById("instructionInput");
  const content = input.value.trim();
  if (!content || !ws || ws.readyState !== WebSocket.OPEN || isThinking) return;

  const filesToSend = [...attachedFiles];
  addLog(`You: ${content}${filesToSend.length ? ` [${filesToSend.length} file(s) attached]` : ""}`);
  ws.send(JSON.stringify({ type: "message", content, attached_files: filesToSend }));

  input.value = "";
  input.style.height = "auto";
  document.getElementById("charCount").textContent = "";
  attachedFiles = [];
  renderAttachedFiles();
}

// ── UI HELPERS ──────────────────────────────────
function setThinking(thinking) {
  isThinking = thinking;
  const bar = document.getElementById("thinkingBar");
  const status = document.getElementById("agentStatus");
  const sendBtn = document.getElementById("sendBtn");

  bar.classList.toggle("visible", thinking);
  status.textContent = thinking ? "AI is working..." : "Ready";
  status.classList.toggle("thinking", thinking);
  sendBtn.disabled = thinking;
}

function updateBadge(state, text) {
  const badge = document.getElementById("serverBadge");
  badge.className = "server-badge " + state;
  badge.querySelector(".badge-text").textContent = text;
}

function showError(msg) {
  document.getElementById("connectError").textContent = msg;
}

// ── FORM INPUT MODAL ─────────────────────────────
let currentFormRequest = null;

function handleFormInput(data) {
  const { request_id, content, input_type, options, fields } = data;
  currentFormRequest = { request_id, input_type };

  const overlay = document.getElementById("formModal");
  const header = document.getElementById("formModalHeader");
  const body = document.getElementById("formModalBody");
  const submitBtn = document.getElementById("formModalSubmit");
  const cancelBtn = document.getElementById("formModalCancel");

  header.textContent = content || "AI needs input";
  body.innerHTML = "";

  if (input_type === "confirmation") {
    body.innerHTML = `
      <div class="confirm-btns">
        <button class="yes-btn" onclick="submitFormResponse('yes')">Yes</button>
        <button class="no-btn" onclick="submitFormResponse('no')">No</button>
      </div>
    `;
    submitBtn.classList.add("hidden");
    cancelBtn.classList.add("hidden");
  } else if (input_type === "options" && options && options.length > 0) {
    options.forEach((opt, idx) => {
      const btn = document.createElement("button");
      btn.className = "option-btn";
      btn.textContent = `${idx + 1}. ${opt}`;
      btn.onclick = () => submitFormResponse(opt);
      body.appendChild(btn);
    });
    submitBtn.classList.add("hidden");
    cancelBtn.classList.remove("hidden");
  } else if (input_type === "form" && fields && fields.length > 0) {
    fields.forEach((field, idx) => {
      const label = document.createElement("label");
      label.style.display = "block";
      label.style.fontSize = "10px";
      label.style.fontWeight = "600";
      label.style.color = "var(--text-secondary)";
      label.style.marginBottom = "4px";
      label.textContent = field.label || field.placeholder || `Field ${idx + 1}`;
      body.appendChild(label);

      const input = document.createElement("input");
      input.type = "text";
      input.className = "form-field-input";
      input.dataset.index = idx;
      input.placeholder = field.placeholder || "";
      input.value = field.value || "";
      body.appendChild(input);
    });
    submitBtn.classList.remove("hidden");
    cancelBtn.classList.remove("hidden");
  } else {
    const input = document.createElement("input");
    input.type = "text";
    input.id = "formModalTextInput";
    input.placeholder = "Type your response...";
    body.appendChild(input);
    submitBtn.classList.remove("hidden");
    cancelBtn.classList.remove("hidden");
    setTimeout(() => input.focus(), 50);
  }

  submitBtn.onclick = () => {
    if (input_type === "form") {
      const inputs = body.querySelectorAll(".form-field-input");
      const values = Array.from(inputs).map(i => i.value);
      submitFormResponse(JSON.stringify(values));
    } else {
      const input = body.querySelector("#formModalTextInput");
      submitFormResponse(input ? input.value : "");
    }
  };

  cancelBtn.onclick = () => submitFormResponse("");

  overlay.classList.remove("hidden");
}

function submitFormResponse(response) {
  if (!currentFormRequest) return;
  const { request_id } = currentFormRequest;

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({
      type: "form_response",
      request_id: request_id,
      content: response,
    }));
  }

  document.getElementById("formModal").classList.add("hidden");
  currentFormRequest = null;
}

function hideConnectOverlay() {
  document.getElementById("connectOverlay").classList.add("hidden");
}

function showConnectOverlay() {
  document.getElementById("connectOverlay").classList.remove("hidden");
}

function toggleLogPanel() {
  const panel = document.getElementById("logPanel");
  const btn = document.getElementById("logToggle");
  const wasCollapsed = panel.classList.contains("collapsed");
  if (wasCollapsed) {
    panel.classList.remove("collapsed");
    panel.style.height = "";
    btn.textContent = "v";
  } else {
    panel.classList.add("collapsed");
    panel.style.height = "";
    btn.textContent = "^";
  }
}

function expandLogPanel() {
  const panel = document.getElementById("logPanel");
  const btn = document.getElementById("logToggle");
  panel.classList.remove("collapsed");
  panel.style.height = "50vh";
  btn.textContent = "v";
}

// ── LOG RESIZE HANDLE ──────────────────────────
(function initLogResize() {
  const handle = document.getElementById("logResizeHandle");
  const panel = document.getElementById("logPanel");
  if (!handle || !panel) return;

  let startY = 0;
  let startH = 0;
  let dragging = false;

  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    dragging = true;
    startY = e.clientY;
    startH = panel.getBoundingClientRect().height;
    handle.classList.add("active");
    document.body.style.cursor = "ns-resize";
    document.body.style.userSelect = "none";
  });

  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const delta = startY - e.clientY;
    const newH = Math.max(28, Math.min(window.innerHeight * 0.85, startH + delta));
    panel.style.height = newH + "px";
    panel.classList.remove("collapsed");
    document.getElementById("logToggle").textContent = "v";
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove("active");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
})();

function addLog(message) {
  const logs = document.getElementById("logContent");
  if (!logs) return;
  const line = document.createElement("div");
  line.className = "log-line";
  line.textContent = `[${new Date().toLocaleTimeString()}] ${message}`;
  logs.appendChild(line);
  logs.scrollTop = logs.scrollHeight;

  while (logs.children.length > 100) {
    logs.removeChild(logs.firstChild);
  }
}

// ── HEARTBEAT ──────────────────────────────────
let heartbeatInterval = null;

function startHeartbeat() {
  stopHeartbeat();
  heartbeatInterval = setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    } else {
      stopHeartbeat();
    }
  }, 30000);
}

function stopHeartbeat() {
  if (heartbeatInterval) {
    clearInterval(heartbeatInterval);
    heartbeatInterval = null;
  }
}

// ── FILE TREE ──────────────────────────────────
let fileTreeData = [];

async function loadFileTree() {
  if (!savedProjectDir) return;
  try {
    fileTreeData = await window.electronAPI.scanDirectory(savedProjectDir);
    renderFileTree();
  } catch (e) {
    console.log("Could not load file tree:", e.message);
  }
}

function renderFileTree() {
  const container = document.getElementById("fileTree");
  if (!container) return;
  container.innerHTML = "";
  if (fileTreeData.length === 0) {
    container.innerHTML = '<div class="tree-item" style="color:var(--text-muted);cursor:default">No files</div>';
    return;
  }
  fileTreeData.forEach(entry => renderTreeNode(container, entry, 0));
}

function renderTreeNode(parent, entry, depth) {
  const item = document.createElement("div");
  item.className = `tree-item ${entry.type}`;
  item.style.paddingLeft = (10 + depth * 12) + "px";

  const icon = document.createElement("span");
  icon.className = "tree-icon";
  icon.textContent = entry.type === "dir" ? "\u25B6" : getFileIcon(entry.name);

  const name = document.createElement("span");
  name.className = "tree-name";
  name.textContent = entry.name;
  name.title = entry.path;

  item.appendChild(icon);
  item.appendChild(name);
  parent.appendChild(item);

  if (entry.type === "file") {
    item.addEventListener("click", (e) => {
      e.stopPropagation();
      attachFileFromTree(entry);
    });
  }

  if (entry.type === "dir" && entry.children) {
    let expanded = false;
    const childContainer = document.createElement("div");
    childContainer.className = "tree-children";
    childContainer.style.display = "none";
    parent.appendChild(childContainer);

    entry.children.forEach(child => renderTreeNode(childContainer, child, depth + 1));

    item.addEventListener("click", (e) => {
      e.stopPropagation();
      expanded = !expanded;
      childContainer.style.display = expanded ? "block" : "none";
      icon.textContent = expanded ? "\u25BC" : "\u25B6";
    });
  }
}

function getFileIcon(name) {
  const ext = name.split(".").pop().toLowerCase();
  const icons = {
    js: "JS", ts: "TS", py: "PY", html: "<>", css: "#",
    json: "{}", md: "M", txt: "T", pdf: "PD",
    png: "I", jpg: "I", jpeg: "I", gif: "I", svg: "I",
    zip: "Z", tar: "Z", gz: "Z",
  };
  return icons[ext] || "\u25A1";
}

function attachFileFromTree(entry) {
  const relPath = entry.path;
  const name = entry.name;
  if (attachedFiles.some(f => f.path === relPath)) return;
  attachedFiles.push({ name, path: relPath });
  renderAttachedFiles();
}

// ── FILE ATTACHMENT ─────────────────────────────
let attachedFiles = [];

function renderAttachedFiles() {
  const bar = document.getElementById("attachedFilesBar");
  if (!bar) return;
  bar.innerHTML = "";
  bar.classList.toggle("has-files", attachedFiles.length > 0);

  attachedFiles.forEach((file, idx) => {
    const chip = document.createElement("div");
    chip.className = "attached-file-chip";

    const nameSpan = document.createElement("span");
    nameSpan.className = "chip-name";
    nameSpan.textContent = file.name;
    nameSpan.title = file.path;

    const removeBtn = document.createElement("button");
    removeBtn.className = "chip-remove";
    removeBtn.textContent = "\u00D7";
    removeBtn.addEventListener("click", () => {
      attachedFiles.splice(idx, 1);
      renderAttachedFiles();
    });

    chip.appendChild(nameSpan);
    chip.appendChild(removeBtn);
    bar.appendChild(chip);
  });
}

async function pickFilesForAttachment() {
  const files = await window.electronAPI.selectFiles(savedProjectDir || undefined);
  if (!files || files.length === 0) return;

  const base = savedProjectDir || "";
  files.forEach(fullPath => {
    let relPath = fullPath;
    if (base && fullPath.startsWith(base)) {
      relPath = fullPath.slice(base.length).replace(/^\//, "");
    }
    const name = fullPath.split("/").pop();
    if (!attachedFiles.some(f => f.path === relPath)) {
      attachedFiles.push({ name, path: relPath });
    }
  });
  renderAttachedFiles();
}

// ── SIDEBAR TOGGLE ─────────────────────────────
function toggleSidebar() {
  const sidebar = document.getElementById("fileSidebar");
  const btn = document.getElementById("sidebarToggle");
  const collapsed = sidebar.classList.toggle("collapsed");
  btn.classList.toggle("collapsed", collapsed);
  updateSidebarTogglePosition();
}

function updateSidebarTogglePosition() {
  const sidebar = document.getElementById("fileSidebar");
  const btn = document.getElementById("sidebarToggle");
  if (!sidebar || !btn) return;
  const w = sidebar.classList.contains("collapsed") ? 0 : sidebar.getBoundingClientRect().width;
  btn.style.left = w + "px";
}

// ── SIDEBAR RESIZE ─────────────────────────────
(function initSidebarResize() {
  const handle = document.getElementById("sidebarResizeHandle");
  const sidebar = document.getElementById("fileSidebar");
  if (!handle || !sidebar) return;

  let startX = 0;
  let startW = 0;
  let dragging = false;

  handle.addEventListener("mousedown", (e) => {
    e.preventDefault();
    dragging = true;
    startX = e.clientX;
    startW = sidebar.getBoundingClientRect().width;
    handle.classList.add("active");
    document.body.style.cursor = "ew-resize";
    document.body.style.userSelect = "none";
  });

  document.addEventListener("mousemove", (e) => {
    if (!dragging) return;
    const delta = e.clientX - startX;
    const newW = Math.max(0, Math.min(400, startW + delta));
    sidebar.style.width = newW + "px";
    if (newW > 0) sidebar.classList.remove("collapsed");
    updateSidebarTogglePosition();
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) return;
    dragging = false;
    handle.classList.remove("active");
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  });
})();
