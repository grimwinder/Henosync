import { create } from "zustand";

const MAX_TRAIL = 2000;

interface TrailStore {
  gpsTrails: Record<string, Array<[number, number]>>; // node_id → [[lon, lat], ...]
  // node_id → [[x_m, y_m], ...]; null marks a gap (link dropout) in the trail
  viconTrails: Record<string, Array<[number, number] | null>>;
  // node_id → segments of [x_m, y_m] the robot logged itself while the link was down
  viconOfflineTrails: Record<string, Array<Array<[number, number]>>>;
  addGpsPoint: (nodeId: string, lon: number, lat: number) => void;
  addViconPoint: (nodeId: string, x: number, y: number) => void;
  addViconBreak: (nodeId: string) => void;
  addViconOfflineSegments: (
    nodeId: string,
    segments: Array<Array<[number, number]>>,
  ) => void;
  clearTrails: () => void;
}

export const useTrailStore = create<TrailStore>((set) => ({
  gpsTrails: {},
  viconTrails: {},
  viconOfflineTrails: {},

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

  addViconBreak: (nodeId) =>
    set((s) => {
      const prev = s.viconTrails[nodeId] ?? [];
      if (prev.length === 0 || prev[prev.length - 1] === null) return s;
      return { viconTrails: { ...s.viconTrails, [nodeId]: [...prev, null] } };
    }),

  addViconOfflineSegments: (nodeId, segments) =>
    set((s) => ({
      viconOfflineTrails: {
        ...s.viconOfflineTrails,
        [nodeId]: [...(s.viconOfflineTrails[nodeId] ?? []), ...segments],
      },
    })),

  clearTrails: () => set({ gpsTrails: {}, viconTrails: {}, viconOfflineTrails: {} }),
}));
