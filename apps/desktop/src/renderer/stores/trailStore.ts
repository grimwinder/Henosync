import { create } from "zustand";

const MAX_TRAIL = 2000;

interface TrailStore {
  gpsTrails: Record<string, Array<[number, number]>>; // node_id → [[lon, lat], ...]
  viconTrails: Record<string, Array<[number, number]>>; // node_id → [[x_m, y_m], ...]
  addGpsPoint: (nodeId: string, lon: number, lat: number) => void;
  addViconPoint: (nodeId: string, x: number, y: number) => void;
  clearTrails: () => void;
}

export const useTrailStore = create<TrailStore>((set) => ({
  gpsTrails: {},
  viconTrails: {},

  addGpsPoint: (nodeId, lon, lat) =>
    set((s) => {
      const prev = s.gpsTrails[nodeId] ?? [];
      const next = prev.length >= MAX_TRAIL ? prev.slice(1) : prev;
      return { gpsTrails: { ...s.gpsTrails, [nodeId]: [...next, [lon, lat]] } };
    }),

  addViconPoint: (nodeId, x, y) =>
    set((s) => {
      const prev = s.viconTrails[nodeId] ?? [];
      const next = prev.length >= MAX_TRAIL ? prev.slice(1) : prev;
      return { viconTrails: { ...s.viconTrails, [nodeId]: [...next, [x, y]] } };
    }),

  clearTrails: () => set({ gpsTrails: {}, viconTrails: {} }),
}));
