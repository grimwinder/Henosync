import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { useTrailStore } from "../../stores/trailStore";

interface NodeTrailsProps {
  map: maplibregl.Map;
}

export default function NodeTrails({ map }: NodeTrailsProps) {
  const gpsTrails = useTrailStore((s) => s.gpsTrails);
  const initializedRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const [nodeId, points] of Object.entries(gpsTrails)) {
      const sourceId = `trail-${nodeId}`;
      const layerId = `trail-layer-${nodeId}`;

      const geojson: GeoJSON.FeatureCollection = {
        type: "FeatureCollection",
        features:
          points.length >= 2
            ? [
                {
                  type: "Feature",
                  geometry: { type: "LineString", coordinates: points },
                  properties: {},
                },
              ]
            : [],
      };

      if (!initializedRef.current.has(nodeId)) {
        if (!map.getSource(sourceId)) {
          map.addSource(sourceId, { type: "geojson", data: geojson });
          map.addLayer({
            id: layerId,
            type: "line",
            source: sourceId,
            layout: { "line-join": "round", "line-cap": "round" },
            paint: {
              "line-color": "#4A9EFF",
              "line-width": 2,
              "line-opacity": 0.8,
            },
          });
        }
        initializedRef.current.add(nodeId);
      } else {
        const source = map.getSource(sourceId) as
          | maplibregl.GeoJSONSource
          | undefined;
        source?.setData(geojson);
      }
    }
  }, [gpsTrails, map]);

  // Remove layers/sources on unmount
  useEffect(() => {
    return () => {
      for (const nodeId of initializedRef.current) {
        const layerId = `trail-layer-${nodeId}`;
        const sourceId = `trail-${nodeId}`;
        if (map.getLayer(layerId)) map.removeLayer(layerId);
        if (map.getSource(sourceId)) map.removeSource(sourceId);
      }
    };
  }, [map]);

  return null;
}
