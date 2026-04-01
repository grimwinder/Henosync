import { useState } from "react";
import { Trash2, Plus, MapPin } from "lucide-react";
import { useZoneStore } from "../../stores/zoneStore";
import { useMarkerStore } from "../../stores/markerStore";
import { useDeleteZone } from "../../hooks/useZones";
import { useDeleteMarker } from "../../hooks/useMarkers";
import type { ZoneType, MarkerType } from "../../types";

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

export default function ZoneListPanel() {
  const zones = useZoneStore((s) => Object.values(s.zones));
  const selectedZoneId = useZoneStore((s) => s.selectedZoneId);
  const setSelectedZone = useZoneStore((s) => s.setSelectedZone);
  const { mutate: deleteZone } = useDeleteZone();

  const markers = useMarkerStore((s) => Object.values(s.markers));
  const selectedMarkerId = useMarkerStore((s) => s.selectedMarkerId);
  const setSelectedMarker = useMarkerStore((s) => s.setSelectedMarker);
  const { mutate: deleteMarker } = useDeleteMarker();

  const [confirmingZoneId, setConfirmingZoneId] = useState<string | null>(null);
  const [confirmingMarkerId, setConfirmingMarkerId] = useState<string | null>(
    null,
  );

  function handleSelectZone(id: string, isSelected: boolean) {
    setSelectedMarker(null);
    setSelectedZone(isSelected ? null : id);
  }

  function handleSelectMarker(id: string, isSelected: boolean) {
    setSelectedZone(null);
    setSelectedMarker(isSelected ? null : id);
  }

  return (
    <div
      style={{
        width: "220px",
        backgroundColor: "#141619",
        borderRight: "1px solid #2A2F38",
        borderBottom: "1px solid #2A2F38",
        borderBottomRightRadius: "8px",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        maxHeight: "50vh",
      }}
    >
      {/* ── ZONES section ── */}
      <div
        style={{
          padding: "10px 14px 8px",
          borderBottom: "1px solid #2A2F38",
          flexShrink: 0,
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
            color: "#8B95A3",
          }}
        >
          ZONES
        </span>
        <span style={{ fontSize: "11px", color: "#8B95A3" }}>
          {zones.length}
        </span>
      </div>

      <div
        style={{ overflowY: "auto", flexShrink: zones.length === 0 ? 0 : 1 }}
      >
        {zones.length === 0 ? (
          <div
            style={{
              padding: "16px 14px",
              textAlign: "center",
              color: "#8B95A3",
              fontSize: "11px",
              lineHeight: 1.5,
            }}
          >
            <Plus size={16} style={{ opacity: 0.4, marginBottom: "6px" }} />
            <div>Use the toolbar above to draw a zone.</div>
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
                onClick={() => handleSelectZone(zone.id, isSelected)}
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
                <div
                  style={{
                    width: "10px",
                    height: "10px",
                    borderRadius: "2px",
                    backgroundColor: color,
                    flexShrink: 0,
                  }}
                />
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
                {confirmingZoneId === zone.id ? (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "3px",
                      flexShrink: 0,
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => setConfirmingZoneId(null)}
                      style={{
                        fontSize: "9px",
                        padding: "2px 5px",
                        borderRadius: "3px",
                        border: "1px solid #2A2F38",
                        backgroundColor: "transparent",
                        color: "#8B95A3",
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        deleteZone(zone.id);
                        setConfirmingZoneId(null);
                      }}
                      style={{
                        fontSize: "9px",
                        padding: "2px 5px",
                        borderRadius: "3px",
                        border: "1px solid #F05252",
                        backgroundColor: "#F0525222",
                        color: "#F05252",
                        cursor: "pointer",
                      }}
                    >
                      Delete
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmingZoneId(zone.id);
                    }}
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
                )}
              </div>
            );
          })
        )}
      </div>

      {/* ── MARKERS section ── */}
      <div
        style={{
          padding: "10px 14px 8px",
          borderTop: "1px solid #2A2F38",
          borderBottom: "1px solid #2A2F38",
          flexShrink: 0,
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
            color: "#8B95A3",
          }}
        >
          MARKERS
        </span>
        <span style={{ fontSize: "11px", color: "#8B95A3" }}>
          {markers.length}
        </span>
      </div>

      <div
        style={{ overflowY: "auto", flexShrink: markers.length === 0 ? 0 : 1 }}
      >
        {markers.length === 0 ? (
          <div
            style={{
              padding: "16px 14px",
              textAlign: "center",
              color: "#8B95A3",
              fontSize: "11px",
              lineHeight: 1.5,
            }}
          >
            <MapPin size={16} style={{ opacity: 0.4, marginBottom: "6px" }} />
            <div>Use the toolbar above to place a marker.</div>
          </div>
        ) : (
          markers.map((marker) => {
            const color =
              marker.color ||
              MARKER_TYPE_COLORS[marker.marker_type as MarkerType] ||
              "#8B95A3";
            const isSelected = selectedMarkerId === marker.id;
            return (
              <div
                key={marker.id}
                onClick={() => handleSelectMarker(marker.id, isSelected)}
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
                <MapPin size={10} color={color} style={{ flexShrink: 0 }} />
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
                    {marker.name}
                  </div>
                  <div
                    style={{
                      fontSize: "10px",
                      color: "#8B95A3",
                      marginTop: "1px",
                    }}
                  >
                    {MARKER_TYPE_LABELS[marker.marker_type as MarkerType] ??
                      marker.marker_type}
                  </div>
                </div>
                {confirmingMarkerId === marker.id ? (
                  <div
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      gap: "3px",
                      flexShrink: 0,
                    }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <button
                      onClick={() => setConfirmingMarkerId(null)}
                      style={{
                        fontSize: "9px",
                        padding: "2px 5px",
                        borderRadius: "3px",
                        border: "1px solid #2A2F38",
                        backgroundColor: "transparent",
                        color: "#8B95A3",
                        cursor: "pointer",
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        deleteMarker(marker.id);
                        setConfirmingMarkerId(null);
                      }}
                      style={{
                        fontSize: "9px",
                        padding: "2px 5px",
                        borderRadius: "3px",
                        border: "1px solid #F05252",
                        backgroundColor: "#F0525222",
                        color: "#F05252",
                        cursor: "pointer",
                      }}
                    >
                      Delete
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setConfirmingMarkerId(marker.id);
                    }}
                    title="Delete marker"
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
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
