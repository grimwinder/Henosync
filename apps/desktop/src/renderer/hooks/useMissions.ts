import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../lib/api";
import { useMissionStore } from "../stores";
import type { MissionCreate, MissionUpdate } from "../types";

export const MISSION_KEYS = {
  all: ["missions"] as const,
  detail: (id: string) => ["missions", id] as const,
  engineStatus: ["missions", "engine", "status"] as const,
};

export function useMissions() {
  return useQuery({ queryKey: MISSION_KEYS.all, queryFn: api.getMissions });
}

export function useMission(id: string) {
  return useQuery({
    queryKey: MISSION_KEYS.detail(id),
    queryFn: () => api.getMission(id),
    enabled: !!id,
  });
}

export function useMissionEngineStatus() {
  const setEngineStatus = useMissionStore((s) => s.setEngineStatus);
  return useQuery({
    queryKey: MISSION_KEYS.engineStatus,
    queryFn: async () => {
      const status = await api.getMissionEngineStatus();
      setEngineStatus(status);
      return status;
    },
    refetchInterval: 2_000,
  });
}

export function useCreateMission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MissionCreate) => api.createMission(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: MISSION_KEYS.all }),
  });
}

export function useUpdateMission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: MissionUpdate }) =>
      api.updateMission(id, body),
    onSuccess: (_, { id }) => {
      qc.invalidateQueries({ queryKey: MISSION_KEYS.all });
      qc.invalidateQueries({ queryKey: MISSION_KEYS.detail(id) });
    },
  });
}

export function useDeleteMission() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteMission(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: MISSION_KEYS.all }),
  });
}

export function useExecuteMission() {
  const qc = useQueryClient();
  const setEngineStatus = useMissionStore((s) => s.setEngineStatus);
  return useMutation({
    mutationFn: (id: string) => api.executeMission(id),
    onSuccess: (data) => {
      setEngineStatus(data.status);
      qc.invalidateQueries({ queryKey: MISSION_KEYS.engineStatus });
    },
  });
}

export function usePauseMission() {
  const setEngineStatus = useMissionStore((s) => s.setEngineStatus);
  return useMutation({
    mutationFn: (id: string) => api.pauseMission(id),
    onSuccess: (data) => setEngineStatus(data.status),
  });
}

export function useResumeMission() {
  const setEngineStatus = useMissionStore((s) => s.setEngineStatus);
  return useMutation({
    mutationFn: (id: string) => api.resumeMission(id),
    onSuccess: (data) => setEngineStatus(data.status),
  });
}

export function useAbortMission() {
  const setEngineStatus = useMissionStore((s) => s.setEngineStatus);
  return useMutation({
    mutationFn: (id: string) => api.abortMission(id),
    onSuccess: (data) => setEngineStatus(data.status),
  });
}
