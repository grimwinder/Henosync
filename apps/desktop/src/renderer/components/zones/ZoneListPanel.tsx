import { Trash2, Pentagon, Circle, Plus } from "lucide-react";
import { useZoneStore } from "../../stores/zoneStore";
import { useDeleteZone } from "../../hooks/useZones";
import type { ZoneType } from "../../types";
import type { DrawMode } from "../../pages/ZonesPage";

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
  custom: "#8B95A3",
};

interface ZoneListPanelProps {
  drawMode: DrawMode;
  onSetDrawMode: (mode: DrawMode) => void;
}

export default function ZoneListPanel({
  drawMode,
  onSetDrawMode,
}: ZoneListPanelProps) {
  const zones = useZoneStore((s) => Object.values(s.zones));
  const selectedZoneId = useZoneStore((s) => s.selectedZoneId);
  const setSelectedZone = useZoneStore((s) => s.setSelectedZone);
  const { mutate: deleteZone } = useDeleteZone();

  const isDrawing = drawMode !== null;

  return (
    <div
      style={{
        width: "220px",
        height: "100%",
        backgroundColor: "#141619",
        borderRight: "1px solid #2A2F38",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 14px 10px",
          borderBottom: "1px solid #2A2F38",
          flexShrink: 0,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: "10px",
          }}
        >
          <span
            style={{
              fontSize: "11px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#8B95A3",
            }}
          >
            ZONES
          </span>
          <span style={{ fontSize: "11px", color: "#8B95A3" }}>
            {zones.length}
          </span>
        </div>

        {/* Draw mode buttons */}
        <div style={{ display: "flex", gap: "6px" }}>
          <DrawBtn
            icon={<Pentagon size={13} />}
            label="Polygon"
            active={drawMode === "polygon"}
            disabled={isDrawing && drawMode !== "polygon"}
            onClick={() =>
              onSetDrawMode(drawMode === "polygon" ? null : "polygon")
            }
          />
          <DrawBtn
            icon={<Circle size={13} />}
            label="Circle"
            active={drawMode === "circle"}
            disabled={isDrawing && drawMode !== "circle"}
            onClick={() =>
              onSetDrawMode(drawMode === "circle" ? null : "circle")
            }
          />
        </div>

        {isDrawing && (
          <div
            style={{
              marginTop: "8px",
              fontSize: "10px",
              color: "#F5A623",
              lineHeight: 1.4,
            }}
          >
            {drawMode === "polygon"
              ? "Click to add vertices. Double-click to finish."
              : "Click to set centre. Click again to set radius."}
          </div>
        )}
      </div>

      {/* Zone list */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {zones.length === 0 ? (
          <div
            style={{
              padding: "24px 14px",
              textAlign: "center",
              color: "#8B95A3",
              fontSize: "12px",
              lineHeight: 1.5,
            }}
          >
            <Plus size={20} style={{ opacity: 0.4, marginBottom: "8px" }} />
            <div>Draw a zone on the map to get started.</div>
          </div>
        ) : (
          zones.map((zone) => {
            const color =
              zone.color ||
              ZONE_TYPE_COLORS[zone.zone_type as ZoneType] ||
              "#8B95A3";
            const isSelected = selectedZoneId === zone.id;
            return (
              <div
                key={zone.id}
                onClick={() => setSelectedZone(isSelected ? null : zone.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  padding: "9px 14px",
                  borderBottom: "1px solid #1C1F24",
                  cursor: "pointer",
                  backgroundColor: isSelected ? "#1C1F24" : "transparent",
                  borderLeft: isSelected
                    ? `2px solid ${color}`
                    : "2px solid transparent",
                }}
              >
                {/* Color swatch */}
                <div
                  style={{
                    width: "10px",
                    height: "10px",
                    borderRadius: "2px",
                    backgroundColor: color,
                    flexShrink: 0,
                  }}
                />

                {/* Info */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: "12px",
                      color: "#E8EAED",
                      fontWeight: 500,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {zone.name}
                  </div>
                  <div
                    style={{
                      fontSize: "10px",
                      color: "#8B95A3",
                      marginTop: "1px",
                    }}
                  >
                    {ZONE_TYPE_LABELS[zone.zone_type as ZoneType] ??
                      zone.zone_type}
                    {" · "}
                    {zone.shape === "circle"
                      ? "Circle"
                      : `${zone.points.length} pts`}
                  </div>
                </div>

                {/* Delete */}
                <button
                  onClick={() => deleteZone(zone.id)}
                  title="Delete zone"
                  style={{
                    background: "none",
                    border: "none",
                    color: "#8B95A3",
                    cursor: "pointer",
                    padding: "2px",
                    display: "flex",
                    flexShrink: 0,
                  }}
                  onMouseEnter={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color =
                      "#F05252";
                  }}
                  onMouseLeave={(e) => {
                    (e.currentTarget as HTMLButtonElement).style.color =
                      "#8B95A3";
                  }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

function DrawBtn({
  icon,
  label,
  active,
  disabled,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "5px",
        padding: "5px 0",
        borderRadius: "5px",
        border: `1px solid ${active ? "#4A9EFF" : "#2A2F38"}`,
        backgroundColor: active ? "#4A9EFF18" : "transparent",
        color: active ? "#4A9EFF" : disabled ? "#3A4048" : "#8B95A3",
        fontSize: "11px",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "all 150ms",
      }}
    >
      {icon}
      {label}
    </button>
  );
}
