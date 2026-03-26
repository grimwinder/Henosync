import { app, BrowserWindow, ipcMain, shell, dialog } from "electron";
import { join } from "path";
import { spawn, ChildProcess } from "child_process";
import { existsSync, readFileSync, writeFileSync } from "fs";

const isDev = process.env.NODE_ENV === "development";
const BACKEND_PORT = 8765;
const BACKEND_HOST = "127.0.0.1";
const BACKEND_URL = `http://${BACKEND_HOST}:${BACKEND_PORT}`;
const HEALTH_CHECK_URL = `${BACKEND_URL}/health`;
const HEALTH_CHECK_RETRIES = 20;
const HEALTH_CHECK_INTERVAL = 500;
const WINDOW_STATE_PATH = join(app.getPath("userData"), "window-state.json");

let mainWindow: BrowserWindow | null = null;
let backendProcess: ChildProcess | null = null;

// ── Backend ───────────────────────────────────────────────────

function startBackend(): Promise<void> {
  return new Promise((resolve, reject) => {
    const backendDir = join(app.getAppPath(), "..", "..", "apps", "backend");

    console.log(`Starting backend in: ${backendDir}`);

    if (!existsSync(backendDir)) {
      reject(new Error(`Backend directory not found: ${backendDir}`));
      return;
    }

    backendProcess = spawn(
      "poetry",
      [
        "run",
        "uvicorn",
        "main:app",
        "--host",
        BACKEND_HOST,
        "--port",
        String(BACKEND_PORT),
      ],
      {
        cwd: backendDir,
        env: { ...process.env },
        stdio: ["ignore", "pipe", "pipe"],
        shell: true,
      },
    );

    backendProcess.stdout?.on("data", (data: Buffer) => {
      console.log(`[backend] ${data.toString().trim()}`);
    });

    backendProcess.stderr?.on("data", (data: Buffer) => {
      console.error(`[backend] ${data.toString().trim()}`);
    });

    backendProcess.on("error", (err: Error) => {
      console.error("Backend process error:", err);
      reject(err);
    });

    backendProcess.on("exit", (code: number | null) => {
      console.log(`Backend exited with code: ${code}`);
      backendProcess = null;
    });

    waitForBackend().then(resolve).catch(reject);
  });
}

async function waitForBackend(): Promise<void> {
  for (let i = 0; i < HEALTH_CHECK_RETRIES; i++) {
    try {
      const response = await fetch(HEALTH_CHECK_URL);
      if (response.ok) {
        console.log("Backend health check passed");
        return;
      }
    } catch {
      // Not ready yet
    }
    await new Promise((r) => setTimeout(r, HEALTH_CHECK_INTERVAL));
  }
  throw new Error(
    `Backend did not start within ${
      (HEALTH_CHECK_RETRIES * HEALTH_CHECK_INTERVAL) / 1000
    }s`,
  );
}

function stopBackend(): void {
  if (backendProcess) {
    console.log("Stopping backend...");
    backendProcess.kill("SIGTERM");
    backendProcess = null;
  }
}

// ── Window State ──────────────────────────────────────────────

interface WindowBounds {
  x: number;
  y: number;
  width: number;
  height: number;
}

function loadWindowBounds(): WindowBounds | null {
  try {
    if (existsSync(WINDOW_STATE_PATH)) {
      const data = readFileSync(WINDOW_STATE_PATH, "utf-8");
      return JSON.parse(data) as WindowBounds;
    }
  } catch {
    // Ignore — use defaults
  }
  return null;
}

function saveWindowBounds(bounds: WindowBounds): void {
  try {
    writeFileSync(WINDOW_STATE_PATH, JSON.stringify(bounds), "utf-8");
  } catch {
    // Ignore save errors
  }
}

// ── Main Window ───────────────────────────────────────────────

function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1280,
    minHeight: 720,
    frame: false,
    show: false,
    backgroundColor: "#0D0F12",
    webPreferences: {
      preload: join(__dirname, "preload/index.js"),
      nodeIntegration: false,
      contextIsolation: true,
      sandbox: true,
    },
  });

  // Restore saved window position and size
  const savedBounds = loadWindowBounds();
  if (savedBounds) {
    mainWindow.setBounds(savedBounds);
  } else {
    mainWindow.center();
  }

  // Save window position on move or resize
  mainWindow.on("resize", () => {
    if (mainWindow && !mainWindow.isMaximized()) {
      saveWindowBounds(mainWindow.getBounds());
    }
  });

  mainWindow.on("move", () => {
    if (mainWindow && !mainWindow.isMaximized()) {
      saveWindowBounds(mainWindow.getBounds());
    }
  });

  // Content Security Policy
  mainWindow.webContents.session.webRequest.onHeadersReceived(
    (details, callback) => {
      callback({
        responseHeaders: {
          ...details.responseHeaders,
          "Content-Security-Policy": [
            "default-src 'self'; " +
              "script-src 'self'; " +
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; " +
              "font-src 'self' https://fonts.gstatic.com; " +
              "connect-src 'self' http://127.0.0.1:8765 ws://127.0.0.1:8765",
          ],
        },
      });
    },
  );

  mainWindow.on("ready-to-show", () => {
    mainWindow?.show();
    mainWindow?.focus();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  if (isDev) {
    mainWindow.loadURL("http://localhost:5173");
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(join(__dirname, "../renderer/index.html"));
  }
}

// ── IPC ───────────────────────────────────────────────────────

function setupIPC(): void {
  ipcMain.on("window:minimize", () => {
    mainWindow?.minimize();
  });

  ipcMain.on("window:maximize", () => {
    if (mainWindow?.isMaximized()) {
      mainWindow.unmaximize();
    } else {
      mainWindow?.maximize();
    }
  });

  ipcMain.on("window:close", () => {
    mainWindow?.close();
  });

  ipcMain.handle("window:isMaximized", () => {
    return mainWindow?.isMaximized() ?? false;
  });

  ipcMain.handle("backend:getUrl", () => {
    return BACKEND_URL;
  });

  ipcMain.handle("backend:getPort", () => {
    return BACKEND_PORT;
  });

  ipcMain.handle("dialog:openFile", async (_, filters) => {
    const result = await dialog.showOpenDialog(mainWindow!, {
      properties: ["openFile"],
      filters: filters ?? [
        { name: "Henosync Mission", extensions: ["rbmission"] },
        { name: "All Files", extensions: ["*"] },
      ],
    });
    return result.canceled ? null : result.filePaths[0];
  });

  ipcMain.handle("dialog:saveFile", async (_, filters) => {
    const result = await dialog.showSaveDialog(mainWindow!, {
      filters: filters ?? [
        { name: "Henosync Mission", extensions: ["rbmission"] },
      ],
    });
    return result.canceled ? null : result.filePath;
  });

  mainWindow?.on("maximize", () => {
    mainWindow?.webContents.send("window:maximizeChanged", true);
  });

  mainWindow?.on("unmaximize", () => {
    mainWindow?.webContents.send("window:maximizeChanged", false);
  });
}

// ── App Lifecycle ─────────────────────────────────────────────

app.whenReady().then(async () => {
  try {
    await startBackend();
  } catch (err) {
    console.error("Failed to start backend:", err);
    dialog.showErrorBox(
      "Henosync — Backend Error",
      `Failed to start the Henosync backend.\n\n${err}\n\nMake sure Python and Poetry are installed.`,
    );
    app.quit();
    return;
  }

  createMainWindow();
  setupIPC();
});

app.on("window-all-closed", () => {
  stopBackend();
  app.quit();
});

app.on("before-quit", () => {
  stopBackend();
});

app.on("web-contents-created", (_, contents) => {
  contents.on("will-navigate", (event, url) => {
    if (!url.startsWith("http://localhost")) {
      event.preventDefault();
    }
  });
});
