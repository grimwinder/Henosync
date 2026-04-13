import { useState, useEffect } from "react";
import { X } from "lucide-react";
import union from "@turf/union";
import booleanIntersects from "@turf/boolean-intersects";
import { polygon as turfPolygon, featureCollection } from "@turf/helpers";
import type { Feature, Polygon } from "geojson";
import { useZoneStore } from "../../stores/zoneStore";
import { useCreateZone } from "../../hooks/useZones";
import type { ZoneType, GeoPoint } from "../../types";

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

/** Approximate a circle as a closed GeoJSON ring [lon, lat][]. */
function circleRing(
  lat: number,
  lon: number,
  radiusM: number,
  steps = 64,
): [number, number][] {
  const R = 6371000;
  const ring: [number, number][] = [];
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const dLat = (radiusM / R) * (180 / Math.PI) * Math.cos(angle);
    const dLon =
      ((radiusM / R) * (180 / Math.PI) * Math.sin(angle)) /
      Math.cos((lat * Math.PI) / 180);
    ring.push([lon + dLon, lat + dLat]);
  }
  return ring;
}

function zoneToTurfPolygon(zone: {
  shape: string;
  points: GeoPoint[];
  center?: GeoPoint | null;
  radius_m?: number | null;
}): Feature<Polygon> | null {
  if (zone.shape === "circle") {
    if (!zone.center || zone.radius_m == null) return null;
    const ring = circleRing(zone.center.lat, zone.center.lon, zone.radius_m);
    return turfPolygon([ring]);
  }
  if (zone.points.length < 3) return null;
  const ring = zone.points.map((p) => [p.lon, p.lat] as [number, number]);
  ring.push(ring[0]);
  return turfPolygon([ring]);
}

/** Check if all selected zones mutually overlap (each pair must intersect). */
function allOverlap(turfPolys: Feature<Polygon>[]): boolean {
  for (let i = 0; i < turfPolys.length; i++) {
    for (let j = i + 1; j < turfPolys.length; j++) {
      if (!booleanIntersects(turfPolys[i], turfPolys[j])) return false;
    }
  }
  return true;
}

/** Merge an array of polygon features into a single union polygon.
 *  Returns null if union produces a MultiPolygon (disconnected zones). */
function computeUnion(turfPolys: Feature<Polygon>[]): Feature<Polygon> | null {
  if (turfPolys.length === 0) return null;
  const result = union(featureCollection(turfPolys));
  if (!result || result.geometry.type !== "Polygon") return null;
  return result as Feature<Polygon>;
}

interface MergeZonesPanelProps {
  onClose: () => void;
}

export default function MergeZonesPanel({ onClose }: MergeZonesPanelProps) {
  const zones = useZoneStore((s) => Object.values(s.zones));
  const setMergeHighlightedIds = useZoneStore((s) => s.setMergeHighlightedIds);
  const { mutate: createZone, isPending } = useCreateZone();

  const [name, setName] = useState("");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [zoneType, setZoneType] = useState<ZoneType>("perimeter");
  const [overlapError, setOverlapError] = useState(false);

  // Keep map highlights in sync
  useEffect(() => {
    setMergeHighlightedIds(selectedIds);
  }, [selectedIds, setMergeHighlightedIds]);

  // Clear highlights on unmount
  useEffect(() => {
    return () => setMergeHighlightedIds(new Set());
  }, [setMergeHighlightedIds]);

  function toggleZone(id: string) {
    setOverlapError(false);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleCreate() {
    if (!name.trim() || selectedIds.size < 2) return;

    const selectedZones = zones.filter((z) => selectedIds.has(z.id));
    const turfPolys = selectedZones
      .map(zoneToTurfPolygon)
      .filter(Boolean) as Feature<Polygon>[];

    if (turfPolys.length < 2) return;

    if (!allOverlap(turfPolys)) {
      setOverlapError(true);
      return;
    }

    const merged = computeUnion(turfPolys);
    if (!merged) {
      setOverlapError(true);
      return;
    }

    // Drop the closing duplicate point from the exterior ring
    const ring = merged.geometry.coordinates[0];
    const points: GeoPoint[] = ring
      .slice(0, -1)
      .map(([lon, lat]) => ({ lat, lon }));

    createZone(
      { name: name.trim(), zone_type: zoneType, points },
      { onSuccess: onClose },
    );
  }

  const canCreate =
    name.trim().length > 0 && selectedIds.size >= 2 && !isPending;

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
          borderBottom: "1px solid #2D2D2D",
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
            color: "#999999",
          }}
        >
          MERGE ZONES
        </span>
        <button
          onClick={onClose}
          title="Close"
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

      {/* Scrollable content */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {/* Name input */}
        <div
          style={{ padding: "12px 14px", borderBottom: "1px solid #2D2D2D" }}
        >
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#999999",
              marginBottom: "8px",
            }}
          >
            ZONE NAME
          </div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
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
            }}
          />
        </div>

        {/* Zone selector */}
        <div
          style={{ padding: "12px 14px", borderBottom: "1px solid #2D2D2D" }}
        >
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#999999",
              marginBottom: "8px",
            }}
          >
            SELECT ZONES
            {selectedIds.size > 0 && selectedIds.size < 2 ? " (min 2)" : ""}
          </div>
          {overlapError && (
            <div
              style={{
                fontSize: "11px",
                color: "#F05252",
                backgroundColor: "#F0525218",
                border: "1px solid #F0525240",
                borderRadius: "5px",
                padding: "6px 8px",
                marginBottom: "8px",
                lineHeight: 1.4,
              }}
            >
              Selected zones must overlap to be merged.
            </div>
          )}
          {zones.length === 0 ? (
            <div style={{ fontSize: "11px", color: "#999999" }}>
              No zones available.
            </div>
          ) : (
            zones.map((zone) => {
              const color =
                zone.color ||
                ZONE_TYPE_COLORS[zone.zone_type as ZoneType] ||
                "#999999";
              const checked = selectedIds.has(zone.id);
              return (
                <div
                  key={zone.id}
                  onClick={() => toggleZone(zone.id)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    padding: "7px 0",
                    cursor: "pointer",
                    borderBottom: "1px solid #1C1C1C",
                  }}
                >
                  <div
                    style={{
                      width: "14px",
                      height: "14px",
                      borderRadius: "3px",
                      border: `1.5px solid ${checked ? color : "#2D2D2D"}`,
                      backgroundColor: checked ? `${color}33` : "transparent",
                      flexShrink: 0,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {checked && (
                      <div
                        style={{
                          width: "6px",
                          height: "6px",
                          borderRadius: "1px",
                          backgroundColor: color,
                        }}
                      />
                    )}
                  </div>
                  <div
                    style={{
                      width: "8px",
                      height: "8px",
                      borderRadius: "2px",
                      backgroundColor: color,
                      flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div
                      style={{
                        fontSize: "12px",
                        color: "#EFEFEF",
                        fontWeight: 500,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {zone.name}
                    </div>
                    <div style={{ fontSize: "10px", color: "#999999" }}>
                      {ZONE_TYPE_LABELS[zone.zone_type as ZoneType] ??
                        zone.zone_type}
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Zone type selector — directly below zone selector */}
        <div style={{ padding: "12px 14px" }}>
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#999999",
              marginBottom: "8px",
            }}
          >
            MERGED ZONE TYPE
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "6px",
            }}
          >
            {(Object.entries(ZONE_TYPE_LABELS) as [ZoneType, string][]).map(
              ([type, label]) => {
                const active = zoneType === type;
                const color = ZONE_TYPE_COLORS[type];
                return (
                  <button
                    key={type}
                    onClick={() => setZoneType(type)}
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
                    }}
                  >
                    {label}
                  </button>
                );
              },
            )}
          </div>
        </div>
      </div>

      {/* Create button — always pinned to bottom */}
      <div
        style={{
          padding: "12px 14px",
          borderTop: "1px solid #2D2D2D",
          flexShrink: 0,
        }}
      >
        <button
          onClick={handleCreate}
          disabled={!canCreate}
          style={{
            width: "100%",
            padding: "9px",
            borderRadius: "6px",
            border: "none",
            backgroundColor: canCreate ? "#4A9EFF" : "#2D2D2D",
            color: canCreate ? "#fff" : "#999999",
            fontSize: "12px",
            fontWeight: 600,
            cursor: canCreate ? "pointer" : "not-allowed",
            transition: "background-color 150ms",
          }}
        >
          {isPending ? "Creating…" : "Create Zone"}
        </button>
      </div>
    </div>
  );
}
