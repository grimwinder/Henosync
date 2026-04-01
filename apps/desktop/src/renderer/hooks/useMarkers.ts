import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../lib/api";
import { useMarkerStore } from "../stores/markerStore";
import type { MapMarkerCreate } from "../types";

export const MARKER_KEYS = {
  all: ["markers"] as const,
};

export function useMarkers() {
  const setMarkers = useMarkerStore((s) => s.setMarkers);
  return useQuery({
    queryKey: MARKER_KEYS.all,
    queryFn: async () => {
      const markers = await api.getMarkers();
      setMarkers(markers);
      return markers;
    },
    refetchInterval: 30_000,
  });
}

export function useCreateMarker() {
  const qc = useQueryClient();
  const upsertMarker = useMarkerStore((s) => s.upsertMarker);
  return useMutation({
    mutationFn: (body: MapMarkerCreate) => api.createMarker(body),
    onSuccess: (marker) => {
      upsertMarker(marker);
      qc.invalidateQueries({ queryKey: MARKER_KEYS.all });
    },
  });
}

export function useDeleteMarker() {
  const qc = useQueryClient();
  const removeMarker = useMarkerStore((s) => s.removeMarker);
  return useMutation({
    mutationFn: (id: string) => api.deleteMarker(id),
    onSuccess: (_, id) => {
      removeMarker(id);
      qc.invalidateQueries({ queryKey: MARKER_KEYS.all });
    },
  });
}
