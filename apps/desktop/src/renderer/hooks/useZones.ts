import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getZones, createZone, deleteZone } from "../lib/api";
import { useZoneStore } from "../stores/zoneStore";
import { useUIStore } from "../stores/uiStore";
import type { ZoneCreate } from "../types";

export const ZONE_KEYS = {
  all: ["zones"] as const,
  byMode: (mode: string) => ["zones", mode] as const,
};

export function useZones(mode?: string) {
  const setZones = useZoneStore((s) => s.setZones);
  const mapMode = useUIStore((s) => s.mapMode);
  const resolvedMode = mode ?? mapMode;
  return useQuery({
    queryKey: ZONE_KEYS.byMode(resolvedMode),
    queryFn: async () => {
      const zones = await getZones(resolvedMode);
      setZones(zones);
      return zones;
    },
    refetchInterval: 10_000,
  });
}

export function useCreateZone() {
  const qc = useQueryClient();
  const upsertZone = useZoneStore((s) => s.upsertZone);
  const mapMode = useUIStore((s) => s.mapMode);
  return useMutation({
    mutationFn: (body: ZoneCreate) =>
      createZone({ ...body, map_mode: body.map_mode ?? mapMode }),
    onSuccess: (zone) => {
      upsertZone(zone);
      qc.invalidateQueries({ queryKey: ZONE_KEYS.byMode(mapMode) });
    },
  });
}

export function useDeleteZone() {
  const qc = useQueryClient();
  const removeZone = useZoneStore((s) => s.removeZone);
  const mapMode = useUIStore((s) => s.mapMode);
  return useMutation({
    mutationFn: (id: string) => deleteZone(id),
    onSuccess: (_, id) => {
      removeZone(id);
      qc.invalidateQueries({ queryKey: ZONE_KEYS.byMode(mapMode) });
    },
  });
}
