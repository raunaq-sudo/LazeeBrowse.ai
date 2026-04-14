const { app, BrowserWindow, ipcMain, shell, dialog, powerSaveBlocker } = require("electron");
const path = require("path");
const { spawn } = require("child_process")

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
    width: 1100,
    height: 760,
    minWidth: 800,
    minHeight: 600,
    frame: false,
    titleBarStyle: "hidden",
    backgroundColor: "#0d0f14",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
    icon: path.join(__dirname, "../assets/icon.png"),
    show: false,
  });

  mainWindow.loadFile(path.join(__dirname, "../src/index.html"));

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  // Open devtools in dev mode
  if (process.argv.includes("--dev")) {
    mainWindow.webContents.openDevTools();
  }
}

function getBackendPath() {
  const isDev = !app.isPackaged;

  if (isDev) {
    return path.join(__dirname, "../backend/main/main"); // adjust if needed
  } else {
    return path.join(process.resourcesPath, "backend", "main", "main");
  }
}

function startBackend() {
  const backendPath = getBackendPath();

  console.log("Starting backend from:", backendPath);

  backendProcess = spawn(backendPath, [], {
    stdio: "pipe"
  });

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

app.whenReady().then(async () => {
  createSplash();          // 👈 show loader
  startBackend();          // 👈 start backend

  try {
    await waitForBackend();  // 👈 wait until ready

    createWindow();          // 👈 load main UI

    if (splash) {
      splash.close();        // 👈 remove loader
    }

  } catch (err) {
    console.error("Backend failed:", err);
  }

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });

  blockerId = powerSaveBlocker.start('prevent-display-sleep');
  app.on("window-all-closed", () => {
  app.quit();
});
})


ipcMain.handle("open-file", async (event, filePath) => {
  try {
    const result = await shell.openPath(filePath);

    if (result) {
      console.error("Failed to open:", result);
      return { success: false, error: result };
    }

    return { success: true };
  } catch (err) {
    return { success: false, error: err.message };
  }
});

ipcMain.handle('select-folder', async () => {
    const result = await dialog.showOpenDialog({
        properties: ['openDirectory', 'createDirectory']
    });

    if (result.canceled) return null;

    return result.filePaths[0]; // 👈 absolute path
});


app.on("will-quit", () => {
  if (backendProcess) backendProcess.kill();
});