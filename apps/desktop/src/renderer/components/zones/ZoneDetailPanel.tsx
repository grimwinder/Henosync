import { X } from "lucide-react";
import { useZoneStore } from "../../stores/zoneStore";
import type { ZoneType, GeoPoint } from "../../types";

function polygonAreaM2(points: GeoPoint[]): number {
  if (points.length < 3) return 0;
  const R = 6371000;
  const lat0 = (points[0].lat * Math.PI) / 180;
  let area = 0;
  for (let i = 0; i < points.length; i++) {
    const j = (i + 1) % points.length;
    const xi = ((points[i].lon * Math.PI) / 180) * R * Math.cos(lat0);
    const yi = ((points[i].lat * Math.PI) / 180) * R;
    const xj = ((points[j].lon * Math.PI) / 180) * R * Math.cos(lat0);
    const yj = ((points[j].lat * Math.PI) / 180) * R;
    area += xi * yj - xj * yi;
  }
  return Math.abs(area / 2);
}

function formatArea(m2: number): string {
  return `${m2.toFixed(1)} m²`;
}

const ZONE_TYPE_LABELS: Record<ZoneType, string> = {
  perimeter: "Perimeter",
  no_go: "No-Go",
  safe_return: "Safe Return",
  coverage: "Coverage",
  alert: "Alert",
  custom: "Custom",
};

const ZONE_TYPE_COLORS: Record<ZoneType, string> = {
  perimeter: "#4A9EFF",
  no_go: "#F05252",
  safe_return: "#3DD68C",
  coverage: "#A78BFA",
  alert: "#F5A623",
  custom: "#999999",
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
        flex: 1,
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

export function vertexLabel(i: number): string {
  if (i < 26) return String.fromCharCode(65 + i);
  return (
    String.fromCharCode(64 + Math.floor(i / 26)) +
    String.fromCharCode(65 + (i % 26))
  );
}

function CoordRow({
  label,
  lat,
  lon,
  color,
}: {
  label: string;
  lat: number;
  lon: number;
  color: string;
}) {
  return (
    <div
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
          width: "20px",
          height: "20px",
          borderRadius: "50%",
          backgroundColor: `${color}22`,
          border: `1.5px solid ${color}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: "9px",
            fontWeight: 700,
            color,
            fontFamily: "Inter, sans-serif",
          }}
        >
          {label}
        </span>
      </div>
      <div>
        <div
          style={{
            fontSize: "11px",
            color: "#EFEFEF",
            fontFamily: "Inter, sans-serif",
            lineHeight: 1.4,
          }}
        >
          {lat.toFixed(6)}°
        </div>
        <div
          style={{
            fontSize: "11px",
            color: "#EFEFEF",
            fontFamily: "Inter, sans-serif",
            lineHeight: 1.4,
          }}
        >
          {lon.toFixed(6)}°
        </div>
        <div style={{ fontSize: "9px", color: "#999999", marginTop: "1px" }}>
          lat · lon
        </div>
      </div>
    </div>
  );
}

export default function ZoneDetailPanel() {
  const selectedZoneId = useZoneStore((s) => s.selectedZoneId);
  const zones = useZoneStore((s) => s.zones);
  const setSelectedZone = useZoneStore((s) => s.setSelectedZone);

  const zone = selectedZoneId ? zones[selectedZoneId] : null;
  if (!zone) return null;

  const color =
    zone.color || ZONE_TYPE_COLORS[zone.zone_type as ZoneType] || "#999999";

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
              <div
                style={{
                  width: "8px",
                  height: "8px",
                  borderRadius: "2px",
                  backgroundColor: color,
                  flexShrink: 0,
                }}
              />
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
                {zone.name}
              </span>
            </div>
            <div style={{ fontSize: "10px", color: "#999999" }}>
              {ZONE_TYPE_LABELS[zone.zone_type as ZoneType] ?? zone.zone_type}
              {" · "}
              {zone.shape === "circle"
                ? "Circle"
                : `${zone.points.length} vertices`}
            </div>
          </div>
          <button
            onClick={() => setSelectedZone(null)}
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
        {zone.shape === "circle" ? (
          <>
            <div
              style={{
                fontSize: "10px",
                fontWeight: 600,
                letterSpacing: "1px",
                color: "#999999",
                marginBottom: "8px",
              }}
            >
              CENTRE POINT
            </div>
            {zone.center && (
              <CoordRow
                label="C"
                lat={zone.center.lat}
                lon={zone.center.lon}
                color={color}
              />
            )}
            <StatBox
              label="RADIUS"
              value={
                zone.radius_m != null ? `${zone.radius_m.toFixed(1)} m` : "—"
              }
              style={{ marginTop: "12px" }}
            />
            <StatBox
              label="AREA"
              value={
                zone.radius_m != null
                  ? formatArea(Math.PI * zone.radius_m ** 2)
                  : "—"
              }
              style={{ marginTop: "8px" }}
            />
          </>
        ) : (
          <>
            <div
              style={{
                fontSize: "10px",
                fontWeight: 600,
                letterSpacing: "1px",
                color: "#999999",
                marginBottom: "8px",
              }}
            >
              VERTICES
            </div>
            {zone.points.map((pt, i) => (
              <CoordRow
                key={i}
                label={vertexLabel(i)}
                lat={pt.lat}
                lon={pt.lon}
                color={color}
              />
            ))}
            <StatBox
              label="AREA"
              value={formatArea(polygonAreaM2(zone.points))}
              style={{ marginTop: "12px" }}
            />
          </>
        )}
      </div>
    </div>
  );
}
