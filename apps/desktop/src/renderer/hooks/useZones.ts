import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../lib/api";
import type { ZoneCreate } from "../types";

export const ZONE_KEYS = {
  all: ["zones"] as const,
};

export function useZones() {
  return useQuery({ queryKey: ZONE_KEYS.all, queryFn: api.getZones });
}

export function useCreateZone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ZoneCreate) => api.createZone(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ZONE_KEYS.all }),
  });
}

export function useDeleteZone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteZone(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ZONE_KEYS.all }),
  });
}
