import { create } from "zustand";
import type { AppMode } from "../types";
import type { VICONSpace } from "../components/map/VICONMap";

function loadStorage<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function saveStorage(key: string, val: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(val));
  } catch {}
}

interface UIStore {
  // State
  mode: AppMode;
  leftSidebarOpen: boolean;
  rightSidebarOpen: boolean;
  timelineOpen: boolean;
  cameraFeedOpen: boolean;
  operationsMonitorOpen: boolean;
  mapMode: "gps" | "vicon";
  viconSpace: VICONSpace | null;

  // Actions
  setMode: (mode: AppMode) => void;
  toggleLeftSidebar: () => void;
  toggleRightSidebar: () => void;
  toggleTimeline: () => void;
  toggleCameraFeed: () => void;
  toggleOperationsMonitor: () => void;
  setMapMode: (mode: "gps" | "vicon") => void;
  setViconSpace: (space: VICONSpace) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  mode: "plan",
  leftSidebarOpen: true,
  rightSidebarOpen: true,
  timelineOpen: true,
  cameraFeedOpen: false,
  operationsMonitorOpen: false,
  mapMode: loadStorage<"gps" | "vicon">("henosync_map_mode", "gps"),
  viconSpace: loadStorage<VICONSpace | null>("henosync_vicon_space", null),

  setMode: (mode) => set({ mode }),
  toggleLeftSidebar: () =>
    set((s) => ({ leftSidebarOpen: !s.leftSidebarOpen })),
  toggleRightSidebar: () =>
    set((s) => ({ rightSidebarOpen: !s.rightSidebarOpen })),
  toggleTimeline: () => set((s) => ({ timelineOpen: !s.timelineOpen })),
  toggleCameraFeed: () => set((s) => ({ cameraFeedOpen: !s.cameraFeedOpen })),
  toggleOperationsMonitor: () =>
    set((s) => ({ operationsMonitorOpen: !s.operationsMonitorOpen })),
  setMapMode: (mapMode) => {
    saveStorage("henosync_map_mode", mapMode);
    set({ mapMode });
  },
  setViconSpace: (viconSpace) => {
    saveStorage("henosync_vicon_space", viconSpace);
    set({ viconSpace });
  },
}));
