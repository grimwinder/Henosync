import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getMarkers, createMarker, deleteMarker } from "../lib/api";
import { useMarkerStore } from "../stores/markerStore";
import { useUIStore } from "../stores/uiStore";
import type { MapMarkerCreate } from "../types";

export const MARKER_KEYS = {
  all: ["markers"] as const,
  byMode: (mode: string) => ["markers", mode] as const,
};

export function useMarkers(mode?: string) {
  const setMarkers = useMarkerStore((s) => s.setMarkers);
  const mapMode = useUIStore((s) => s.mapMode);
  const resolvedMode = mode ?? mapMode;
  return useQuery({
    queryKey: MARKER_KEYS.byMode(resolvedMode),
    queryFn: async () => {
      const markers = await getMarkers(resolvedMode);
      setMarkers(markers);
      return markers;
    },
    refetchInterval: 30_000,
  });
}

export function useCreateMarker() {
  const qc = useQueryClient();
  const upsertMarker = useMarkerStore((s) => s.upsertMarker);
  const mapMode = useUIStore((s) => s.mapMode);
  return useMutation({
    mutationFn: (body: MapMarkerCreate) =>
      createMarker({ ...body, map_mode: body.map_mode ?? mapMode }),
    onSuccess: (marker) => {
      upsertMarker(marker);
      qc.invalidateQueries({ queryKey: MARKER_KEYS.byMode(mapMode) });
    },
  });
}

export function useDeleteMarker() {
  const qc = useQueryClient();
  const removeMarker = useMarkerStore((s) => s.removeMarker);
  const mapMode = useUIStore((s) => s.mapMode);
  return useMutation({
    mutationFn: (id: string) => deleteMarker(id),
    onSuccess: (_, id) => {
      removeMarker(id);
      qc.invalidateQueries({ queryKey: MARKER_KEYS.byMode(mapMode) });
    },
  });
}
