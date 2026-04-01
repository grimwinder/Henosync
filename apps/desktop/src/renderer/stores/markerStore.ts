import { create } from "zustand";
import type { MapMarker } from "../types";

interface MarkerStore {
  markers: Record<string, MapMarker>;
  selectedMarkerId: string | null;
  setMarkers: (markers: MapMarker[]) => void;
  upsertMarker: (marker: MapMarker) => void;
  removeMarker: (id: string) => void;
  setSelectedMarker: (id: string | null) => void;
}

export const useMarkerStore = create<MarkerStore>((set) => ({
  markers: {},
  selectedMarkerId: null,

  setMarkers: (markers) =>
    set({ markers: Object.fromEntries(markers.map((m) => [m.id, m])) }),

  upsertMarker: (marker) =>
    set((s) => ({ markers: { ...s.markers, [marker.id]: marker } })),

  removeMarker: (id) =>
    set((s) => {
      const markers = { ...s.markers };
      delete markers[id];
      return {
        markers,
        selectedMarkerId: s.selectedMarkerId === id ? null : s.selectedMarkerId,
      };
    }),

  setSelectedMarker: (id) => set({ selectedMarkerId: id }),
}));
