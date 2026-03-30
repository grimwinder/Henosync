import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import * as api from "../lib/api";
import { useNodeStore } from "../stores/nodeStore";
import type { NodeCreate } from "../types";

export const NODE_KEYS = {
  all: ["nodes"] as const,
  detail: (id: string) => ["nodes", id] as const,
  streamUrl: (id: string) => ["nodes", id, "stream_url"] as const,
};

export function useNodes() {
  const setNodes = useNodeStore((s) => s.setNodes);
  return useQuery({
    queryKey: NODE_KEYS.all,
    queryFn: async () => {
      const nodes = await api.getNodes();
      setNodes(nodes);
      return nodes;
    },
    refetchInterval: 5_000,
  });
}

export function useNode(id: string) {
  return useQuery({
    queryKey: NODE_KEYS.detail(id),
    queryFn: () => api.getNode(id),
  });
}

export function useStreamUrl(id: string) {
  return useQuery({
    queryKey: NODE_KEYS.streamUrl(id),
    queryFn: () => api.getStreamUrl(id),
    staleTime: Infinity,
  });
}

export function useAddNode() {
  const qc = useQueryClient();
  const upsertNode = useNodeStore((s) => s.upsertNode);
  return useMutation({
    mutationFn: (body: NodeCreate) => api.addNode(body),
    onSuccess: (node) => {
      upsertNode(node);
      qc.invalidateQueries({ queryKey: NODE_KEYS.all });
    },
  });
}

export function useRemoveNode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.removeNode(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: NODE_KEYS.all }),
  });
}

export function useReconnectNode() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.reconnectNode(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: NODE_KEYS.all }),
  });
}

export function useSendCommand() {
  return useMutation({
    mutationFn: ({
      nodeId,
      capability,
      params,
    }: {
      nodeId: string;
      capability: string;
      params?: Record<string, unknown>;
    }) => api.sendCommand(nodeId, capability, params),
  });
}
