import { useEffect, useRef } from "react";
import { useNodeStore } from "../stores/nodeStore";
import { useTrailStore } from "../stores/trailStore";
import { useOperations } from "./useOperations";

/**
 * Records device trails while any operation is running.
 * Clears trails when a new operation starts.
 * Call once from App.tsx so it runs regardless of which page is visible.
 */
export function useTrailRecorder() {
  const nodes = useNodeStore((s) => s.nodes);
  const { data: operations = [] } = useOperations();
  const { addGpsPoint, addViconPoint, clearTrails } = useTrailStore();
  const prevOpKeysRef = useRef<string>("");
  const skipRef = useRef(false);

  // Clear trails when a new operation starts
  useEffect(() => {
    const keys = operations
      .map((o) => o.plugin_id)
      .sort()
      .join(",");
    if (keys && keys !== prevOpKeysRef.current) {
      clearTrails();
    }
    prevOpKeysRef.current = keys;
  }, [operations, clearTrails]);

  // Record positions while any operation is running (every other node update)
  useEffect(() => {
    if (operations.length === 0) return;
    skipRef.current = !skipRef.current;
    if (skipRef.current) return;
    for (const node of Object.values(nodes)) {
      if (node.status !== "online" && node.status !== "degraded") continue;

      const t = node.telemetry as Record<string, unknown> | null;

      // VICON trail — uses vicon_x/vicon_y published by vicon_manager
      const vx = t?.vicon_x;
      const vy = t?.vicon_y;
      if (typeof vx === "number" && typeof vy === "number") {
        addViconPoint(node.id, vx, vy);
      }

      // GPS trail
      if (node.position.lat !== 0 || node.position.lon !== 0) {
        addGpsPoint(node.id, node.position.lon, node.position.lat);
      }
    }
  }, [nodes, operations, addGpsPoint, addViconPoint]);
}
