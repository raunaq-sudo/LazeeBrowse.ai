const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  // Window controls
  minimize: () => ipcRenderer.send("window:minimize"),
  maximize: () => ipcRenderer.send("window:maximize"),
  close: () => ipcRenderer.send("window:close"),

  // File operations
  openFile: (path) => ipcRenderer.invoke("open-file", path),
  savePdf: (data, defaultName) => ipcRenderer.invoke("save-pdf", data, defaultName),
  selectFolder: () => ipcRenderer.invoke("select-folder"),
  selectFiles: (defaultPath) => ipcRenderer.invoke("select-files", defaultPath),
  scanDirectory: (dirPath) => ipcRenderer.invoke("scan-directory", dirPath),
  deleteEntry: (basePath, relPath) => ipcRenderer.invoke("delete-entry", basePath, relPath),

  // Browser page (webview guest webContents)
  runJs: (code) => ipcRenderer.invoke("run-js", code),
  getNetworkLog: () => ipcRenderer.invoke("network-log", "get"),

  captureWebview: (id, w, h) => ipcRenderer.invoke('capture-webview', id, w, h),
saveScreenshotToProject: (projectDir, base64Data, filename) =>
  ipcRenderer.invoke('save-screenshot-to-project', projectDir, base64Data, filename),
});
