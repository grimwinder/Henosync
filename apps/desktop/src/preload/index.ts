import { contextBridge, ipcRenderer } from "electron";

/**
 * Typed API exposed to the React renderer.
 * The renderer ONLY accesses Electron/Node via these methods.
 * Nothing else is exposed — security boundary.
 */
const henosyncAPI = {
  // ── Backend ──────────────────────────────────────────────────
  backend: {
    getUrl: (): Promise<string> => ipcRenderer.invoke("backend:getUrl"),
    getPort: (): Promise<number> => ipcRenderer.invoke("backend:getPort"),
  },

  // ── Window Controls ───────────────────────────────────────────
  window: {
    minimize: (): void => ipcRenderer.send("window:minimize"),
    maximize: (): void => ipcRenderer.send("window:maximize"),
    close: (): void => ipcRenderer.send("window:close"),
    isMaximized: (): Promise<boolean> =>
      ipcRenderer.invoke("window:isMaximized"),
    onMaximizeChanged: (callback: (maximized: boolean) => void): void => {
      ipcRenderer.on("window:maximizeChanged", (_, maximized) =>
        callback(maximized),
      );
    },
  },

  // ── File Dialogs ──────────────────────────────────────────────
  dialog: {
    openFile: (filters?: Electron.FileFilter[]): Promise<string | null> =>
      ipcRenderer.invoke("dialog:openFile", filters),
    saveFile: (filters?: Electron.FileFilter[]): Promise<string | null> =>
      ipcRenderer.invoke("dialog:saveFile", filters),
  },
};

contextBridge.exposeInMainWorld("henosync", henosyncAPI);

// TypeScript declaration for renderer access
export type HensoyncAPI = typeof henosyncAPI;
