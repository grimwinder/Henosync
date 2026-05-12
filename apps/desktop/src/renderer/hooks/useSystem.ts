import { useQuery, useMutation } from "@tanstack/react-query";
import { getHealth, emergencyStop } from "../lib/api";
import { useSystemStore } from "../stores";

export function useHealth() {
  const setHealth = useSystemStore((s) => s.setHealth);
  const setBackendConnected = useSystemStore((s) => s.setBackendConnected);
  return useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      try {
        const health = await getHealth();
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
  return useMutation({ mutationFn: emergencyStop });
}
