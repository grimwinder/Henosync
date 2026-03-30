import { create } from "zustand";
import type { Zone } from "../types";

interface ZoneStore {
  // State
  zones: Record<string, Zone>;
  selectedZoneId: string | null;

  // Actions
  setZones: (zones: Zone[]) => void;
  upsertZone: (zone: Zone) => void;
  removeZone: (id: string) => void;
  setSelectedZone: (id: string | null) => void;
}

export const useZoneStore = create<ZoneStore>((set) => ({
  zones: {},
  selectedZoneId: null,

  setZones: (zones) =>
    set({ zones: Object.fromEntries(zones.map((z) => [z.id, z])) }),

  upsertZone: (zone) =>
    set((s) => ({ zones: { ...s.zones, [zone.id]: zone } })),

  removeZone: (id) =>
    set((s) => {
      const zones = { ...s.zones };
      delete zones[id];
      return {
        zones,
        selectedZoneId: s.selectedZoneId === id ? null : s.selectedZoneId,
      };
    }),

  setSelectedZone: (id) => set({ selectedZoneId: id }),
}));
