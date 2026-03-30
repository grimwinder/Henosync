import { create } from "zustand";
import type { RunningOperation } from "../types";

interface OperationStore {
  // State
  operations: Record<string, RunningOperation>;

  // Actions
  setOperations: (ops: RunningOperation[]) => void;
  upsertOperation: (op: RunningOperation) => void;
  removeOperation: (pluginId: string) => void;
}

export const useOperationStore = create<OperationStore>((set) => ({
  operations: {},

  setOperations: (ops) =>
    set({
      operations: Object.fromEntries(ops.map((o) => [o.plugin_id, o])),
    }),

  upsertOperation: (op) =>
    set((s) => ({ operations: { ...s.operations, [op.plugin_id]: op } })),

  removeOperation: (pluginId) =>
    set((s) => {
      const operations = { ...s.operations };
      delete operations[pluginId];
      return { operations };
    }),
}));
