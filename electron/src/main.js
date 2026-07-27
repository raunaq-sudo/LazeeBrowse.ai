const { app, BrowserWindow, ipcMain, shell, dialog, powerSaveBlocker } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

let mainWindow;
let backendProcess;
let splash;

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
