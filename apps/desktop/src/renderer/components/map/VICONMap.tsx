import { useRef, useState, useMemo, useCallback } from "react";
import { useNodeStore } from "../../stores/nodeStore";
import { useZoneStore } from "../../stores/zoneStore";
import { useMarkerStore } from "../../stores/markerStore";
import type { DrawMode } from "../../pages/ZonesPage";

export interface VICONSpace {
  shape: "rectangle" | "circle";
  width_m: number; // rectangle width (X axis) or circle diameter
  height_m: number; // rectangle depth (Y axis); ignored for circle
}

interface VICONMapProps {
  space: VICONSpace;
  drawMode?: DrawMode | null;
  onFinishPolygon?: (points: [number, number][]) => void; // [x_m, y_m] pairs
  onFinishCircle?: (center: [number, number], radiusM: number) => void;
  onPlaceMarker?: (x_m: number, y_m: number) => void;
  // Real-world anchor for the arena's (0, 0) point (set via the VICON panel
  // in the title bar). Zones/markers are now stored as real WGS84 (backend
  // converts on create — see zones.py/markers.py), so rendering them here
  // needs the inverse conversion back to local metres. Until an origin is
  // set, existing zones/markers can't be placed correctly, so they're
  // hidden rather than drawn at a wrong position.
  homeLat?: number | null;
  homeLon?: number | null;
}

const VB = 600;
const PAD = 52;
const EARTH_RADIUS_M = 6_371_000;

/** Inverse of the backend's local_to_gps() (vicon_manager.py) — real WGS84 back to local arena metres. */
function gpsToLocal(
  lat: number, lon: number, homeLat: number, homeLon: number,
): [number, number] {
  const latRad = (homeLat * Math.PI) / 180;
  const y_m = ((lat - homeLat) * Math.PI / 180) * EARTH_RADIUS_M;
  const x_m = ((lon - homeLon) * Math.PI / 180) * EARTH_RADIUS_M * Math.cos(latRad);
  return [x_m, y_m];
}

const DOT_COLOR: Record<string, string> = {
  online: "#3DD68C",
  degraded: "#F5A623",
  offline: "#555555",
  connecting: "#888888",
  error: "#F05252",
};

const ZONE_COLORS: Record<string, string> = {
  perimeter: "#4A9EFF",
  no_go: "#F05252",
  safe_return: "#3DD68C",
  coverage: "#A78BFA",
  alert: "#F5A623",
  custom: "#999999",
};

const MARKER_COLORS: Record<string, string> = {
  home_position: "#3DD68C",
  waypoint: "#4A9EFF",
  reference: "#A78BFA",
  hazard: "#F05252",
  custom: "#F5A623",
};

export default function VICONMap({
  space,
  drawMode,
  onFinishPolygon,
  onFinishCircle,
  onPlaceMarker,
  homeLat,
  homeLon,
}: VICONMapProps) {
  const hasOrigin = homeLat != null && homeLon != null;
  const toLocal = useCallback(
    (lat: number, lon: number): [number, number] =>
      hasOrigin ? gpsToLocal(lat, lon, homeLat, homeLon) : [0, 0],
    [hasOrigin, homeLat, homeLon],
  );
  const nodes = Object.values(useNodeStore((s) => s.nodes)).filter(
    (n) => n.config?.position_source === "vicon",
  );
  const zones = Object.values(useZoneStore((s) => s.zones));
  const markers = Object.values(useMarkerStore((s) => s.markers));

  const svgRef = useRef<SVGSVGElement>(null);

  // Drawing state
  const [draftPoly, setDraftPoly] = useState<[number, number][]>([]); // VICON x_m, y_m
  const [circleCenter, setCircleCenter] = useState<[number, number] | null>(
    null,
  );
  const [mouseVicon, setMouseVicon] = useState<[number, number] | null>(null);

  const cx = VB / 2;
  const cy = VB / 2;

  const { spaceW, spaceH, scale } = useMemo(() => {
    const isCircle = space.shape === "circle";
    const maxDim = isCircle
      ? space.width_m
      : Math.max(space.width_m, space.height_m);
    const sc = (VB - 2 * PAD) / Math.max(maxDim, 0.1);
    return {
      spaceW: space.width_m * sc,
      spaceH: isCircle ? space.width_m * sc : space.height_m * sc,
      scale: sc,
    };
  }, [space]);

  const toSvg = useCallback(
    (x_m: number, y_m: number): [number, number] => [
      cx + x_m * scale,
      cy - y_m * scale,
    ],
    [cx, cy, scale],
  );

  // Convert a DOM mouse event to VICON x_m, y_m
  function eventToVicon(
    e: React.MouseEvent<SVGSVGElement>,
  ): [number, number] | null {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const dim = Math.min(rect.width, rect.height);
    const offX = (rect.width - dim) / 2;
    const offY = (rect.height - dim) / 2;
    const svgX = ((e.clientX - rect.left - offX) / dim) * VB;
    const svgY = ((e.clientY - rect.top - offY) / dim) * VB;
    return [(svgX - cx) / scale, (cy - svgY) / scale];
  }

  const isDrawing =
    drawMode === "polygon" || drawMode === "circle" || drawMode === "marker";

  function handleMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    if (!isDrawing) return;
    setMouseVicon(eventToVicon(e));
  }

  function handleMouseLeave() {
    setMouseVicon(null);
  }

  function handleClick(e: React.MouseEvent<SVGSVGElement>) {
    const pt = eventToVicon(e);
    if (!pt) return;

    if (drawMode === "marker") {
      onPlaceMarker?.(pt[0], pt[1]);
      return;
    }
    if (drawMode === "polygon") {
      setDraftPoly((prev) => [...prev, pt]);
      return;
    }
    if (drawMode === "circle") {
      if (!circleCenter) {
        setCircleCenter(pt);
      } else {
        const dx = pt[0] - circleCenter[0];
        const dy = pt[1] - circleCenter[1];
        const radiusM = Math.sqrt(dx * dx + dy * dy);
        onFinishCircle?.(circleCenter, radiusM);
        setCircleCenter(null);
        setMouseVicon(null);
      }
    }
  }

  function handleDoubleClick(e: React.MouseEvent<SVGSVGElement>) {
    e.preventDefault();
    if (drawMode !== "polygon") return;
    if (draftPoly.length < 3) return;
    onFinishPolygon?.(draftPoly);
    setDraftPoly([]);
    setMouseVicon(null);
  }

  // Cancel draft when draw mode exits
  useMemo(() => {
    if (!drawMode) {
      setDraftPoly([]);
      setCircleCenter(null);
      setMouseVicon(null);
    }
  }, [drawMode]);

  const isCircle = space.shape === "circle";
  const r = spaceW / 2;

  // Draft polygon ring with live mouse preview
  const draftRing: [number, number][] =
    drawMode === "polygon" && mouseVicon
      ? [...draftPoly, mouseVicon]
      : draftPoly;

  // Draft circle radius preview
  let draftCircleR = 0;
  if (drawMode === "circle" && circleCenter && mouseVicon) {
    const dx = mouseVicon[0] - circleCenter[0];
    const dy = mouseVicon[1] - circleCenter[1];
    draftCircleR = Math.sqrt(dx * dx + dy * dy) * scale;
  }

  const cursor = isDrawing ? "crosshair" : "default";

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: "#0D0D0D",
        position: "relative",
      }}
    >
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VB} ${VB}`}
        style={{ width: "100%", height: "100%", display: "block", cursor }}
        preserveAspectRatio="xMidYMid meet"
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        onClick={handleClick}
        onDoubleClick={handleDoubleClick}
      >
        <rect width={VB} height={VB} fill="#0D0D0D" />

        {/* Space fill */}
        {isCircle ? (
          <circle cx={cx} cy={cy} r={r} fill="#111416" />
        ) : (
          <rect
            x={cx - spaceW / 2}
            y={cy - spaceH / 2}
            width={spaceW}
            height={spaceH}
            fill="#111416"
          />
        )}

        {/* Space boundary */}
        {isCircle ? (
          <circle
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke="#FFFFFF"
            strokeWidth={3}
          />
        ) : (
          <rect
            x={cx - spaceW / 2}
            y={cy - spaceH / 2}
            width={spaceW}
            height={spaceH}
            fill="none"
            stroke="#FFFFFF"
            strokeWidth={3}
          />
        )}

        {/* Origin dot */}
        <circle cx={cx} cy={cy} r={3} fill="#3A3F48" />

        {/* Existing zones — points/center are real WGS84 (converted by the
            backend at creation time), so convert back to local metres
            before projecting to SVG. Hidden until an arena origin is set,
            since there's no correct position to draw them at. */}
        {hasOrigin && zones.map((zone) => {
          const color = zone.color || ZONE_COLORS[zone.zone_type] || "#4A9EFF";
          if (zone.shape === "circle" && zone.center && zone.radius_m != null) {
            const [sx, sy] = toSvg(...toLocal(zone.center.lat, zone.center.lon));
            const sr = zone.radius_m * scale;
            return (
              <g key={zone.id}>
                <circle
                  cx={sx}
                  cy={sy}
                  r={sr}
                  fill={color}
                  fillOpacity={0.15}
                  stroke={color}
                  strokeWidth={1.5}
                />
              </g>
            );
          }
          if (zone.shape === "polygon" && zone.points.length >= 3) {
            const pts = zone.points.map((p) => toSvg(...toLocal(p.lat, p.lon)));
            const polyStr = pts.map(([x, y]) => `${x},${y}`).join(" ");
            return (
              <g key={zone.id}>
                <polygon
                  points={polyStr}
                  fill={color}
                  fillOpacity={0.15}
                  stroke={color}
                  strokeWidth={1.5}
                />
              </g>
            );
          }
          return null;
        })}

        {/* Existing markers — same real-WGS84-back-to-local conversion as zones. */}
        {hasOrigin && markers.map((marker) => {
          const [sx, sy] = toSvg(...toLocal(marker.lat, marker.lon));
          const color = MARKER_COLORS[marker.marker_type] || "#4A9EFF";
          return (
            <g key={marker.id}>
              <circle cx={sx} cy={sy} r={5} fill={color} fillOpacity={0.9} />
              <circle
                cx={sx}
                cy={sy}
                r={5}
                fill="none"
                stroke="#0D0D0D"
                strokeWidth={1}
              />
              <text
                x={sx}
                y={sy + 15}
                textAnchor="middle"
                fill={color}
                fontSize={8}
                fontFamily="Inter, sans-serif"
                fontWeight={600}
              >
                {marker.name}
              </text>
            </g>
          );
        })}

        {/* Draft polygon */}
        {drawMode === "polygon" && draftRing.length >= 2 && (
          <>
            {draftRing.length >= 3 && (
              <polygon
                points={draftRing
                  .map((p) => toSvg(p[0], p[1]).join(","))
                  .join(" ")}
                fill="#4A9EFF"
                fillOpacity={0.12}
                stroke="#4A9EFF"
                strokeWidth={1.5}
                strokeDasharray="5 3"
              />
            )}
            <polyline
              points={draftRing
                .map((p) => toSvg(p[0], p[1]).join(","))
                .join(" ")}
              fill="none"
              stroke="#4A9EFF"
              strokeWidth={1.5}
              strokeDasharray="5 3"
            />
          </>
        )}
        {drawMode === "polygon" &&
          draftPoly.map((p, i) => {
            const [sx, sy] = toSvg(p[0], p[1]);
            return (
              <circle
                key={i}
                cx={sx}
                cy={sy}
                r={4}
                fill="#4A9EFF"
                stroke="#0D0D0D"
                strokeWidth={1}
              />
            );
          })}

        {/* Draft circle */}
        {drawMode === "circle" && circleCenter && (
          <>
            {draftCircleR > 0 && (
              <circle
                cx={toSvg(circleCenter[0], circleCenter[1])[0]}
                cy={toSvg(circleCenter[0], circleCenter[1])[1]}
                r={draftCircleR}
                fill="#4A9EFF"
                fillOpacity={0.12}
                stroke="#4A9EFF"
                strokeWidth={1.5}
                strokeDasharray="5 3"
              />
            )}
            <circle
              cx={toSvg(circleCenter[0], circleCenter[1])[0]}
              cy={toSvg(circleCenter[0], circleCenter[1])[1]}
              r={4}
              fill="#4A9EFF"
              stroke="#0D0D0D"
              strokeWidth={1}
            />
          </>
        )}

        {/* Marker preview dot */}
        {drawMode === "marker" &&
          mouseVicon &&
          (() => {
            const [sx, sy] = toSvg(mouseVicon[0], mouseVicon[1]);
            return (
              <circle cx={sx} cy={sy} r={5} fill="#4A9EFF" fillOpacity={0.6} />
            );
          })()}

        {/* Robot dots */}
        {nodes.flatMap((node) => {
          const vx = node.telemetry?.vicon_x as number | undefined;
          const vy = node.telemetry?.vicon_y as number | undefined;
          if (vx == null || vy == null) return [];
          const [sx, sy] = toSvg(vx, vy);
          const color = DOT_COLOR[node.status] ?? "#888888";
          return [
            <g key={node.id}>
              <circle cx={sx} cy={sy} r={8} fill={color} />
              <circle
                cx={sx}
                cy={sy}
                r={8}
                fill="none"
                stroke="#0D0D0D"
                strokeWidth={1}
              />
              <text
                x={sx}
                y={sy + 19}
                textAnchor="middle"
                fill="#EFEFEF"
                fontSize={9}
                fontFamily="Inter, sans-serif"
                fontWeight={600}
              >
                {node.name}
              </text>
            </g>,
          ];
        })}
      </svg>

      {/* Dimension label */}
      <div
        style={{
          position: "absolute",
          bottom: 10,
          right: 14,
          fontSize: 10,
          color: "#3A3F48",
          fontFamily: "Inter, sans-serif",
          userSelect: "none",
          pointerEvents: "none",
        }}
      >
        {isCircle
          ? `⌀ ${space.width_m} m`
          : `${space.width_m} × ${space.height_m} m`}
      </div>

      {/* Draw hint */}
      {drawMode === "polygon" && draftPoly.length >= 3 && (
        <div
          style={{
            position: "absolute",
            bottom: 30,
            left: "50%",
            transform: "translateX(-50%)",
            fontSize: 10,
            color: "#8B95A3",
            pointerEvents: "none",
            backgroundColor: "#141414CC",
            borderRadius: 4,
            padding: "3px 8px",
          }}
        >
          Double-click to finish polygon
        </div>
      )}
      {drawMode === "circle" && !circleCenter && (
        <div
          style={{
            position: "absolute",
            bottom: 30,
            left: "50%",
            transform: "translateX(-50%)",
            fontSize: 10,
            color: "#8B95A3",
            pointerEvents: "none",
            backgroundColor: "#141414CC",
            borderRadius: 4,
            padding: "3px 8px",
          }}
        >
          Click to place centre
        </div>
      )}
      {drawMode === "circle" && circleCenter && (
        <div
          style={{
            position: "absolute",
            bottom: 30,
            left: "50%",
            transform: "translateX(-50%)",
            fontSize: 10,
            color: "#8B95A3",
            pointerEvents: "none",
            backgroundColor: "#141414CC",
            borderRadius: 4,
            padding: "3px 8px",
          }}
        >
          Click to set radius
        </div>
      )}
    </div>
  );
}
