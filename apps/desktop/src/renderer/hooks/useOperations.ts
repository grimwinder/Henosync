import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { getOperations, startOperation, stopOperation } from "../lib/api";

export const OPERATION_KEYS = {
  all: ["operations"] as const,
};

export function useOperations() {
  return useQuery({
    queryKey: OPERATION_KEYS.all,
    queryFn: getOperations,
    refetchInterval: 2_000,
  });
}

export function useStartOperation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      plugin_id,
      config,
    }: {
      plugin_id: string;
      config?: Record<string, unknown>;
    }) => startOperation(plugin_id, config),
    onSuccess: () => qc.invalidateQueries({ queryKey: OPERATION_KEYS.all }),
  });
}

export function useStopOperation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (plugin_id: string) => stopOperation(plugin_id),
    onSuccess: () => qc.invalidateQueries({ queryKey: OPERATION_KEYS.all }),
  });
}
