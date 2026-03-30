import { create } from "zustand";
import type { AppMode } from "../types";

interface UIStore {
  // State
  mode: AppMode;
  leftSidebarOpen: boolean;
  rightSidebarOpen: boolean;
  timelineOpen: boolean;
  cameraFeedOpen: boolean;
  operationsMonitorOpen: boolean;

  // Actions
  setMode: (mode: AppMode) => void;
  toggleLeftSidebar: () => void;
  toggleRightSidebar: () => void;
  toggleTimeline: () => void;
  toggleCameraFeed: () => void;
  toggleOperationsMonitor: () => void;
}

export const useUIStore = create<UIStore>((set) => ({
  mode: "plan",
  leftSidebarOpen: true,
  rightSidebarOpen: true,
  timelineOpen: true,
  cameraFeedOpen: false,
  operationsMonitorOpen: false,

  setMode: (mode) => set({ mode }),
  toggleLeftSidebar: () =>
    set((s) => ({ leftSidebarOpen: !s.leftSidebarOpen })),
  toggleRightSidebar: () =>
    set((s) => ({ rightSidebarOpen: !s.rightSidebarOpen })),
  toggleTimeline: () => set((s) => ({ timelineOpen: !s.timelineOpen })),
  toggleCameraFeed: () => set((s) => ({ cameraFeedOpen: !s.cameraFeedOpen })),
  toggleOperationsMonitor: () =>
    set((s) => ({ operationsMonitorOpen: !s.operationsMonitorOpen })),
}));
