/**
 * ZoneLayer — renders all zones onto a MapLibre map as GeoJSON fill + outline layers.
 * Handles polygon and circle zones. Reacts to zone store changes.
 */
import { useEffect } from "react";
import maplibregl from "maplibre-gl";
import type { FeatureCollection, Feature, Geometry } from "geojson";
import { useZoneStore } from "../../stores/zoneStore";
import type { Zone } from "../../types";

const SOURCE_ID = "zones-source";
const FILL_LAYER = "zones-fill";
const LINE_LAYER = "zones-line";

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

function zoneToFeature(zone: Zone): Feature | null {
  let coordinates: number[][][];

  if (zone.shape === "circle") {
    if (!zone.center || zone.radius_m == null) return null;
    coordinates = [
      circleToPolygon(zone.center.lat, zone.center.lon, zone.radius_m),
    ];
  } else {
    if (zone.points.length < 3) return null;
    const ring = zone.points.map((p) => [p.lon, p.lat]);
    // Close the ring
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
    },
  };
}

function buildGeoJSON(zones: Zone[]): FeatureCollection {
  return {
    type: "FeatureCollection",
    features: zones.map(zoneToFeature).filter(Boolean) as Feature[],
  };
}

interface ZoneLayerProps {
  map: maplibregl.Map;
}

export default function ZoneLayer({ map }: ZoneLayerProps) {
  const zones = useZoneStore((s) => s.zones);

  // Bootstrap source + layers once
  useEffect(() => {
    if (!map.getSource(SOURCE_ID)) {
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: buildGeoJSON([]),
      });

      map.addLayer({
        id: FILL_LAYER,
        type: "fill",
        source: SOURCE_ID,
        paint: {
          "fill-color": ["get", "color"],
          "fill-opacity": 0.15,
        },
      });

      map.addLayer({
        id: LINE_LAYER,
        type: "line",
        source: SOURCE_ID,
        paint: {
          "line-color": ["get", "color"],
          "line-width": 2,
          "line-opacity": 0.85,
        },
      });
    }

    return () => {
      if (map.getLayer(FILL_LAYER)) map.removeLayer(FILL_LAYER);
      if (map.getLayer(LINE_LAYER)) map.removeLayer(LINE_LAYER);
      if (map.getSource(SOURCE_ID)) map.removeSource(SOURCE_ID);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Update GeoJSON whenever zones change
  useEffect(() => {
    const source = map.getSource(SOURCE_ID) as
      | maplibregl.GeoJSONSource
      | undefined;
    if (!source) return;
    source.setData(buildGeoJSON(Object.values(zones)));
  }, [map, zones]);

  return null;
}
