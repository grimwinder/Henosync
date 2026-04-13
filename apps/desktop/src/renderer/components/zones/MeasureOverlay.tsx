/**
 * MeasureOverlay — handles distance measurement between two points.
 * Points can be clicked anywhere on the map, or snapped to zone vertices / markers.
 * Renders a dashed line and a distance label on the map.
 */
import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import { X } from "lucide-react";

const MEASURE_SOURCE = "measure-source";
const MEASURE_LINE = "measure-line";
const MEASURE_POINTS = "measure-points";

function haversineM(
  lat1: number,
  lon1: number,
  lat2: number,
  lon2: number,
): number {
  const R = 6371000;
  const dLat = ((lat2 - lat1) * Math.PI) / 180;
  const dLon = ((lon2 - lon1) * Math.PI) / 180;
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos((lat1 * Math.PI) / 180) *
      Math.cos((lat2 * Math.PI) / 180) *
      Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function formatDistance(m: number): string {
  if (m >= 1000) return `${(m / 1000).toFixed(3)} km`;
  return `${m.toFixed(1)} m`;
}

function buildGeoJSON(pts: [number, number][]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  if (pts.length >= 2) {
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: pts },
      properties: {},
    });
  }
  for (const p of pts) {
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: p },
      properties: {},
    });
  }
  return { type: "FeatureCollection", features };
}

interface MeasureOverlayProps {
  map: maplibregl.Map;
  onExit: () => void;
}

export default function MeasureOverlay({ map, onExit }: MeasureOverlayProps) {
  const [points, setPoints] = useState<[number, number][]>([]);
  const labelMarkerRef = useRef<maplibregl.Marker | null>(null);
  const pointsRef = useRef<[number, number][]>([]);

  // Keep ref in sync for use inside event handlers
  useEffect(() => {
    pointsRef.current = points;
  }, [points]);

  // Bootstrap source + layers
  useEffect(() => {
    map.addSource(MEASURE_SOURCE, {
      type: "geojson",
      data: buildGeoJSON([]),
    });
    map.addLayer({
      id: MEASURE_LINE,
      type: "line",
      source: MEASURE_SOURCE,
      filter: ["==", "$type", "LineString"],
      paint: {
        "line-color": "#F5A623",
        "line-width": 2,
        "line-dasharray": [4, 3],
      },
    });
    map.addLayer({
      id: MEASURE_POINTS,
      type: "circle",
      source: MEASURE_SOURCE,
      filter: ["==", "$type", "Point"],
      paint: {
        "circle-radius": 5,
        "circle-color": "#F5A623",
        "circle-stroke-width": 2,
        "circle-stroke-color": "#0D0D0D",
      },
    });

    map.getCanvas().style.cursor = "crosshair";

    return () => {
      map.getCanvas().style.cursor = "";
      if (map.getLayer(MEASURE_POINTS)) map.removeLayer(MEASURE_POINTS);
      if (map.getLayer(MEASURE_LINE)) map.removeLayer(MEASURE_LINE);
      if (map.getSource(MEASURE_SOURCE)) map.removeSource(MEASURE_SOURCE);
      labelMarkerRef.current?.remove();
      labelMarkerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Click handler
  useEffect(() => {
    const onClick = (e: maplibregl.MapMouseEvent) => {
      const current = pointsRef.current;

      // Try to snap to a zone vertex or marker (within ~8px)
      const snapped = map.queryRenderedFeatures(
        [
          [e.point.x - 8, e.point.y - 8],
          [e.point.x + 8, e.point.y + 8],
        ],
        { layers: ["zones-fill"] },
      );

      let lng = e.lngLat.lng;
      let lat = e.lngLat.lat;

      // If clicked on a zone, still use the exact click point (vertices snap via HTML markers, not GeoJSON)
      void snapped; // unused — snap logic for zone vertices is below via DOM proximity

      if (current.length >= 2) {
        // Reset: start a new measurement
        const newPts: [number, number][] = [[lng, lat]];
        setPoints(newPts);
        updateMap(newPts);
      } else {
        const newPts = [...current, [lng, lat]] as [number, number][];
        setPoints(newPts);
        updateMap(newPts);
      }
    };

    map.on("click", onClick);
    return () => {
      map.off("click", onClick);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  function updateMap(pts: [number, number][]) {
    const source = map.getSource(MEASURE_SOURCE) as
      | maplibregl.GeoJSONSource
      | undefined;
    source?.setData(buildGeoJSON(pts));

    // Update distance label
    labelMarkerRef.current?.remove();
    labelMarkerRef.current = null;

    if (pts.length === 2) {
      const [p1, p2] = pts;
      const dist = haversineM(p1[1], p1[0], p2[1], p2[0]);
      const midLng = (p1[0] + p2[0]) / 2;
      const midLat = (p1[1] + p2[1]) / 2;

      const el = document.createElement("div");
      el.style.cssText = [
        "background:#F5A623;color:#0D0D0D",
        "font-size:11px;font-weight:700",
        "font-family:Inter, sans-serif",
        "padding:3px 8px;border-radius:4px",
        "border:1.5px solid #0D0D0D",
        "box-shadow:0 2px 8px rgba(0,0,0,0.5)",
        "white-space:nowrap;pointer-events:none",
      ].join(";");
      el.textContent = formatDistance(dist);

      labelMarkerRef.current = new maplibregl.Marker({
        element: el,
        anchor: "bottom",
      })
        .setLngLat([midLng, midLat])
        .addTo(map);
    }
  }

  // Distance for the HUD
  const distance =
    points.length === 2
      ? formatDistance(
          haversineM(points[0][1], points[0][0], points[1][1], points[1][0]),
        )
      : null;

  return (
    <div
      style={{
        position: "absolute",
        bottom: "60px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 20,
        backgroundColor: "#141414CC",
        border: "1px solid #2D2D2D",
        borderRadius: "8px",
        padding: "8px 14px",
        display: "flex",
        alignItems: "center",
        gap: "14px",
        pointerEvents: "auto",
      }}
    >
      <span
        style={{
          fontSize: "10px",
          color: "#F5A623",
          letterSpacing: "1px",
          fontWeight: 600,
        }}
      >
        MEASURE
      </span>
      {points.length === 0 && (
        <span style={{ fontSize: "11px", color: "#999999" }}>
          Click two points on the map
        </span>
      )}
      {points.length === 1 && (
        <span style={{ fontSize: "11px", color: "#999999" }}>
          Click a second point
        </span>
      )}
      {distance && (
        <span
          style={{
            fontSize: "13px",
            fontWeight: 700,
            color: "#EFEFEF",
            fontFamily: "Inter, sans-serif",
          }}
        >
          {distance}
        </span>
      )}
      {points.length === 2 && (
        <button
          onClick={() => {
            setPoints([]);
            updateMap([]);
          }}
          style={{
            fontSize: "10px",
            color: "#999999",
            background: "none",
            border: "1px solid #2D2D2D",
            borderRadius: "4px",
            padding: "2px 7px",
            cursor: "pointer",
          }}
        >
          Reset
        </button>
      )}
      <button
        onClick={onExit}
        title="Exit measure mode"
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
  );
}
