import { create } from "zustand";
import type { Node } from "../types";

interface NodeStore {
  // State
  nodes: Record<string, Node>;
  selectedNodeId: string | null;

  // Actions
  setNodes: (nodes: Node[]) => void;
  upsertNode: (node: Node) => void;
  removeNode: (id: string) => void;
  setSelectedNode: (id: string | null) => void;
  updateTelemetry: (nodeId: string, values: Record<string, unknown>) => void;
}

export const useNodeStore = create<NodeStore>((set) => ({
  nodes: {},
  selectedNodeId: null,

  setNodes: (nodes) =>
    set({ nodes: Object.fromEntries(nodes.map((n) => [n.id, n])) }),

  upsertNode: (node) =>
    set((s) => ({ nodes: { ...s.nodes, [node.id]: node } })),

  removeNode: (id) =>
    set((s) => {
      const nodes = { ...s.nodes };
      delete nodes[id];
      return {
        nodes,
        selectedNodeId: s.selectedNodeId === id ? null : s.selectedNodeId,
      };
    }),

  setSelectedNode: (id) => set({ selectedNodeId: id }),

  updateTelemetry: (nodeId, values) =>
    set((s) => {
      const node = s.nodes[nodeId];
      if (!node) return s;
      const updated: Node = {
        ...node,
        telemetry: { ...node.telemetry, ...values },
        battery_percent:
          typeof values.battery_percent === "number"
            ? values.battery_percent
            : node.battery_percent,
        signal_strength:
          typeof values.signal_strength === "number"
            ? values.signal_strength
            : node.signal_strength,
        position:
          typeof values.lat === "number" && typeof values.lon === "number"
            ? {
                ...node.position,
                lat: values.lat as number,
                lon: values.lon as number,
                alt:
                  typeof values.alt === "number"
                    ? (values.alt as number)
                    : node.position.alt,
              }
            : node.position,
      };
      return { nodes: { ...s.nodes, [nodeId]: updated } };
    }),
}));
