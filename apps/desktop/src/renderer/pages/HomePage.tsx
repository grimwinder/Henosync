import { useState } from "react";
import maplibregl from "maplibre-gl";
import { useNodeStore } from "../stores/nodeStore";
import DevicePanel from "../components/fleet/DevicePanel";
import DeviceDetailPanel from "../components/fleet/DeviceDetailPanel";
import MissionMap from "../components/map/MissionMap";
import NodeMarkers from "../components/map/NodeMarkers";

export default function HomePage() {
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const nodes = useNodeStore((s) => s.nodes);
  const selectedNode = selectedNodeId ? nodes[selectedNodeId] : null;
  const [map, setMap] = useState<maplibregl.Map | null>(null);

  return (
    <div
      style={{
        display: "flex",
        flex: 1,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Map fills the entire background */}
      <div style={{ position: "absolute", inset: 0 }}>
        <MissionMap onMapReady={setMap} />
        {map && <NodeMarkers map={map} />}
      </div>

      {/* Fleet panel — top-left, half height */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: "50%",
          zIndex: 10,
        }}
      >
        <DevicePanel />
      </div>

      {/* Detail panel — right side, full height */}
      {selectedNode && (
        <div
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            height: "100%",
            zIndex: 10,
          }}
        >
          <DeviceDetailPanel node={selectedNode} />
        </div>
      )}
    </div>
  );
}
