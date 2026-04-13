import { useState } from "react";
import { X } from "lucide-react";
import { useCreateMarker } from "../../hooks/useMarkers";
import type { MarkerType } from "../../types";

const MARKER_TYPE_LABELS: Record<MarkerType, string> = {
  home_position: "Home Position",
  waypoint: "Waypoint",
  reference: "Reference",
  hazard: "Hazard",
  custom: "Custom",
};

const MARKER_TYPE_COLORS: Record<MarkerType, string> = {
  home_position: "#3DD68C",
  waypoint: "#4A9EFF",
  reference: "#A78BFA",
  hazard: "#F05252",
  custom: "#F5A623",
};

interface PlaceMarkerModalProps {
  lat: number;
  lon: number;
  onClose: () => void;
}

export default function PlaceMarkerModal({
  lat,
  lon,
  onClose,
}: PlaceMarkerModalProps) {
  const [name, setName] = useState("");
  const [markerType, setMarkerType] = useState<MarkerType>("waypoint");
  const { mutate: createMarker, isPending } = useCreateMarker();

  function handleCreate() {
    if (!name.trim()) return;
    createMarker(
      {
        name: name.trim(),
        marker_type: markerType,
        lat,
        lon,
        color: MARKER_TYPE_COLORS[markerType],
      },
      { onSuccess: onClose },
    );
  }

  return (
    <div
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: "#141414",
          border: "1px solid #2D2D2D",
          borderRadius: "10px",
          width: "300px",
          display: "flex",
          flexDirection: "column",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: "12px 14px",
            borderBottom: "1px solid #2D2D2D",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#999999",
            }}
          >
            PLACE MARKER
          </span>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              color: "#999999",
              cursor: "pointer",
              padding: "2px",
              display: "flex",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = "#EFEFEF";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.color = "#999999";
            }}
          >
            <X size={14} />
          </button>
        </div>

        <div style={{ padding: "14px" }}>
          {/* Coords */}
          <div
            style={{
              fontSize: "10px",
              color: "#999999",
              marginBottom: "12px",
              fontFamily: "Inter, sans-serif",
            }}
          >
            {lat.toFixed(6)}°, {lon.toFixed(6)}°
          </div>

          {/* Name */}
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#999999",
              marginBottom: "6px",
            }}
          >
            NAME
          </div>
          <input
            autoFocus
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleCreate();
            }}
            placeholder="Enter name…"
            style={{
              width: "100%",
              boxSizing: "border-box",
              padding: "7px 10px",
              borderRadius: "5px",
              border: "1px solid #2D2D2D",
              backgroundColor: "#1C1C1C",
              color: "#EFEFEF",
              fontSize: "12px",
              outline: "none",
              marginBottom: "14px",
            }}
          />

          {/* Type */}
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#999999",
              marginBottom: "8px",
            }}
          >
            TYPE
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "6px",
              marginBottom: "16px",
            }}
          >
            {(Object.entries(MARKER_TYPE_LABELS) as [MarkerType, string][]).map(
              ([type, label]) => {
                const active = markerType === type;
                const color = MARKER_TYPE_COLORS[type];
                return (
                  <button
                    key={type}
                    onClick={() => setMarkerType(type)}
                    style={{
                      padding: "6px 8px",
                      borderRadius: "5px",
                      border: `1px solid ${active ? color : "#2D2D2D"}`,
                      backgroundColor: active ? `${color}22` : "transparent",
                      color: active ? color : "#999999",
                      fontSize: "11px",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "all 150ms",
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                    }}
                  >
                    <div
                      style={{
                        width: "7px",
                        height: "7px",
                        borderRadius: "50%",
                        backgroundColor: color,
                        flexShrink: 0,
                      }}
                    />
                    {label}
                  </button>
                );
              },
            )}
          </div>

          {/* Create */}
          <button
            onClick={handleCreate}
            disabled={!name.trim() || isPending}
            style={{
              width: "100%",
              padding: "9px",
              borderRadius: "6px",
              border: "none",
              backgroundColor:
                name.trim() && !isPending
                  ? MARKER_TYPE_COLORS[markerType]
                  : "#2D2D2D",
              color: name.trim() && !isPending ? "#fff" : "#999999",
              fontSize: "12px",
              fontWeight: 600,
              cursor: name.trim() && !isPending ? "pointer" : "not-allowed",
              transition: "background-color 150ms",
            }}
          >
            {isPending ? "Placing…" : "Place Marker"}
          </button>
        </div>
      </div>
    </div>
  );
}
