import { useState, useRef, useCallback, useEffect } from "react";
import maplibregl from "maplibre-gl";
import MissionMap from "../components/map/MissionMap";
import ZoneLayer from "../components/zones/ZoneLayer";
import ZoneListPanel from "../components/zones/ZoneListPanel";
import CreateZoneModal from "../components/zones/CreateZoneModal";
import { useZones } from "../hooks/useZones";
import type { ZoneType as ZT } from "../types";

// Re-export for child components
export type ZoneType = ZT;
export type DrawMode = "polygon" | "circle" | null;

// Preview source/layer IDs
const DRAFT_SOURCE = "draft-source";
const DRAFT_FILL = "draft-fill";
const DRAFT_LINE = "draft-line";
const DRAFT_VERT = "draft-vertices";

export default function ZonesPage() {
  useZones(); // populate store on mount

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>(null);

  // Polygon draw state
  const polyPoints = useRef<[number, number][]>([]); // [lng, lat]
  const mousePos = useRef<[number, number] | null>(null);

  // Circle draw state
  const circleCenter = useRef<[number, number] | null>(null); // [lng, lat]

  // Modal state — called when shape is finished
  const [pendingShape, setPendingShape] = useState<
    | { type: "polygon"; points: [number, number][] }
    | { type: "circle"; center: [number, number]; radiusM: number }
    | null
  >(null);

  // ── Draft GeoJSON helpers ─────────────────────────────────────────────────

  const updateDraft = useCallback(
    (map: maplibregl.Map) => {
      const source = map.getSource(DRAFT_SOURCE) as
        | maplibregl.GeoJSONSource
        | undefined;
      if (!source) return;

      const pts = polyPoints.current;
      const mouse = mousePos.current;

      const features: GeoJSON.Feature[] = [];

      if (drawMode === "polygon" && pts.length > 0) {
        const ring = mouse ? [...pts, mouse] : pts;
        if (ring.length >= 3) {
          features.push({
            type: "Feature",
            geometry: { type: "Polygon", coordinates: [[...ring, ring[0]]] },
            properties: {},
          });
        }
        if (ring.length >= 2) {
          features.push({
            type: "Feature",
            geometry: { type: "LineString", coordinates: ring },
            properties: {},
          });
        }
        features.push({
          type: "Feature",
          geometry: { type: "MultiPoint", coordinates: pts },
          properties: {},
        });
      }

      if (drawMode === "circle" && circleCenter.current && mouse) {
        const [cLng, cLat] = circleCenter.current;
        const [mLng, mLat] = mouse;
        const R = 6371000;
        const dLat = ((mLat - cLat) * Math.PI) / 180;
        const dLon = ((mLng - cLng) * Math.PI) / 180;
        const a =
          Math.sin(dLat / 2) ** 2 +
          Math.cos((cLat * Math.PI) / 180) *
            Math.cos((mLat * Math.PI) / 180) *
            Math.sin(dLon / 2) ** 2;
        const radiusM = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));

        const steps = 64;
        const ring: [number, number][] = [];
        for (let i = 0; i <= steps; i++) {
          const angle = (i / steps) * 2 * Math.PI;
          const dLatR = (radiusM / R) * (180 / Math.PI) * Math.cos(angle);
          const dLonR =
            ((radiusM / R) * (180 / Math.PI) * Math.sin(angle)) /
            Math.cos((cLat * Math.PI) / 180);
          ring.push([cLng + dLonR, cLat + dLatR]);
        }
        features.push({
          type: "Feature",
          geometry: { type: "Polygon", coordinates: [ring] },
          properties: {},
        });
        features.push({
          type: "Feature",
          geometry: { type: "Point", coordinates: [cLng, cLat] },
          properties: {},
        });
      }

      source.setData({ type: "FeatureCollection", features });
    },
    [drawMode],
  );

  // ── Bootstrap draft layers when map is ready ──────────────────────────────

  useEffect(() => {
    if (!map) return;

    map.addSource(DRAFT_SOURCE, {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: DRAFT_FILL,
      type: "fill",
      source: DRAFT_SOURCE,
      filter: ["==", "$type", "Polygon"],
      paint: { "fill-color": "#4A9EFF", "fill-opacity": 0.12 },
    });
    map.addLayer({
      id: DRAFT_LINE,
      type: "line",
      source: DRAFT_SOURCE,
      filter: ["in", "$type", "LineString", "Polygon"],
      paint: {
        "line-color": "#4A9EFF",
        "line-width": 2,
        "line-dasharray": [3, 2],
      },
    });
    map.addLayer({
      id: DRAFT_VERT,
      type: "circle",
      source: DRAFT_SOURCE,
      filter: ["in", "$type", "Point", "MultiPoint"],
      paint: {
        "circle-radius": 4,
        "circle-color": "#4A9EFF",
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#0D0F12",
      },
    });

    return () => {
      [DRAFT_VERT, DRAFT_LINE, DRAFT_FILL].forEach((l) => {
        if (map.getLayer(l)) map.removeLayer(l);
      });
      if (map.getSource(DRAFT_SOURCE)) map.removeSource(DRAFT_SOURCE);
    };
  }, [map]);

  // ── Map event handlers ────────────────────────────────────────────────────

  useEffect(() => {
    if (!map) return;

    const canvas = map.getCanvas();

    const onMouseMove = (e: maplibregl.MapMouseEvent) => {
      mousePos.current = [e.lngLat.lng, e.lngLat.lat];
      updateDraft(map);
    };

    const onClick = (e: maplibregl.MapMouseEvent) => {
      if (drawMode === "polygon") {
        polyPoints.current = [
          ...polyPoints.current,
          [e.lngLat.lng, e.lngLat.lat],
        ];
        updateDraft(map);
      } else if (drawMode === "circle") {
        if (!circleCenter.current) {
          circleCenter.current = [e.lngLat.lng, e.lngLat.lat];
        } else {
          // Second click — compute radius and open modal
          const [cLng, cLat] = circleCenter.current;
          const R = 6371000;
          const dLat = ((e.lngLat.lat - cLat) * Math.PI) / 180;
          const dLon = ((e.lngLat.lng - cLng) * Math.PI) / 180;
          const a =
            Math.sin(dLat / 2) ** 2 +
            Math.cos((cLat * Math.PI) / 180) *
              Math.cos((e.lngLat.lat * Math.PI) / 180) *
              Math.sin(dLon / 2) ** 2;
          const radiusM = R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
          setPendingShape({
            type: "circle",
            center: circleCenter.current,
            radiusM,
          });
          circleCenter.current = null;
          mousePos.current = null;
          clearDraft(map);
        }
      }
    };

    const onDblClick = (e: maplibregl.MapMouseEvent) => {
      if (drawMode !== "polygon") return;
      e.preventDefault();
      const pts = polyPoints.current;
      if (pts.length < 3) return;
      setPendingShape({ type: "polygon", points: pts });
      polyPoints.current = [];
      mousePos.current = null;
      clearDraft(map);
    };

    if (drawMode) {
      canvas.style.cursor = "crosshair";
      map.on("mousemove", onMouseMove);
      map.on("click", onClick);
      map.on("dblclick", onDblClick);
    } else {
      canvas.style.cursor = "";
    }

    return () => {
      canvas.style.cursor = "";
      map.off("mousemove", onMouseMove);
      map.off("click", onClick);
      map.off("dblclick", onDblClick);
    };
  }, [map, drawMode, updateDraft]);

  // Cancel draw mode when Escape is pressed
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && drawMode) {
        cancelDraw();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [drawMode, map]);

  function clearDraft(m: maplibregl.Map) {
    const src = m.getSource(DRAFT_SOURCE) as
      | maplibregl.GeoJSONSource
      | undefined;
    src?.setData({ type: "FeatureCollection", features: [] });
  }

  function cancelDraw() {
    polyPoints.current = [];
    circleCenter.current = null;
    mousePos.current = null;
    if (map) clearDraft(map);
    setDrawMode(null);
  }

  function handleDrawModeChange(mode: DrawMode) {
    // Reset in-progress state when switching modes
    polyPoints.current = [];
    circleCenter.current = null;
    mousePos.current = null;
    if (map) clearDraft(map);
    setDrawMode(mode);
  }

  return (
    <div
      style={{
        display: "flex",
        flex: 1,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Map fills full background */}
      <div style={{ position: "absolute", inset: 0 }}>
        <MissionMap onMapReady={setMap} />
        {map && <ZoneLayer map={map} />}
      </div>

      {/* Left panel */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          height: "100%",
          zIndex: 10,
        }}
      >
        <ZoneListPanel
          drawMode={drawMode}
          onSetDrawMode={handleDrawModeChange}
        />
      </div>

      {/* Zone creation modal */}
      {pendingShape && (
        <CreateZoneModal
          shape={pendingShape}
          onClose={() => {
            setPendingShape(null);
            setDrawMode(null);
          }}
        />
      )}
    </div>
  );
}
