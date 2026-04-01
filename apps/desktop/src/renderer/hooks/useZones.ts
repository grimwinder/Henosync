import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../lib/api";
import { useZoneStore } from "../stores/zoneStore";
import type { ZoneCreate } from "../types";

export const ZONE_KEYS = {
  all: ["zones"] as const,
};

export function useZones() {
  const setZones = useZoneStore((s) => s.setZones);
  return useQuery({
    queryKey: ZONE_KEYS.all,
    queryFn: async () => {
      const zones = await api.getZones();
      setZones(zones);
      return zones;
    },
    refetchInterval: 10_000,
  });
}

export function useCreateZone() {
  const qc = useQueryClient();
  const upsertZone = useZoneStore((s) => s.upsertZone);
  return useMutation({
    mutationFn: (body: ZoneCreate) => api.createZone(body),
    onSuccess: (zone) => {
      upsertZone(zone);
      qc.invalidateQueries({ queryKey: ZONE_KEYS.all });
    },
  });
}

export function useDeleteZone() {
  const qc = useQueryClient();
  const removeZone = useZoneStore((s) => s.removeZone);
  return useMutation({
    mutationFn: (id: string) => api.deleteZone(id),
    onSuccess: (_, id) => {
      removeZone(id);
      qc.invalidateQueries({ queryKey: ZONE_KEYS.all });
    },
  });
}
