import { create } from "zustand";
import type { PluginManifest, ControlPluginInfo } from "../types";

interface PluginStore {
  // State
  devicePlugins: PluginManifest[];
  controlPlugins: ControlPluginInfo[];
  transports: string[];

  // Actions
  setDevicePlugins: (plugins: PluginManifest[]) => void;
  setControlPlugins: (plugins: ControlPluginInfo[]) => void;
  setTransports: (transports: string[]) => void;
}

export const usePluginStore = create<PluginStore>((set) => ({
  devicePlugins: [],
  controlPlugins: [],
  transports: [],

  setDevicePlugins: (plugins) => set({ devicePlugins: plugins }),
  setControlPlugins: (plugins) => set({ controlPlugins: plugins }),
  setTransports: (transports) => set({ transports }),
}));
