// ─────────────────────────────────────────
//  LazeeBrowse.ai — WebSocket Client
// ─────────────────────────────────────────

let ws = null;
let sessionId = null;
let isThinking = false;
let isConnecting = false;
let telegramModeOn = false;
let browserView = null;
let reconnectAttempts = 0;
let reconnectTimer = null;
let deepDive = false;
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
  return "http://localhost:8000";
}

let savedProjectDir = "";

async function selectFolder() {
  const folder = await window.electronAPI.selectFolder();
  if (folder) {
    savedProjectDir = folder;
    updateProjectDisplay(folder);
  }
}

function updateProjectDisplay(path) {
  const nameEl = document.getElementById("projectName");
  const pathEl = document.getElementById("projectPath");
  if (path) {
    const name = path.split("/").pop() || path.split("\\").pop() || path;
    nameEl.textContent = name;
    pathEl.textContent = path;
    nameEl.classList.remove("project-name-empty");
  } else {
    nameEl.textContent = "Select a project folder";
    pathEl.textContent = "";
    nameEl.classList.add("project-name-empty");
  }
}

// ── RECENT PROJECTS ────────────────────────────
async function migrateRecentProjects() {
  try {
    const old = JSON.parse(localStorage.getItem("recentProjects") || "[]");
    if (!old.length) return;
    const base = getRestBase();
    for (const p of old) {
      await fetch(`${base}/api/recent-projects`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: p.path, name: p.name }),
      });
    }
    localStorage.removeItem("recentProjects");
  } catch {}
}

async function getRecentProjects() {
  try {
    const base = getRestBase();
    const res = await fetch(`${base}/api/recent-projects`);
    if (!res.ok) return [];
    const data = await res.json();
    return data.projects || [];
  } catch { return []; }
}

async function addRecentProject(path) {
  if (!path) return;
  const name = path.split("/").pop() || path.split("\\").pop() || path;
  try {
    const base = getRestBase();
    await fetch(`${base}/api/recent-projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path, name }),
    });
  } catch {}
  await renderRecentProjects();
}

async function removeRecentProject(path) {
  const confirmed = confirm("Delete this project permanently?\nThis will remove the project folder and all its contents.");
  if (!confirmed) return;
  try {
    const base = getRestBase();
    await fetch(`${base}/api/recent-projects`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path }),
    });
  } catch {}
  await renderRecentProjects();
}

async function renderRecentProjects() {
  const list = document.getElementById("recentProjectsList");
  const projects = await getRecentProjects();
  if (!projects.length) {
    list.innerHTML = '<div class="recent-project-empty">No recent projects</div>';
    return;
  }
  list.innerHTML = projects.map(p =>
    `<div class="recent-project" onclick="selectRecentProject('${p.path.replace(/'/g, "\\'")}')">
      <span class="recent-project-remove" onclick="event.stopPropagation(); removeRecentProject('${p.path.replace(/'/g, "\\'")}')">×</span>
      <div class="recent-project-name">${p.name}</div>
      <div class="recent-project-path">${p.path}</div>
    </div>`
  ).join("");
}

function selectRecentProject(path) {
  savedProjectDir = path;
  updateProjectDisplay(path);
  document.querySelectorAll(".recent-project").forEach(el => el.classList.remove("active"));
}

let modelProviderMap = {};

async function loadModels() {
  try {
    const base = getRestBase();
    const res = await fetch(`${base}/api/models`);
    if (!res.ok) return;
    const data = await res.json();
    const select = document.getElementById("modelName");
    select.innerHTML = "";
    modelProviderMap = {};
    (data.models || []).forEach(m => {
      modelProviderMap[m.tag] = m.provider;
      const opt = document.createElement("option");
      opt.value = m.tag;
      opt.textContent = m.label;
      select.appendChild(opt);
    });
    select.addEventListener("change", () => swapApiKeyForModel(select.value));
  } catch (e) {
    console.log("Could not load models:", e.message);
  }
}

function swapApiKeyForModel(modelTag) {
  const provider = modelProviderMap[modelTag] || "deepseek";
  const input = document.getElementById("llmApiKey");
  const prev = localStorage.getItem(`api_key_${provider}`) || "";
  input.value = prev;
  input.placeholder = `${provider.charAt(0).toUpperCase() + provider.slice(1)} API key`;
}

async function loadSettings() {
  try {
    const base = getRestBase();
    const res = await fetch(`${base}/api/settings`);
    if (!res.ok) return;
    const data = await res.json();
    const api_keys = data.api_keys || {};
    for (const [provider, key] of Object.entries(api_keys)) {
      if (key) localStorage.setItem(`api_key_${provider}`, key);
    }
    if (data.model_name) {
      const select = document.getElementById("modelName");
      if (select.querySelector(`option[value="${data.model_name}"]`)) {
        select.value = data.model_name;
      }
    }
    swapApiKeyForModel(document.getElementById("modelName").value);
    if (data.project_dir) {
      savedProjectDir = data.project_dir;
      updateProjectDisplay(data.project_dir);
    }
    const tg = document.getElementById("telegramToggle");
    if (tg) {
      tg.checked = data.telegram_mode === "on";
      updateTelegramTokenVisibility();
      applyTelegramChatDisable();
    }
    const tgToken = document.getElementById("telegramToken");
    if (tgToken && data.telegram_bot_token) {
      tgToken.value = data.telegram_bot_token;
      localStorage.setItem("telegram_bot_token", data.telegram_bot_token);
    }
  } catch (e) {
    console.log("Could not load saved settings:", e.message);
  }
}

function updateTelegramTokenVisibility() {
  const tg = document.getElementById("telegramToggle");
  const row = document.getElementById("telegramTokenRow");
  if (!tg || !row) return;
  row.classList.toggle("hidden", !tg.checked);
}

function applyTelegramChatDisable() {
  const tg = document.getElementById("telegramToggle");
  telegramModeOn = !!(tg && tg.checked);
  const input = document.getElementById("instructionInput");
  const attachBtn = document.getElementById("attachBtn");
  const diveBtn = document.getElementById("deepDiveBtn");
  const sendBtn = document.getElementById("sendBtn");
  const urlInput = document.getElementById("urlInput");
  [input, attachBtn, diveBtn, urlInput].forEach((el) => {
    if (el) el.disabled = telegramModeOn;
  });
  if (sendBtn && !isThinking) {
    sendBtn.disabled = telegramModeOn;
  }
}

async function saveTelegramSettings() {
  try {
    const base = getRestBase();
    const tg = document.getElementById("telegramToggle");
    const tgToken = document.getElementById("telegramToken");
    const mode = tg ? tg.checked : false;
    const token = tgToken ? tgToken.value.trim() : "";
    if (token) localStorage.setItem("telegram_bot_token", token);
    await fetch(`${base}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ telegram_mode: mode, telegram_bot_token: token }),
    });
  } catch (e) {
    console.log("Could not save telegram settings:", e.message);
  }
}

function initTelegramToggle() {
  const tg = document.getElementById("telegramToggle");
  if (!tg) return;
  const tgToken = document.getElementById("telegramToken");
  tg.addEventListener("change", () => {
    updateTelegramTokenVisibility();
    applyTelegramChatDisable();
    saveTelegramSettings();
  });
  if (tgToken) {
    tgToken.addEventListener("change", () => saveTelegramSettings());
  }
}

async function saveSettings(model_name, project_dir) {
  try {
    const base = getRestBase();
    const api_keys = {};
    for (const p of ["deepseek", "google", "anthropic", "openai", "openrouter"]) {
      const k = localStorage.getItem(`api_key_${p}`) || "";
      if (k) api_keys[p] = k;
    }
    const tg = document.getElementById("telegramToggle");
    const tgToken = document.getElementById("telegramToken");
    await fetch(`${base}/api/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        api_keys,
        model_name,
        project_dir,
        telegram_mode: tg ? tg.checked : false,
        telegram_bot_token: tgToken ? tgToken.value.trim() : "",
      }),
    });
  } catch (e) {
    console.log("Could not save settings:", e.message);
  }
}

loadModels().then(() => loadSettings());
initTelegramToggle();
migrateRecentProjects().then(() => renderRecentProjects());

// ── WEBVIEW SETUP ───────────────────────────────
function getBrowserView() {
  if (!browserView) {
    browserView = document.getElementById("browserView");
    if (browserView) {
      browserView.addEventListener("did-navigate", () => {
        try {
          const url = browserView.getURL();
          document.getElementById("urlInput").value = url;
        } catch (e) {}
      });
      browserView.addEventListener("did-navigate-in-page", () => {
        try {
          const url = browserView.getURL();
          document.getElementById("urlInput").value = url;
        } catch (e) {}
      });
    }
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

// ── SAVE OVERLAY (floating on the browser) ──────
function initSaveOverlay() {
  const btn = document.getElementById("saveOverlayBtn");
  const menu = document.getElementById("saveMenu");
  if (!btn || !menu) return;

  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    menu.classList.toggle("hidden");
  });

  document.addEventListener("click", (e) => {
    if (e.target !== btn && !menu.contains(e.target)) {
      menu.classList.add("hidden");
    }
  });

  const savePdfBtn = document.getElementById("savePdfBtn");
  if (savePdfBtn) {
    savePdfBtn.addEventListener("click", async () => {
      menu.classList.add("hidden");
      const wv = getBrowserView();
      if (!wv) {
        addLog("Save as PDF: browser not initialized");
        return;
      }
      try {
        const title = (wv.getTitle() || "page").replace(/[\\/:*?"<>|]/g, "_").slice(0, 80);
        addLog("Rendering current page to PDF...");
        const data = await wv.printToPDF({ printBackground: true, pageSize: "A4" });
        const res = await window.electronAPI.savePdf(new Uint8Array(data), title + ".pdf");
        if (res && res.success) {
          addLog("Saved PDF: " + res.path);
        } else if (res && res.canceled) {
          addLog("Save canceled");
        } else {
          addLog("Save as PDF failed: " + ((res && res.error) || "unknown error"));
        }
      } catch (e) {
        addLog("Save as PDF failed: " + e.message);
      }
    });
  }

  const savePptBtn = document.getElementById("savePptBtn");
  if (savePptBtn) {
    savePptBtn.addEventListener("click", () => {
      menu.classList.add("hidden");
      addLog("Save as PPT is coming soon.");
    });
  }
}

initSaveOverlay();

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
  const api_key = document.getElementById("llmApiKey").value.trim();
  const model_name = document.getElementById("modelName").value;
  const project_dir = savedProjectDir;
  const provider = modelProviderMap[model_name] || "deepseek";
  if (!project_dir) return showError("Please select a project directory.");

  if (api_key) localStorage.setItem(`api_key_${provider}`, api_key);

  if (ws) {
    if (ws.readyState === WebSocket.OPEN) return;
    if (ws.readyState === WebSocket.CONNECTING) return;
  }
  if (isConnecting) return;
  isConnecting = true;

  const server = "ws://localhost:8000";
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

    const folder_path = savedProjectDir;

    // Send auth
    ws.send(JSON.stringify({
      type: "llmApiAuth",
      api_key: api_key,
      model_name: model_name,
      provider: provider,
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

    saveSettings(model_name, folder_path);
    addRecentProject(folder_path);
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

    case "thinking_token":
      addThinkingToken(data.content);
      break;

    case "tool_call":
      addLog(`Tool: ${data.name}`);
      break;

    case "log":
      addLog(data.content);
      break;

    case "browser_command":
      handleBrowserCommand(data);
      break;

    case "message":
      setThinking(false);
      addResponseLog(data.content);
      expandLogPanel();
      break;

    case "tot_message":
      // Intermediate ToT report messages: render without clearing the
      // thinking/stop state — the run is still in progress.
      addResponseLog(data.content);
      expandLogPanel();
      break;

    case "user_input_request":
      handleUserInputRequest(data);
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
            el.scrollIntoView({ block: 'center' });
            el.focus();
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
            const text = '${escapeJsString(params.text)}';

            if (el.isContentEditable) {
              el.textContent = text;
              el.dispatchEvent(new InputEvent('input', { bubbles: true, data: text, inputType: 'insertText' }));
            } else {
              const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
              const nativeSetter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
              if (nativeSetter) {
                nativeSetter.call(el, text);
              } else {
                el.value = text;
              }
              el.dispatchEvent(new Event('input', { bubbles: true }));
              el.dispatchEvent(new Event('change', { bubbles: true }));
            }
            return { ok: true };
          })()
        `);
        break;
      case "scroll":
        result = await webviewExecute(`
          (() => {
            const amount = ${Number(params.amount) || 500};
            function isScrollable(el) {
              if (!el || el === document.body || el === document.documentElement) return false;
              const style = getComputedStyle(el);
              return (style.overflowY === 'auto' || style.overflowY === 'scroll')
                && el.scrollHeight > el.clientHeight;
            }
            let target = document.activeElement;
            while (target && !isScrollable(target)) {
              target = target.parentElement;
            }
            if (!target) target = document.scrollingElement || document.documentElement;

            const before = target.scrollTop;
            target.scrollBy({ top: amount, behavior: 'instant' });
            const after = target.scrollTop;
            return { ok: true, before, after, delta: after - before, scrolledElement: target.tagName + (target.id ? '#' + target.id : '') };
          })()
        `);
        break;
      case "select_option":
  result = await webviewExecute(`
    (() => {
      const el = document.querySelector('${escapeJsString(params.selector)}');
      if (!el) return { error: 'Element not found: ${escapeJsString(params.selector)}' };

      if (el.tagName === 'SELECT') {
        const value = '${escapeJsString(params.value || '')}';
        const label = '${escapeJsString(params.label || '')}';
        let matched = null;
        for (const opt of el.options) {
          if ((value && opt.value === value) || (label && opt.textContent.trim() === label)) {
            matched = opt;
            break;
          }
        }
        if (!matched) return { error: 'No matching option found', available: Array.from(el.options).map(o => ({ value: o.value, label: o.textContent.trim() })) };

        el.value = matched.value;
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true, selected: matched.value };
      }
      return { error: 'Not a native select element', tag: el.tagName };
    })()
  `);
  break;
  case "get_dropdown_options":
  result = await webviewExecute(`
    (() => {
      const el = document.querySelector('${escapeJsString(params.selector)}');
      if (!el) return { error: 'Element not found' };
      if (el.tagName === 'SELECT') {
        return Array.from(el.options).map(o => ({ value: o.value, label: o.textContent.trim(), selected: o.selected }));
      }
      return { error: 'Not a native select' };
    })()
  `);
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
      case "run_js":
        result = await window.electronAPI.runJs(params.code);
        break;
      case "get_network_payloads":
        result = await window.electronAPI.getNetworkLog();
        break;
      case "submit_form":
        result = await webviewExecute(`
          (() => {
            const active = document.activeElement;
            if (active) {
              let form = active.closest('form');
              if (!form && active.form) form = active.form;
              if (form) { form.requestSubmit(); return { ok: true }; }
            }
            const forms = document.querySelectorAll('form');
            if (forms.length === 1) { forms[0].requestSubmit(); return { ok: true }; }
            if (active) {
              active.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
              active.dispatchEvent(new KeyboardEvent('keyup', { key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true }));
            }
            return { ok: true };
          })()
        `);
        break;
      case "press_key": {
            const wv = getBrowserView();
            if (!wv) { result = { error: "Webview not initialized" }; break; }
            const keyMap = {
              'Enter': 'Enter', 'Tab': 'Tab', 'Escape': 'Escape',
              'Backspace': 'Backspace', 'Delete': 'Delete',
              'ArrowUp': 'Up', 'ArrowDown': 'Down', 'ArrowLeft': 'Left', 'ArrowRight': 'Right',
              ' ': 'Space', 'Home': 'Home', 'End': 'End', 'PageUp': 'PageUp', 'PageDown': 'PageDown'
            };
            const electronKey = keyMap[params.key] || params.key;
            wv.sendInputEvent({ type: 'keyDown', keyCode: electronKey });
            wv.sendInputEvent({ type: 'keyUp', keyCode: electronKey });
            result = { ok: true };
            break;
          }
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
    if (command === "get_schema" && result && result.modals && result.modals.length > 0) {
      addLog(`Modal found: ${result.modals.length} dialog(s) detected`);
    }
    ws.send(JSON.stringify({
      type: "browser_result",
      request_id: request_id,
      result: result,
    }));
  }
}

// ── URL BAR ─────────────────────────────────────
const urlInput = document.getElementById("urlInput");
const urlDropdown = document.getElementById("urlDropdown");

function flattenFileTree(tree, prefix) {
  const results = [];
  for (const entry of tree) {
    const path = prefix ? `${prefix}/${entry.name}` : entry.name;
    if (entry.type === "file") {
      results.push({ name: entry.name, path: path });
    }
    if (entry.children) {
      results.push(...flattenFileTree(entry.children, path));
    }
  }
  return results;
}

function showUrlDropdown(query) {
  if (!query || !fileTreeData.length) {
    urlDropdown.classList.add("hidden");
    return;
  }
  const flat = flattenFileTree(fileTreeData, "");
  const q = query.toLowerCase();
  const matches = flat.filter(f => f.name.toLowerCase().includes(q) || f.path.toLowerCase().includes(q)).slice(0, 8);
  if (!matches.length) {
    urlDropdown.classList.add("hidden");
    return;
  }
  urlDropdown.innerHTML = "";
  matches.forEach(f => {
    const item = document.createElement("div");
    item.className = "url-dropdown-item";
    item.innerHTML = `<span class="dropdown-file-name">${f.name}</span><span class="dropdown-file-path">${f.path}</span>`;
    item.addEventListener("mousedown", (e) => {
      e.preventDefault();
      urlInput.value = f.path;
      urlDropdown.classList.add("hidden");
      navigateToUrl(f.path);
    });
    urlDropdown.appendChild(item);
  });
  urlDropdown.classList.remove("hidden");
}

function hideUrlDropdown() {
  urlDropdown.classList.add("hidden");
}

function navigateToUrl(url) {
  if (!url) return;
  if (!url.match(/^https?:\/\//i) && !url.startsWith("file:")) {
    url = "https://" + url;
  }
  getBrowserView().src = url;
  urlInput.value = url;
}

urlInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    let val = urlInput.value.trim();
    if (val && !val.match(/^https?:\/\//i) && !val.startsWith("file:")) {
      val = "https://www." + val.replace(/^www\./i, "") + ".com";
    }
    hideUrlDropdown();
    if (val) navigateToUrl(val);
    return;
  }
  if (e.key === "Enter") {
    e.preventDefault();
    const val = urlInput.value.trim();
    hideUrlDropdown();
    if (val) navigateToUrl(val);
    return;
  }
  if (e.key === "Escape") {
    hideUrlDropdown();
    urlInput.blur();
    return;
  }
  if (e.key === "ArrowDown" && !urlDropdown.classList.contains("hidden")) {
    e.preventDefault();
    const first = urlDropdown.querySelector(".url-dropdown-item");
    if (first) first.focus();
    return;
  }
});

urlInput.addEventListener("input", () => {
  showUrlDropdown(urlInput.value.trim());
});

urlInput.addEventListener("blur", () => {
  setTimeout(hideUrlDropdown, 150);
});

urlInput.addEventListener("focus", () => {
  if (urlInput.value.trim()) showUrlDropdown(urlInput.value.trim());
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

// ── THEME TOGGLE ────────────────────────────────
(function initTheme() {
  const saved = localStorage.getItem("ai_browser_theme");
  if (saved === "light" || saved === "dark") {
    document.documentElement.setAttribute("data-theme", saved);
  } else {
    document.documentElement.setAttribute("data-theme", "dark");
  }
  document.getElementById("themeToggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "light" ? "dark" : "light";
    document.documentElement.setAttribute("data-theme", next);
    localStorage.setItem("ai_browser_theme", next);
  });
})();

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
  const label = deepDive ? "🧠" : "";
  addLog(`${label}You: ${content}${filesToSend.length ? ` [${filesToSend.length} file(s) attached]` : ""}`);
  ws.send(JSON.stringify({ type: "message", content, attached_files: filesToSend, deep_dive: deepDive }));
  resetThinkingTokens();

  input.value = "";
  input.style.height = "auto";
  document.getElementById("charCount").textContent = "";
  attachedFiles = [];
  renderAttachedFiles();
}

function toggleDeepDive() {
  deepDive = !deepDive;
  const btn = document.getElementById("deepDiveBtn");
  btn.classList.toggle("active", deepDive);
  btn.querySelector("span").textContent = deepDive ? "Dive" : "Dive";
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

  if (thinking) {
    sendBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><rect x="6" y="6" width="12" height="12" rx="2" fill="currentColor"/></svg>';
    sendBtn.onclick = stopAgent;
    sendBtn.disabled = false;
    sendBtn.classList.add("stop-btn");
  } else {
    sendBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    sendBtn.onclick = sendInstruction;
    sendBtn.disabled = telegramModeOn;
    sendBtn.classList.remove("stop-btn");
  }
}

function stopAgent() {
  if (!ws || ws.readyState !== WebSocket.OPEN) return;
  ws.send(JSON.stringify({ type: "stop" }));
  setThinking(false);
  const input = document.getElementById("instructionInput");
  input.disabled = telegramModeOn;
}

function updateBadge(state, text) {
  const badge = document.getElementById("serverBadge");
  badge.className = "server-badge " + state;
  badge.querySelector(".badge-text").textContent = text;
}

function showError(msg) {
  document.getElementById("connectError").textContent = msg;
}

// ── USER INPUT REQUEST (HITL Interrupt) ─────────
let currentUserInputRequest = null;

function handleUserInputRequest(data) {
  const { tool, args, description } = data;
  currentUserInputRequest = { tool, args };

  const logs = document.getElementById("logContent");
  const wrapper = document.createElement("div");
  wrapper.className = "log-line form-request";

  const timestamp = document.createElement("span");
  timestamp.className = "response-timestamp";
  timestamp.textContent = `[${new Date().toLocaleTimeString()}] AI`;

  const text = document.createElement("div");
  text.className = "form-request-text";
  text.textContent = description || `AI needs your input for: ${tool}`;

  const controls = document.createElement("div");
  controls.className = "form-request-controls";

  if (tool === "get_user_confirmation") {
    const yesBtn = document.createElement("button");
    yesBtn.className = "form-inline-btn yes";
    yesBtn.textContent = "Yes";
    yesBtn.onclick = () => sendUserInputResponse("respond", "yes");
    const noBtn = document.createElement("button");
    noBtn.className = "form-inline-btn no";
    noBtn.textContent = "No";
    noBtn.onclick = () => sendUserInputResponse("respond", "no");
    controls.appendChild(yesBtn);
    controls.appendChild(noBtn);
  } else if (tool === "get_user_input_from_options") {
    let raw = (args && args.options) || [];
    if (typeof raw === "string") {
      try {
        raw = JSON.parse(raw);
      } catch {
        raw = raw.split("\n").map(s => s.trim()).filter(Boolean).join(",").split(",").map(s => s.trim()).filter(Boolean);
      }
    }
    const options = Array.isArray(raw) ? raw.filter(o => typeof o === "string" && o.trim()) : [];
    if (options.length) {
      options.forEach((opt) => {
        const btn = document.createElement("button");
        btn.className = "form-inline-btn option";
        btn.textContent = opt;
        btn.onclick = () => sendUserInputResponse("respond", opt);
        controls.appendChild(btn);
      });
    } else {
      const row = document.createElement("div");
      row.className = "form-inline-row";
      const input = document.createElement("input");
      input.type = "text";
      input.className = "form-inline-input";
      input.placeholder = "Type your response...";
      input.addEventListener("keydown", (e) => { if (e.key === "Enter") row.querySelector("button")?.click(); });
      const btn = document.createElement("button");
      btn.className = "form-inline-btn submit";
      btn.textContent = "Send";
      btn.onclick = () => sendUserInputResponse("respond", input.value);
      row.appendChild(input);
      row.appendChild(btn);
      controls.appendChild(row);
      setTimeout(() => input.focus(), 50);
    }
  } else {
    const row = document.createElement("div");
    row.className = "form-inline-row";
    const input = document.createElement("input");
    input.type = "text";
    input.className = "form-inline-input";
    input.placeholder = "Type your response...";
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") row.querySelector("button")?.click(); });
    const btn = document.createElement("button");
    btn.className = "form-inline-btn submit";
    btn.textContent = "Send";
    btn.onclick = () => sendUserInputResponse("respond", input.value);
    row.appendChild(input);
    row.appendChild(btn);
    controls.appendChild(row);
    setTimeout(() => input.focus(), 50);
  }

  wrapper.appendChild(timestamp);
  wrapper.appendChild(text);
  wrapper.appendChild(controls);
  logs.appendChild(wrapper);
  logs.scrollTop = logs.scrollHeight;
  expandLogPanel();
}

function sendUserInputResponse(type, content, editedArgs) {
  if (!currentUserInputRequest) return;

  const payload = {
    type: "user_input_response",
    tool: currentUserInputRequest.tool,
    content: content,
  };
  if (type === "edit" && editedArgs) {
    payload.type = "edit";
    payload.edited_args = editedArgs;
  }

  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(payload));
  }

  const logs = document.getElementById("logContent");
  const lastFormRequest = logs.querySelector(".form-request:last-child");
  if (lastFormRequest) {
    const ctrl = lastFormRequest.querySelector(".form-request-controls");
    if (ctrl) {
      ctrl.querySelectorAll("button").forEach(b => { b.disabled = true; b.classList.add("disabled"); });
      ctrl.querySelectorAll("input").forEach(i => { i.disabled = true; });
    }
  }

  currentUserInputRequest = null;
}

function hideConnectOverlay() {
  document.getElementById("connectOverlay").classList.add("hidden");
}

function showConnectOverlay() {
  document.getElementById("connectOverlay").classList.remove("hidden");
  renderRecentProjects();
}

function toggleLogPanel() {
  const panel = document.getElementById("logPanel");
  const btn = document.getElementById("logToggle");
  const badge = document.getElementById("logBadge");
  const wasCollapsed = panel.classList.contains("collapsed");
  if (wasCollapsed) {
    panel.classList.remove("collapsed");
    panel.style.height = "";
    btn.childNodes[btn.childNodes.length - 1].textContent = "v";
    badge.classList.add("hidden");
  } else {
    panel.classList.add("collapsed");
    panel.style.height = "";
    btn.childNodes[btn.childNodes.length - 1].textContent = "^";
  }
}

function expandLogPanel() {
  const panel = document.getElementById("logPanel");
  const btn = document.getElementById("logToggle");
  const badge = document.getElementById("logBadge");
  panel.classList.remove("collapsed");
  panel.style.height = "50vh";
  btn.childNodes[btn.childNodes.length - 1].textContent = "v";
  badge.classList.add("hidden");
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

let thinkingLine = null;

function addThinkingToken(token) {
  const logs = document.getElementById("logContent");
  if (!logs) return;
  if (!thinkingLine) {
    thinkingLine = document.createElement("div");
    thinkingLine.className = "log-line thinking-line";
    thinkingLine.textContent = `[${new Date().toLocaleTimeString()}] Thinking: `;
    logs.appendChild(thinkingLine);
  }
  thinkingLine.textContent += token;
  logs.scrollTop = logs.scrollHeight;
}

function resetThinkingTokens() {
  thinkingLine = null;
}

function addResponseLog(content) {
  const logs = document.getElementById("logContent");
  if (!logs) return;

  const wrapper = document.createElement("div");
  wrapper.className = "log-line ai-response";

  const timestamp = document.createElement("span");
  timestamp.className = "response-timestamp";
  timestamp.textContent = `[${new Date().toLocaleTimeString()}] AI`;

  const text = document.createElement("div");
  text.className = "response-text";
  text.textContent = content;

  const footer = document.createElement("div");
  footer.className = "response-footer";

  const copyBtn = document.createElement("button");
  copyBtn.className = "copy-btn";
  copyBtn.innerHTML = `<svg width="12" height="12" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="2"/></svg><span>Copy</span>`;
  copyBtn.addEventListener("click", () => {
    navigator.clipboard.writeText(content).then(() => {
      copyBtn.classList.add("copied");
      copyBtn.querySelector("span").textContent = "Copied!";
      setTimeout(() => {
        copyBtn.classList.remove("copied");
        copyBtn.querySelector("span").textContent = "Copy";
      }, 1500);
    });
  });

  footer.appendChild(copyBtn);
  wrapper.appendChild(timestamp);
  wrapper.appendChild(text);
  wrapper.appendChild(footer);
  logs.appendChild(wrapper);
  logs.scrollTop = logs.scrollHeight;

  while (logs.children.length > 100) {
    logs.removeChild(logs.firstChild);
  }

  const panel = document.getElementById("logPanel");
  if (panel && panel.classList.contains("collapsed")) {
    document.getElementById("logBadge").classList.remove("hidden");
  }
}
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

async function refreshFileTree() {
  const btn = document.getElementById("sidebarRefresh");
  if (btn) btn.style.animation = "spin 0.6s linear";
  await loadFileTree();
  if (btn) setTimeout(() => btn.style.animation = "", 600);
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

  const delBtn = document.createElement("button");
  delBtn.className = "tree-delete-btn";
  delBtn.textContent = "\u00D7";
  delBtn.title = `Delete ${entry.name}`;
  delBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    deleteFileFromTree(entry);
  });

  item.appendChild(icon);
  item.appendChild(name);
  item.appendChild(delBtn);
  parent.appendChild(item);

  if (entry.type === "file") {
    item.addEventListener("click", (e) => {
      if (e.target === delBtn) return;
      e.stopPropagation();
      attachFileFromTree(entry);
    });
    item.addEventListener("dblclick", (e) => {
      e.stopPropagation();
      if (!savedProjectDir) return;
      const fullPath = savedProjectDir + "/" + entry.path;
      if (/\.(html?|xhtml)$/i.test(entry.name)) {
        navigateToUrl("file://" + fullPath);
      } else {
        window.electronAPI.openFile(fullPath);
      }
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
      if (e.target === delBtn) return;
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

async function deleteFileFromTree(entry) {
  if (!savedProjectDir) return;
  if (!confirm(`Delete "${entry.name}"?`)) return;
  const result = await window.electronAPI.deleteEntry(savedProjectDir, entry.path);
  if (!result.success) {
    addLog(`Delete failed: ${result.error}`);
    return;
  }
  attachedFiles = attachedFiles.filter(f => f.path !== entry.path);
  renderAttachedFiles();
  await loadFileTree();
  addLog(`Deleted: ${entry.name}`);
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
