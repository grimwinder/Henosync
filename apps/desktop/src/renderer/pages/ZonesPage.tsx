import { useState, useRef, useCallback, useEffect } from "react";
import maplibregl from "maplibre-gl";
import MissionMap from "../components/map/MissionMap";
import ZoneLayer from "../components/zones/ZoneLayer";
import MarkerLayer from "../components/zones/MarkerLayer";
import ZoneListPanel from "../components/zones/ZoneListPanel";
import MapToolbar from "../components/zones/MapToolbar";
import ZoneDetailPanel, {
  vertexLabel,
} from "../components/zones/ZoneDetailPanel";
import CreateZoneModal from "../components/zones/CreateZoneModal";
import MergeZonesPanel from "../components/zones/MergeZonesPanel";
import MarkerDetailPanel from "../components/zones/MarkerDetailPanel";
import PlaceMarkerModal from "../components/zones/PlaceMarkerModal";
import MeasureOverlay from "../components/zones/MeasureOverlay";
import { useZones } from "../hooks/useZones";
import { useMarkers } from "../hooks/useMarkers";
import { useZoneStore } from "../stores/zoneStore";
import type { ZoneType as ZT } from "../types";

// Re-export for child components
export type ZoneType = ZT;
export type DrawMode =
  | "polygon"
  | "circle"
  | "merge"
  | "marker"
  | "measure"
  | null;

// Preview source/layer IDs
const DRAFT_SOURCE = "draft-source";
const DRAFT_FILL = "draft-fill";
const DRAFT_LINE = "draft-line";
const DRAFT_VERT = "draft-vertices";

export default function ZonesPage() {
  useZones(); // populate store on mount
  useMarkers(); // populate marker store on mount

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const [drawMode, setDrawMode] = useState<DrawMode>(null);
  const [cursorLatLon, setCursorLatLon] = useState<[number, number] | null>(
    null,
  );
  const [pendingMarker, setPendingMarker] = useState<{
    lat: number;
    lon: number;
  } | null>(null);

  const selectedZoneId = useZoneStore((s) => s.selectedZoneId);
  const setSelectedZone = useZoneStore((s) => s.setSelectedZone);

  // Polygon draw state
  const polyPoints = useRef<[number, number][]>([]); // [lng, lat]
  const mousePos = useRef<[number, number] | null>(null);

  // Circle draw state
  const circleCenter = useRef<[number, number] | null>(null); // [lng, lat]

  // Vertex label HTML markers
  const labelMarkersRef = useRef<maplibregl.Marker[]>([]);

  // Modal state — called when shape is finished
  const [pendingShape, setPendingShape] = useState<
    | { type: "polygon"; points: [number, number][] }
    | { type: "circle"; center: [number, number]; radiusM: number }
    | null
  >(null);

  // ── Vertex label markers ──────────────────────────────────────────────────

  function updateVertexMarkers(
    points: [number, number][],
    currentMap: maplibregl.Map,
  ) {
    labelMarkersRef.current.forEach((m) => m.remove());
    labelMarkersRef.current = [];

    points.forEach(([lng, lat], i) => {
      const label = vertexLabel(i);
      const el = document.createElement("div");
      el.style.cssText = [
        "width:20px;height:20px;border-radius:50%",
        "background:#141619;border:1.5px solid #4A9EFF",
        "display:flex;align-items:center;justify-content:center",
        "font-size:9px;font-weight:700;color:#4A9EFF",
        "font-family:Inter,sans-serif;pointer-events:none",
      ].join(";");
      el.textContent = label;
      const marker = new maplibregl.Marker({ element: el, anchor: "center" })
        .setLngLat([lng, lat])
        .addTo(currentMap);
      labelMarkersRef.current.push(marker);
    });
  }

  function clearVertexMarkers() {
    labelMarkersRef.current.forEach((m) => m.remove());
    labelMarkersRef.current = [];
  }

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
        // Individual points (no MultiPoint — label markers handle these visually)
        pts.forEach(([lng, lat]) => {
          features.push({
            type: "Feature",
            geometry: { type: "Point", coordinates: [lng, lat] },
            properties: {},
          });
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
      filter: ["==", "$type", "Point"],
      paint: {
        "circle-radius": 4,
        "circle-color": "#4A9EFF",
        "circle-stroke-width": 1.5,
        "circle-stroke-color": "#0D0F12",
      },
    });

    return () => {
      clearVertexMarkers();
      [DRAFT_VERT, DRAFT_LINE, DRAFT_FILL].forEach((l) => {
        if (map.getLayer(l)) map.removeLayer(l);
      });
      if (map.getSource(DRAFT_SOURCE)) map.removeSource(DRAFT_SOURCE);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // ── Cursor coordinate tracking (always active) ────────────────────────────

  useEffect(() => {
    if (!map) return;
    const onMove = (e: maplibregl.MapMouseEvent) => {
      setCursorLatLon([e.lngLat.lat, e.lngLat.lng]);
    };
    const canvas = map.getCanvas();
    const onLeave = () => setCursorLatLon(null);
    map.on("mousemove", onMove);
    canvas.addEventListener("mouseleave", onLeave);
    return () => {
      map.off("mousemove", onMove);
      canvas.removeEventListener("mouseleave", onLeave);
    };
  }, [map]);

  // ── Marker placement click (when in marker mode) ─────────────────────────

  useEffect(() => {
    if (!map || drawMode !== "marker") return;
    map.getCanvas().style.cursor = "crosshair";
    const onClick = (e: maplibregl.MapMouseEvent) => {
      setPendingMarker({ lat: e.lngLat.lat, lon: e.lngLat.lng });
    };
    map.on("click", onClick);
    return () => {
      map.getCanvas().style.cursor = "";
      map.off("click", onClick);
    };
  }, [map, drawMode]);

  // ── Zone selection via map click (when not drawing) ───────────────────────

  useEffect(() => {
    if (!map || drawMode !== null) return;

    const onClickSelect = (e: maplibregl.MapMouseEvent) => {
      const features = map.queryRenderedFeatures(e.point, {
        layers: ["zones-fill"],
      });
      if (features.length > 0) {
        const zoneId = features[0].properties?.id as string;
        setSelectedZone(selectedZoneId === zoneId ? null : zoneId);
      } else {
        setSelectedZone(null);
      }
    };

    map.on("click", onClickSelect);
    return () => {
      map.off("click", onClickSelect);
    };
  }, [map, drawMode, selectedZoneId, setSelectedZone]);

  // ── Pointer cursor over zones (when not drawing) ──────────────────────────

  useEffect(() => {
    if (!map) return;
    const setPointer = () => {
      if (!drawMode) map.getCanvas().style.cursor = "pointer";
    };
    const clearPointer = () => {
      if (!drawMode) map.getCanvas().style.cursor = "";
    };
    map.on("mouseenter", "zones-fill", setPointer);
    map.on("mouseleave", "zones-fill", clearPointer);
    return () => {
      map.off("mouseenter", "zones-fill", setPointer);
      map.off("mouseleave", "zones-fill", clearPointer);
    };
  }, [map, drawMode]);

  // ── Map draw event handlers ───────────────────────────────────────────────

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
        updateVertexMarkers(polyPoints.current, map);
      } else if (drawMode === "circle") {
        if (!circleCenter.current) {
          circleCenter.current = [e.lngLat.lng, e.lngLat.lat];
        } else {
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
      clearVertexMarkers();
    };

    if (drawMode === "polygon" || drawMode === "circle") {
      canvas.style.cursor = "crosshair";
      map.on("mousemove", onMouseMove);
      map.on("click", onClick);
      map.on("dblclick", onDblClick);
    }
    // marker/measure modes manage their own cursor — don't reset here

    return () => {
      if (drawMode === "polygon" || drawMode === "circle") {
        canvas.style.cursor = "";
      }
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
    clearVertexMarkers();
    setDrawMode(null);
  }

  function handleDrawModeChange(mode: DrawMode) {
    polyPoints.current = [];
    circleCenter.current = null;
    mousePos.current = null;
    if (map) clearDraft(map);
    clearVertexMarkers();
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
        {map && <MarkerLayer map={map} />}
      </div>

      {/* Floating toolbar */}
      <MapToolbar drawMode={drawMode} onSetDrawMode={handleDrawModeChange} />

      {/* Left panel */}
      <div style={{ position: "absolute", top: 0, left: 0, zIndex: 10 }}>
        <ZoneListPanel />
      </div>

      {/* Cursor coordinates overlay */}
      {cursorLatLon && (
        <div
          style={{
            position: "absolute",
            bottom: "32px",
            left: "50%",
            transform: "translateX(-50%)",
            backgroundColor: "#141619CC",
            border: "1px solid #2A2F38",
            borderRadius: "6px",
            padding: "4px 10px",
            zIndex: 10,
            display: "flex",
            gap: "14px",
            pointerEvents: "none",
          }}
        >
          <CoordDisplay label="LAT" value={cursorLatLon[0]} />
          <CoordDisplay label="LON" value={cursorLatLon[1]} />
        </div>
      )}

      {/* Measure overlay */}
      {map && drawMode === "measure" && (
        <MeasureOverlay map={map} onExit={() => setDrawMode(null)} />
      )}

      {/* Right detail / merge panel */}
      {drawMode === "merge" ? (
        <MergeZonesPanel onClose={() => setDrawMode(null)} />
      ) : (
        <>
          <ZoneDetailPanel />
          <MarkerDetailPanel />
        </>
      )}

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

      {/* Place marker modal */}
      {pendingMarker && (
        <PlaceMarkerModal
          lat={pendingMarker.lat}
          lon={pendingMarker.lon}
          onClose={() => setPendingMarker(null)}
        />
      )}
    </div>
  );
}

function CoordDisplay({ label, value }: { label: string; value: number }) {
  return (
    <div style={{ display: "flex", alignItems: "baseline", gap: "5px" }}>
      <span style={{ fontSize: "9px", color: "#8B95A3", letterSpacing: "1px" }}>
        {label}
      </span>
      <span
        style={{
          fontSize: "11px",
          color: "#E8EAED",
          fontFamily: "JetBrains Mono, monospace",
        }}
      >
        {value.toFixed(6)}°
      </span>
    </div>
  );
}
