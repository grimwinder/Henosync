import { X, MapPin } from "lucide-react";
import { useMarkerStore } from "../../stores/markerStore";
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

function StatBox({
  label,
  value,
  style,
}: {
  label: string;
  value: string;
  style?: React.CSSProperties;
}) {
  return (
    <div
      style={{
        padding: "8px 10px",
        backgroundColor: "#1C1C1C",
        borderRadius: "6px",
        ...style,
      }}
    >
      <div style={{ fontSize: "10px", color: "#999999", marginBottom: "3px" }}>
        {label}
      </div>
      <div
        style={{
          fontSize: "13px",
          fontWeight: 600,
          color: "#EFEFEF",
          fontFamily: "Inter, sans-serif",
        }}
      >
        {value}
      </div>
    </div>
  );
}

export default function MarkerDetailPanel() {
  const selectedMarkerId = useMarkerStore((s) => s.selectedMarkerId);
  const markers = useMarkerStore((s) => s.markers);
  const setSelectedMarker = useMarkerStore((s) => s.setSelectedMarker);

  const marker = selectedMarkerId ? markers[selectedMarkerId] : null;
  if (!marker) return null;

  const color =
    marker.color ||
    MARKER_TYPE_COLORS[marker.marker_type as MarkerType] ||
    "#999999";

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        right: 0,
        height: "100%",
        width: "260px",
        backgroundColor: "#141414",
        borderLeft: "1px solid #2D2D2D",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 14px",
          backgroundColor: "#0D0D0D",
          borderBottom: "1px solid #2D2D2D",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                marginBottom: "3px",
              }}
            >
              <MapPin size={10} color={color} style={{ flexShrink: 0 }} />
              <span
                style={{
                  fontSize: "12px",
                  fontWeight: 600,
                  color: "#EFEFEF",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {marker.name}
              </span>
            </div>
            <div style={{ fontSize: "10px", color: "#999999" }}>
              {MARKER_TYPE_LABELS[marker.marker_type as MarkerType] ??
                marker.marker_type}
            </div>
          </div>
          <button
            onClick={() => setSelectedMarker(null)}
            title="Close"
            style={{
              background: "none",
              border: "none",
              color: "#999999",
              cursor: "pointer",
              padding: "2px",
              display: "flex",
              flexShrink: 0,
              marginLeft: "8px",
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
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflowY: "auto", padding: "10px 14px" }}>
        <div
          style={{
            fontSize: "10px",
            fontWeight: 600,
            letterSpacing: "1px",
            color: "#999999",
            marginBottom: "8px",
          }}
        >
          POSITION
        </div>

        {/* Lat/Lon rows */}
        {[
          { label: "LAT", value: `${marker.lat.toFixed(6)}°` },
          { label: "LON", value: `${marker.lon.toFixed(6)}°` },
        ].map(({ label, value }) => (
          <div
            key={label}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "10px",
              padding: "7px 0",
              borderBottom: "1px solid #1C1C1C",
            }}
          >
            <div
              style={{
                width: "28px",
                height: "20px",
                borderRadius: "3px",
                backgroundColor: `${color}22`,
                border: `1px solid ${color}`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <span
                style={{
                  fontSize: "8px",
                  fontWeight: 700,
                  color,
                  fontFamily: "Inter, sans-serif",
                }}
              >
                {label}
              </span>
            </div>
            <div
              style={{
                fontSize: "12px",
                color: "#EFEFEF",
                fontFamily: "Inter, sans-serif",
              }}
            >
              {value}
            </div>
          </div>
        ))}

        <StatBox
          label="TYPE"
          value={
            MARKER_TYPE_LABELS[marker.marker_type as MarkerType] ??
            marker.marker_type
          }
          style={{ marginTop: "12px" }}
        />
      </div>
    </div>
  );
}
