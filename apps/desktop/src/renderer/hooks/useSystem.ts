import { useQuery, useMutation } from "@tanstack/react-query";
import * as api from "../lib/api";
import { useSystemStore } from "../stores";
import type { MissionEngineStatus } from "../types";

export function useHealth() {
  const setHealth = useSystemStore((s) => s.setHealth);
  const setBackendConnected = useSystemStore((s) => s.setBackendConnected);
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      try {
        const health = await api.getHealth();
        setHealth(health);
        return health;
      } catch (err) {
        setBackendConnected(false);
        throw err;
      }
    },
    refetchInterval: 5_000,
    retry: false,
  });
}

export function useEmergencyStop() {
  return useMutation({ mutationFn: api.emergencyStop });
}

export function useMissionEngineStatus() {
  return useQuery<MissionEngineStatus>({
    queryKey: ["mission-engine-status"],
    queryFn: api.getMissionEngineStatus,
    refetchInterval: 2_000,
    retry: false,
  });
}
