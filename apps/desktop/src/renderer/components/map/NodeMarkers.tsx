import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { useNodeStore } from "../../stores/nodeStore";
import type { Node } from "../../types";

const STATUS_COLOR: Record<string, string> = {
  online: "#3DD68C",
  connecting: "#F5A623",
  degraded: "#F5A623",
  offline: "#999999",
  error: "#F05252",
};

function buildMarkerEl(node: Node, selected: boolean): HTMLDivElement {
  const color = STATUS_COLOR[node.status] ?? "#999999";

  // Wrapper: 14×14 centered at the coordinate; label floats below absolutely
  const wrap = document.createElement("div");
  wrap.style.cssText =
    "position:relative;width:14px;height:14px;cursor:pointer;";

  const dot = document.createElement("div");
  dot.style.cssText = `
    width: 14px;
    height: 14px;
    border-radius: 50%;
    background-color: ${color};
    border: 2px solid ${selected ? "#4A9EFF" : "#0D0D0D"};
    box-shadow: 0 0 ${selected ? "10px 2px #4A9EFF80" : `6px 1px ${color}60`};
    transition: border-color 150ms, box-shadow 150ms;
  `;

  const label = document.createElement("div");
  label.textContent = node.name;
  label.style.cssText = `
    position: absolute;
    top: 18px;
    left: 50%;
    transform: translateX(-50%);
    font-family: Inter, sans-serif;
    font-size: 10px;
    font-weight: 500;
    color: #EFEFEF;
    background-color: rgba(13,15,18,0.88);
    padding: 2px 6px;
    border-radius: 3px;
    white-space: nowrap;
    border: 1px solid #2D2D2D;
    pointer-events: none;
    user-select: none;
  `;

  wrap.appendChild(dot);
  wrap.appendChild(label);
  return wrap;
}

interface NodeMarkersProps {
  map: maplibregl.Map;
}

export default function NodeMarkers({ map }: NodeMarkersProps) {
  const nodes = useNodeStore((s) => s.nodes);
  const selectedId = useNodeStore((s) => s.selectedNodeId);
  const setSelected = useNodeStore((s) => s.setSelectedNode);
  const markersRef = useRef<Record<string, maplibregl.Marker>>({});

  useEffect(() => {
    const active = new Set<string>();

    for (const node of Object.values(nodes)) {
      const { lat, lon } = node.position;
      if (lat === 0 && lon === 0) continue;

      active.add(node.id);

      // Remove stale marker so we can rebuild with fresh state
      markersRef.current[node.id]?.remove();

      const el = buildMarkerEl(node, node.id === selectedId);
      el.addEventListener("click", () => setSelected(node.id));

      markersRef.current[node.id] = new maplibregl.Marker({
        element: el,
        anchor: "center",
      })
        .setLngLat([lon, lat])
        .addTo(map);
    }

    // Remove markers for nodes that no longer exist or have no position
    for (const id of Object.keys(markersRef.current)) {
      if (!active.has(id)) {
        markersRef.current[id].remove();
        delete markersRef.current[id];
      }
    }
  }, [nodes, selectedId, map, setSelected]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      for (const m of Object.values(markersRef.current)) m.remove();
      markersRef.current = {};
    };
  }, []);

  return null;
}
