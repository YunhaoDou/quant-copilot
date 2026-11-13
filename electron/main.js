// Desktop shell for Quant Copilot. Does NOT reimplement or bundle Postgres/Redis/the
// Python backend — it owns the lifecycle of the existing dev stack (start.sh/stop.sh),
// waits for the Next.js frontend to answer, then opens it in a native window. Quitting
// the app stops everything it started, the same way closing a normal desktop app does.
const { app, BrowserWindow, Menu, shell } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

const FRONTEND_URL = "http://localhost:3000";
const STARTUP_TIMEOUT_MS = 60_000;
const POLL_INTERVAL_MS = 750;

// Dev: this file lives in <repo>/electron, so the repo root is one level up.
// Packaged: start.sh/stop.sh are copied into Resources/app by the "extraResources" build config.
const ROOT = app.isPackaged ? path.join(process.resourcesPath, "app") : path.join(__dirname, "..");

let stackProcess = null;
let mainWindow = null;

function startStack() {
  stackProcess = spawn("bash", ["start.sh"], { cwd: ROOT, stdio: "ignore" });
  stackProcess.on("error", (err) => {
    console.error("Failed to launch start.sh:", err);
  });
}

function stopStack() {
  try {
    spawn("bash", ["stop.sh"], { cwd: ROOT, stdio: "ignore" });
  } catch (err) {
    console.error("Failed to launch stop.sh:", err);
  }
}

function waitForFrontend(url, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  return new Promise((resolve, reject) => {
    (function poll() {
      http
        .get(url, (res) => {
          res.resume();
          resolve();
        })
        .on("error", () => {
          if (Date.now() > deadline) {
            reject(new Error(`Frontend never came up at ${url} within ${timeoutMs}ms`));
          } else {
            setTimeout(poll, POLL_INTERVAL_MS);
          }
        });
    })();
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 900,
    minHeight: 600,
    title: "Quant Copilot",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });
  mainWindow.loadURL(FRONTEND_URL);

  // Open any target="_blank" link (news headline URLs) in the OS browser, not a new Electron window.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function buildMenu() {
  const isMac = process.platform === "darwin";
  const template = [
    ...(isMac ? [{ role: "appMenu" }] : []),
    { role: "editMenu" },
    {
      role: "viewMenu",
      submenu: [
        { role: "reload" },
        { role: "forceReload" },
        { role: "toggleDevTools" },
        { type: "separator" },
        { role: "resetZoom" },
        { role: "zoomIn" },
        { role: "zoomOut" },
        { type: "separator" },
        { role: "togglefullscreen" },
      ],
    },
    { role: "windowMenu" },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

app.whenReady().then(async () => {
  buildMenu();
  startStack();
  try {
    await waitForFrontend(FRONTEND_URL, STARTUP_TIMEOUT_MS);
  } catch (err) {
    console.error(err);
    // Fall through and open the window anyway — it'll show the browser's own connection
    // error, which is a more honest failure state than a silently-stuck splash screen.
  }
  createWindow();

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  stopStack();
});
