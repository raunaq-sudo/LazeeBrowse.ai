const { app, BrowserWindow, ipcMain, shell, dialog, powerSaveBlocker, webContents } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let mainWindow;
let backendProcess;
let splash;
let activeWebContents = null;

function createSplash() {
  splash = new BrowserWindow({
    width: 400,
    height: 300,
    frame: false,
    alwaysOnTop: true,
    transparent: true,
    resizable: false,
    center: true,
  });
  splash.loadFile(path.join(__dirname, "../src/loading.html"));
}

const axios = require("axios");

async function waitForBackend() {
  for (let i = 0; i < 20; i++) {
    try {
      await axios.get("http://127.0.0.1:8000/health");
      console.log("Backend ready");
      return;
    } catch {
      await new Promise(r => setTimeout(r, 2000));
    }
  }
  throw new Error("Backend failed to start");
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1200,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    titleBarStyle: "hidden",
    backgroundColor: "#0d0f14",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      webviewTag: true,
    },
    icon: path.join(__dirname, "../assets/icon.png"),
    show: false,
  });

  mainWindow.loadFile(path.join(__dirname, "../src/index.html"));

  mainWindow.webContents.on("did-attach-webview", (event, webContents) => {
    activeWebContents = webContents;
    // Mask as regular Chrome so sites like LinkedIn don't serve mobile/restricted versions
    webContents.setUserAgent(
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    );
    // Inject Sec-CH-UA client hint headers so sites see a real Chrome browser
    webContents.session.webRequest.onBeforeSendHeaders((details, callback) => {
      details.requestHeaders["Sec-CH-UA"] = '"Chromium";v="131", "Google Chrome";v="131", "Not_A Brand";v="24"';
      details.requestHeaders["Sec-CH-UA-Mobile"] = "?0";
      details.requestHeaders["Sec-CH-UA-Platform"] = '"macOS"';
      details.requestHeaders["Sec-Fetch-Dest"] = "document";
      details.requestHeaders["Sec-Fetch-Mode"] = "navigate";
      details.requestHeaders["Sec-Fetch-Site"] = "none";
      details.requestHeaders["Sec-Fetch-User"] = "?1";
      details.requestHeaders["Upgrade-Insecure-Requests"] = "1";
      callback({ requestHeaders: details.requestHeaders });
    });
    hookWebRequestSession(webContents.session);
    webContents.on("destroyed", () => {
      if (activeWebContents === webContents) activeWebContents = null;
    });
  });

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools();
  }
}

const isDev = !app.isPackaged;

function getBackendCommand() {
  if (isDev) {
    // In dev mode, run the Python backend directly
    const backendDir = path.join(__dirname, "../../fastapi-server");
    const python = path.join(backendDir, ".venv/bin/python");
    return { cmd: python, args: ["main.py"], cwd: backendDir };
  }
  // In production, use the compiled binary
  const basePath = path.join(process.resourcesPath, "backend", "main");
  let executableName = "main";
  if (process.platform === "win32") executableName = "main.exe";
  const cmd = path.join(basePath, executableName);
  return { cmd, args: [], cwd: basePath };
}

function startBackend() {
  const { cmd, args, cwd } = getBackendCommand();
  console.log("Starting backend:", cmd, args.join(" "), "from", cwd);

  backendProcess = spawn(cmd, args, { stdio: "pipe", cwd });

  backendProcess.stdout.on("data", (data) => {
    console.log("BACKEND STDOUT:", data.toString());
  });

  backendProcess.stderr.on("data", (data) => {
    console.error("BACKEND STDERR:", data.toString());
  });

  backendProcess.on("error", (err) => {
    console.error("Failed to start backend:", err);
  });

  backendProcess.on("exit", (code) => {
    console.log("Backend exited with code:", code);
  });
}

// ── FILE/DIALOG IPC HANDLERS ─────────────────────

ipcMain.handle("open-file", async (event, filePath) => {
  try {
    const result = await shell.openPath(filePath);
    if (result) return { success: false, error: result };
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle("save-pdf", async (event, data, defaultName) => {
  try {
    const result = await dialog.showSaveDialog(mainWindow, {
      title: "Save page as PDF",
      defaultPath: defaultName || "page.pdf",
      filters: [{ name: "PDF", extensions: ["pdf"] }],
    });
    if (result.canceled || !result.filePath) return { success: false, canceled: true };
    await fs.promises.writeFile(result.filePath, Buffer.from(data));
    return { success: true, path: result.filePath };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle("select-folder", async () => {
  const result = await dialog.showOpenDialog({
    properties: ["openDirectory", "createDirectory"],
  });
  if (result.canceled) return null;
  return result.filePaths[0];
});

ipcMain.handle("select-files", async (event, defaultPath) => {
  const result = await dialog.showOpenDialog({
    properties: ["openFile", "multiSelections"],
    defaultPath: defaultPath || undefined,
  });
  if (result.canceled) return [];
  return result.filePaths;
});

// ── WINDOW CONTROL IPC HANDLERS ──────────────────

ipcMain.on("window:minimize", () => {
  if (mainWindow) mainWindow.minimize();
});

ipcMain.on("window:maximize", () => {
  if (mainWindow) {
    if (mainWindow.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow.maximize();
    }
  }
});

ipcMain.on("window:close", () => {
  if (mainWindow) mainWindow.close();
});

// ── FILE TREE SCAN IPC HANDLER ──────────────────

function scanDir(dirPath, prefix) {
  const entries = [];
  let items;
  try {
    items = fs.readdirSync(dirPath, { withFileTypes: true });
  } catch (err) {
    return entries;
  }
  items.sort((a, b) => {
    if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1;
    return a.name.localeCompare(b.name, undefined, { sensitivity: "base" });
  });
  for (const item of items) {
    const rel = prefix ? `${prefix}/${item.name}` : item.name;
    if (item.isDirectory()) {
      const children = scanDir(path.join(dirPath, item.name), rel);
      entries.push({ name: item.name, path: rel, type: "dir", children });
    } else {
      let size = 0;
      try { size = fs.statSync(path.join(dirPath, item.name)).size; } catch {}
      entries.push({ name: item.name, path: rel, type: "file", size });
    }
  }
  return entries;
}

ipcMain.handle("scan-directory", async (event, dirPath) => {
  if (!dirPath) return [];
  return scanDir(dirPath, "");
});

// ── DELETE FILE/DIRECTORY IPC HANDLER ────────────

ipcMain.handle("delete-entry", async (event, basePath, relPath) => {
  try {
    if (!basePath || !relPath) return { success: false, error: "Missing path" };
    const normalizedBase = path.resolve(basePath);
    const full = path.resolve(path.join(basePath, relPath));
    if (!full.startsWith(normalizedBase + path.sep) && full !== normalizedBase) {
      return { success: false, error: "Path traversal blocked" };
    }
    if (!fs.existsSync(full)) return { success: false, error: "Not found" };
    const stat = fs.statSync(full);
    if (stat.isDirectory()) {
      fs.rmSync(full, { recursive: true, force: true });
    } else {
      fs.unlinkSync(full);
    }
    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

// ── BROWSER CAPTURE & JS EXEC IPC ───────────────

const networkLogEntries = [];
const NETWORK_LOG_MAX = 300;
const pendingNetworkPayloads = new Map();

function getHeader(headers, name) {
  if (!headers) return null;
  const lower = name.toLowerCase();
  for (const key of Object.keys(headers)) {
    if (key.toLowerCase() === lower) return headers[key];
  }
  return null;
}

function sanitizeJsResult(value) {
  try {
    const seen = new WeakSet();
    const out = JSON.stringify(value, (k, v) => {
      if (typeof v === "function") return "[function]";
      if (typeof v === "symbol") return "[symbol]";
      if (v && typeof v === "object") {
        if (v.nodeType) return "[dom]";
        if (seen.has(v)) return "[circular]";
        seen.add(v);
      }
      return v;
    });
    return out === undefined ? String(value) : out;
  } catch {
    return String(value);
  }
}

function hookWebRequestSession(session) {
  if (!session || session.__networkCaptureHooked) return;
  session.__networkCaptureHooked = true;

  session.webRequest.onBeforeRequest({ urls: ["*://*/*"] }, (details, callback) => {
    let payload = null;
    if (details.uploadData && details.uploadData.length) {
      payload = details.uploadData
        .map((u) => {
          if (u.bytes) return Buffer.from(u.bytes).toString("utf8");
          if (u.file) return `[file upload: ${u.file}]`;
          return "";
        })
        .join("\n")
        .slice(0, 20000);
    }
    pendingNetworkPayloads.set(details.id, payload);
    callback({});
  });

  session.webRequest.onCompleted({ urls: ["*://*/*"] }, (details) => {
    const payload = pendingNetworkPayloads.get(details.id);
    pendingNetworkPayloads.delete(details.id);
    const contentLength = parseInt(getHeader(details.responseHeaders, "content-length") || "0", 10) || 0;
    networkLogEntries.push({
      url: details.url,
      method: details.method,
      resourceType: details.resourceType || null,
      status: details.statusCode,
      contentType: getHeader(details.responseHeaders, "content-type") || null,
      size: contentLength,
      payload: payload || undefined,
      timestamp: new Date(details.timestamp || Date.now()).toISOString(),
    });
    while (networkLogEntries.length > NETWORK_LOG_MAX) networkLogEntries.shift();
  });
}

ipcMain.handle("network-log", async (event, action) => {
  if (action === "clear") {
    networkLogEntries.length = 0;
    pendingNetworkPayloads.clear();
    return { success: true };
  }
  return { success: true, entries: networkLogEntries.map((e) => ({ ...e })) };
});

ipcMain.handle("run-js", async (event, code) => {
  const wc = activeWebContents;
  if (!wc || wc.isDestroyed()) return { error: "No active browser page" };
  try {
    const result = await wc.executeJavaScript(code, true);
    return { ok: true, result: sanitizeJsResult(result) };
  } catch (e) {
    return { error: e.message };
  }
});

// ── CAPTURE WEBVIEW SCREENSHOT ──────────────────

ipcMain.handle("capture-webview", async (event, webContentsId, viewportW, viewportH, fullPage) => {
  const wc = webContents.fromId(webContentsId);
  if (!wc || wc.isDestroyed()) return { error: "WebContents not found or destroyed" };
  try {
    const rect = fullPage
      ? { x: 0, y: 0, width: viewportW, height: viewportH }
      : { x: 0, y: 0, width: viewportW, height: viewportH };
    const image = await wc.capturePage(rect);
    const pngBuffer = image.toPNG();
    return pngBuffer.toString("base64");
  } catch (e) {
    return { error: e.message };
  }
});

// ── SAVE SCREENSHOT TO PROJECT ──────────────────

ipcMain.handle("save-screenshot-to-project", async (event, projectDir, base64Data, filename) => {
  if (!projectDir) return { success: false, error: "No project directory set" };
  try {
    const screenshotsDir = path.join(projectDir, "screenshots");
    await fs.promises.mkdir(screenshotsDir, { recursive: true });
    const filePath = path.join(screenshotsDir, filename);
    await fs.promises.writeFile(filePath, Buffer.from(base64Data, "base64"));
    return { success: true, path: filePath };
  } catch (e) {
    return { success: false, error: e.message };
  }
});

// ── APP LIFECYCLE ───────────────────────────────

app.whenReady().then(async () => {
  createSplash();
  startBackend();

  try {
    await waitForBackend();
    createWindow();
    if (splash) splash.close();
  } catch (err) {
    console.error("Backend failed:", err);
    if (splash) splash.close();
    dialog.showErrorBox("Backend Error", "Failed to start the backend server. Please restart the application.");
    app.quit();
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });

  powerSaveBlocker.start("prevent-display-sleep");
});

app.on("window-all-closed", () => {
  app.quit();
});

app.on("will-quit", () => {
  if (backendProcess) backendProcess.kill();
});

