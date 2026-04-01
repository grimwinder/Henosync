import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// Default centre — Monash University Clayton campus
export const HUB_LOCATION: [number, number] = [145.1312, -37.9105]; // [lng, lat]
const DEFAULT_CENTER = HUB_LOCATION;
const DEFAULT_ZOOM = 15;

interface MissionMapProps {
  /** Called once the map is fully loaded — use to attach sources/layers */
  onMapReady?: (map: maplibregl.Map) => void;
  /** Optional MBTiles URL for offline tiles (Phase 6) */
  tilesUrl?: string;
  className?: string;
}

// Dark blank style — no external tile server required in dev
function buildStyle(tilesUrl?: string): maplibregl.StyleSpecification {
  if (tilesUrl) {
    return {
      version: 8,
      sources: {
        offline: {
          type: "raster",
          url: tilesUrl,
          tileSize: 256,
        },
      },
      layers: [
        {
          id: "offline-tiles",
          type: "raster",
          source: "offline",
        },
      ],
    };
  }

  // Dark vector style using MapLibre's demo tiles (dev only)
  return {
    version: 8,
    sources: {
      "osm-tiles": {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap contributors",
      },
    },
    layers: [
      {
        id: "background",
        type: "background",
        paint: { "background-color": "#0D0F12" },
      },
      {
        id: "osm",
        type: "raster",
        source: "osm-tiles",
        paint: {
          "raster-opacity": 0.6,
          // Invert to a dark style: subtract from 1 for each channel
          "raster-brightness-min": 0,
          "raster-brightness-max": 0.3,
          "raster-saturation": -0.8,
          "raster-contrast": 0.1,
        },
      },
    ],
  };
}

export default function MissionMap({
  onMapReady,
  tilesUrl,
  className,
}: MissionMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(tilesUrl),
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      attributionControl: false,
    });

    map.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-right",
    );

    map.addControl(
      new maplibregl.NavigationControl({ showCompass: true }),
      "bottom-right",
    );

    map.on("load", () => {
      onMapReady?.(map);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: "100%", height: "100%", backgroundColor: "#0D0F12" }}
    />
  );
}
