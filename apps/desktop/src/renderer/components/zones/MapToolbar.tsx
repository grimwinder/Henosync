import {
  Pentagon,
  Circle,
  Combine,
  Eye,
  EyeOff,
  MapPin,
  Ruler,
} from "lucide-react";
import type { DrawMode } from "../../pages/ZonesPage";
import { useZoneStore } from "../../stores/zoneStore";

interface MapToolbarProps {
  drawMode: DrawMode;
  onSetDrawMode: (mode: DrawMode) => void;
}

interface ToolButtonProps {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}

function ToolButton({ icon, label, active, onClick }: ToolButtonProps) {
  return (
    <button
      onClick={onClick}
      title={label}
      style={{
        width: "32px",
        height: "32px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "5px",
        border: `1px solid ${active ? "#4A9EFF" : "transparent"}`,
        backgroundColor: active ? "#4A9EFF22" : "transparent",
        color: active ? "#4A9EFF" : "#8B95A3",
        cursor: "pointer",
        transition: "all 150ms",
        flexShrink: 0,
      }}
      onMouseEnter={(e) => {
        if (!active) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "#1C1F24";
          (e.currentTarget as HTMLButtonElement).style.color = "#E8EAED";
        }
      }}
      onMouseLeave={(e) => {
        if (!active) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "transparent";
          (e.currentTarget as HTMLButtonElement).style.color = "#8B95A3";
        }
      }}
    >
      {icon}
    </button>
  );
}

export default function MapToolbar({
  drawMode,
  onSetDrawMode,
}: MapToolbarProps) {
  const showVertexMarkers = useZoneStore((s) => s.showVertexMarkers);
  const setShowVertexMarkers = useZoneStore((s) => s.setShowVertexMarkers);

  return (
    <div
      style={{
        position: "absolute",
        top: "12px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 20,
        display: "flex",
        alignItems: "center",
        gap: "2px",
        backgroundColor: "#141619",
        border: "1px solid #2A2F38",
        borderRadius: "8px",
        padding: "4px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
      }}
    >
      <ToolButton
        icon={<Pentagon size={15} />}
        label="Draw polygon zone"
        active={drawMode === "polygon"}
        onClick={() => onSetDrawMode(drawMode === "polygon" ? null : "polygon")}
      />
      <ToolButton
        icon={<Circle size={15} />}
        label="Draw circle zone"
        active={drawMode === "circle"}
        onClick={() => onSetDrawMode(drawMode === "circle" ? null : "circle")}
      />
      <ToolButton
        icon={<Combine size={15} />}
        label="Merge zones"
        active={drawMode === "merge"}
        onClick={() => onSetDrawMode(drawMode === "merge" ? null : "merge")}
      />
      <ToolButton
        icon={<MapPin size={15} />}
        label="Place marker"
        active={drawMode === "marker"}
        onClick={() => onSetDrawMode(drawMode === "marker" ? null : "marker")}
      />
      <ToolButton
        icon={<Ruler size={15} />}
        label="Measure distance"
        active={drawMode === "measure"}
        onClick={() => onSetDrawMode(drawMode === "measure" ? null : "measure")}
      />

      {/* Divider */}
      <div
        style={{
          width: "1px",
          height: "20px",
          backgroundColor: "#2A2F38",
          margin: "0 2px",
          flexShrink: 0,
        }}
      />

      <ToolButton
        icon={showVertexMarkers ? <Eye size={15} /> : <EyeOff size={15} />}
        label={
          showVertexMarkers ? "Hide vertex markers" : "Show vertex markers"
        }
        active={false}
        onClick={() => setShowVertexMarkers(!showVertexMarkers)}
      />

      {/* Hint when drawing */}
      {(drawMode === "polygon" || drawMode === "circle") && (
        <>
          <div
            style={{
              width: "1px",
              height: "20px",
              backgroundColor: "#2A2F38",
              margin: "0 4px",
              flexShrink: 0,
            }}
          />
          <span
            style={{
              fontSize: "10px",
              color: "#F5A623",
              paddingRight: "6px",
              whiteSpace: "nowrap",
            }}
          >
            {drawMode === "polygon"
              ? "Click to add points · Double-click to finish · Esc to cancel"
              : "Click to set centre · Click again to set radius · Esc to cancel"}
          </span>
        </>
      )}
    </div>
  );
}
