/**
 * ZoneLayer — renders all zones onto a MapLibre map as GeoJSON fill + outline layers.
 * Handles polygon and circle zones. Reacts to zone store changes.
 * Shows vertex markers (A, B, C…) for the selected zone.
 */
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import type { FeatureCollection, Feature, Geometry } from "geojson";
import { useZoneStore } from "../../stores/zoneStore";
import { vertexLabel } from "./ZoneDetailPanel";
import type { Zone } from "../../types";

const SOURCE_ID = "zones-source";
const FILL_LAYER = "zones-fill";
const FILL_NOGO_LAYER = "zones-fill-nogo";
const LINE_LAYER = "zones-line";
const NOGO_PATTERN = "nogo-hatch";

/** Build a seamlessly-tiling 45° red diagonal stripe pattern as ImageData. */
function createNoGoPattern(): ImageData {
  const size = 12;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.clearRect(0, 0, size, size);
  ctx.strokeStyle = "#F05252";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(size, size);
  ctx.moveTo(-1, size - 1);
  ctx.lineTo(1, size + 1);
  ctx.moveTo(size - 1, -1);
  ctx.lineTo(size + 1, 1);
  ctx.stroke();
  return ctx.getImageData(0, 0, size, size);
}

const ZONE_COLORS: Record<string, string> = {
  perimeter: "#4A9EFF",
  no_go: "#F05252",
  safe_return: "#3DD68C",
  coverage: "#A78BFA",
  alert: "#F5A623",
  custom: "#8B95A3",
};

/** Convert a circle (center + radius_m) to a GeoJSON polygon approximation. */
function circleToPolygon(
  lat: number,
  lon: number,
  radiusM: number,
  steps = 64,
): number[][] {
  const R = 6371000;
  const coords: number[][] = [];
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * 2 * Math.PI;
    const dLat = (radiusM / R) * (180 / Math.PI) * Math.cos(angle);
    const dLon =
      ((radiusM / R) * (180 / Math.PI) * Math.sin(angle)) /
      Math.cos((lat * Math.PI) / 180);
    coords.push([lon + dLon, lat + dLat]);
  }
  return coords;
}

function zoneToFeature(zone: Zone, selected: boolean): Feature | null {
  let coordinates: number[][][];

  if (zone.shape === "circle") {
    if (!zone.center || zone.radius_m == null) return null;
    coordinates = [
      circleToPolygon(zone.center.lat, zone.center.lon, zone.radius_m),
    ];
  } else {
    if (zone.points.length < 3) return null;
    const ring = zone.points.map((p) => [p.lon, p.lat]);
    ring.push(ring[0]);
    coordinates = [ring];
  }

  const color = zone.color || ZONE_COLORS[zone.zone_type] || "#8B95A3";

  return {
    type: "Feature",
    id: zone.id,
    geometry: { type: "Polygon", coordinates } as Geometry,
    properties: {
      id: zone.id,
      name: zone.name,
      zone_type: zone.zone_type,
      color,
      selected,
    },
  };
}

function buildGeoJSON(
  zones: Zone[],
  selectedZoneId: string | null,
  highlightedIds: Set<string> = new Set(),
): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: zones
      .map((z) =>
        zoneToFeature(z, z.id === selectedZoneId || highlightedIds.has(z.id)),
      )
      .filter(Boolean) as Feature[],
  };
}

interface ZoneLayerProps {
  map: maplibregl.Map;
}

export default function ZoneLayer({ map }: ZoneLayerProps) {
  const zones = useZoneStore((s) => s.zones);
  const selectedZoneId = useZoneStore((s) => s.selectedZoneId);
  const mergeHighlightedIds = useZoneStore((s) => s.mergeHighlightedIds);
  const showVertexMarkers = useZoneStore((s) => s.showVertexMarkers);
  const vertexMarkersRef = useRef<maplibregl.Marker[]>([]);

  // Bootstrap source + layers once
  useEffect(() => {
    if (!map.getSource(SOURCE_ID)) {
      // Register the no-go hatch pattern
      if (!map.hasImage(NOGO_PATTERN)) {
        map.addImage(NOGO_PATTERN, createNoGoPattern(), { pixelRatio: 2 });
      }

      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: buildGeoJSON([], null),
      });

      // Base fill for all zones
      map.addLayer({
        id: FILL_LAYER,
        type: "fill",
        source: SOURCE_ID,
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": ["case", ["get", "selected"], 0.32, 0.15],
        },
      });

      // Hatch overlay for no-go zones only
      map.addLayer({
        id: FILL_NOGO_LAYER,
        type: "fill",
        source: SOURCE_ID,
        filter: ["==", ["get", "zone_type"], "no_go"],
        paint: {
          "fill-pattern": NOGO_PATTERN,
          "fill-opacity": ["case", ["get", "selected"], 0.6, 0.35],
        },
      });

      // Outline — rendered above fills so it's never obscured
      map.addLayer({
        id: LINE_LAYER,
        type: "line",
        source: SOURCE_ID,
        paint: {
          "line-color": ["get", "color"],
          "line-width": ["case", ["get", "selected"], 3, 2],
          "line-opacity": ["case", ["get", "selected"], 1, 0.85],
        },
      });
    }

    return () => {
      vertexMarkersRef.current.forEach((m) => m.remove());
      vertexMarkersRef.current = [];
      if (map.getLayer(FILL_NOGO_LAYER)) map.removeLayer(FILL_NOGO_LAYER);
      if (map.getLayer(LINE_LAYER)) map.removeLayer(LINE_LAYER);
      if (map.getLayer(FILL_LAYER)) map.removeLayer(FILL_LAYER);
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Update GeoJSON whenever zones or selection changes
  useEffect(() => {
    const source = map.getSource(SOURCE_ID) as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!source) return;
    const effectiveSelectedId = selectedZoneId;
    const data = buildGeoJSON(
      Object.values(zones),
      effectiveSelectedId,
      mergeHighlightedIds,
    );
    source.setData(data);
  }, [map, zones, selectedZoneId, mergeHighlightedIds]);

  // Show/hide vertex markers based on toggle and selection
  useEffect(() => {
    vertexMarkersRef.current.forEach((m) => m.remove());
    vertexMarkersRef.current = [];

    if (!showVertexMarkers) return;

    // Show markers for selected zone only; if nothing selected, show all zones
    const zonesToShow = selectedZoneId
      ? [zones[selectedZoneId]].filter(Boolean)
      : Object.values(zones);

    for (const zone of zonesToShow) {
      if (!zone) continue;
      const color = zone.color || ZONE_COLORS[zone.zone_type] || "#8B95A3";

      if (zone.shape === "circle" && zone.center) {
        // Dot marker for circle center
        const el = document.createElement("div");
        el.style.cssText = [
          "width:10px;height:10px;border-radius:50%",
          `background:${color};border:1.5px solid #0D0F12`,
          "pointer-events:none",
        ].join(";");
        const marker = new maplibregl.Marker({ element: el, anchor: "center" })
          .setLngLat([zone.center.lon, zone.center.lat])
          .addTo(map);
        vertexMarkersRef.current.push(marker);
      } else if (zone.shape === "polygon" && zone.points.length >= 3) {
        zone.points.forEach((pt, i) => {
          const label = vertexLabel(i);
          const el = document.createElement("div");
          el.style.cssText = [
            "width:20px;height:20px;border-radius:50%",
            "background:#141619;border:1.5px solid " + color,
            "display:flex;align-items:center;justify-content:center",
            `font-size:9px;font-weight:700;color:${color}`,
            "font-family:Inter,sans-serif;pointer-events:none",
          ].join(";");
          el.textContent = label;
          const marker = new maplibregl.Marker({
            element: el,
            anchor: "center",
          })
            .setLngLat([pt.lon, pt.lat])
            .addTo(map);
          vertexMarkersRef.current.push(marker);
        });
      }
    }
  }, [map, selectedZoneId, zones, showVertexMarkers]);

  return null;
}
