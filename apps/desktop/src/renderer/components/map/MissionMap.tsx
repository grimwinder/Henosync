import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

// Default centre — Monash University Clayton campus
export const HUB_LOCATION: [number, number] = [145.1312, -37.9105]; // [lng, lat]
const DEFAULT_CENTER = HUB_LOCATION;
const DEFAULT_ZOOM = 15;

// ── Map style types ────────────────────────────────────────────────────────────

export type MapBase = "standard" | "satellite" | "terrain" | "topo";
export type MapTheme = "dark" | "light";

function buildStyle(
  base: MapBase = "standard",
  theme: MapTheme = "dark",
  tilesUrl?: string,
): maplibregl.StyleSpecification | string {
  if (tilesUrl) {
    return {
      version: 8,
      sources: { offline: { type: "raster", url: tilesUrl, tileSize: 256 } },
      layers: [{ id: "offline-tiles", type: "raster", source: "offline" }],
    };
  }

  switch (base) {
    case "standard":
      // Carto hosted vector styles — no API key required
      return theme === "dark"
        ? "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json"
        : "https://basemaps.cartocdn.com/gl/voyager-gl-style/style.json";

    case "satellite":
      return {
        version: 8,
        sources: {
          satellite: {
            type: "raster",
            tiles: [
              "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            maxzoom: 19,
            attribution:
              "Tiles © Esri — Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP",
          },
        },
        layers: [
          ...(theme === "dark"
            ? ([
                {
                  id: "dark-bg",
                  type: "background",
                  paint: { "background-color": "#000" },
                },
              ] as maplibregl.LayerSpecification[])
            : []),
          {
            id: "satellite",
            type: "raster",
            source: "satellite",
            paint:
              theme === "dark"
                ? { "raster-brightness-max": 0.75, "raster-saturation": -0.2 }
                : {},
          },
        ],
      };

    case "terrain":
      return {
        version: 8,
        sources: {
          topo: {
            type: "raster",
            tiles: ["https://tile.opentopomap.org/{z}/{x}/{y}.png"],
            tileSize: 256,
            maxzoom: 17,
            attribution: "© OpenTopoMap contributors",
          },
        },
        layers: [
          {
            id: "topo",
            type: "raster",
            source: "topo",
            paint:
              theme === "dark"
                ? {
                    "raster-brightness-max": 0.5,
                    "raster-saturation": -0.5,
                    "raster-contrast": 0.2,
                  }
                : {},
          },
        ],
      };

    case "topo":
      // ESRI World Hillshade — pure terrain, no roads or labels.
      // A CSS SVG edge-detection filter (applied to the canvas below) turns
      // the smooth hillshade into contour-like lines on a black background.
      return {
        version: 8,
        sources: {
          hillshade: {
            type: "raster",
            tiles: [
              "https://services.arcgisonline.com/ArcGIS/rest/services/Elevation/World_Hillshade/MapServer/tile/{z}/{y}/{x}",
            ],
            tileSize: 256,
            maxzoom: 16,
            attribution:
              "Tiles © Esri — Esri, USGS, NGA, NASA, CGIAR, N Robinson, NCEAS, NLS, OS, NMA, Geodatastyrelsen, Rijkswaterstaat, GSA, Geoland, FGDC, SEC",
          },
        },
        layers: [
          {
            id: "hillshade",
            type: "raster",
            source: "hillshade",
          },
        ],
      };
  }
}

// ── Component ──────────────────────────────────────────────────────────────────

interface MissionMapProps {
  /** Called once the map is fully loaded — use to attach sources/layers */
  onMapReady?: (map: maplibregl.Map) => void;
  /** Base map type */
  mapBase?: MapBase;
  /** Colour theme */
  mapTheme?: MapTheme;
  /** Override starting centre [lng, lat] */
  initialCenter?: [number, number];
  /** Override starting zoom */
  initialZoom?: number;
  /** Optional MBTiles URL for offline tiles (Phase 6) */
  tilesUrl?: string;
  className?: string;
}

export default function MissionMap({
  onMapReady,
  mapBase = "standard",
  mapTheme = "dark",
  initialCenter,
  initialZoom,
  tilesUrl,
  className,
}: MissionMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: buildStyle(mapBase, mapTheme, tilesUrl),
      center: initialCenter ?? DEFAULT_CENTER,
      zoom: initialZoom ?? DEFAULT_ZOOM,
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

    // Topo: inject an SVG Laplacian edge-detection filter and apply it to the
    // WebGL canvas only — extracts elevation-change edges from the ESRI hillshade
    // tiles, producing white contour-like lines on pure black. HTML overlay
    // markers (hub, zone labels) sit outside the canvas and are unaffected.
    if (mapBase === "topo" && containerRef.current) {
      const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
      svg.setAttribute("width", "0");
      svg.setAttribute("height", "0");
      svg.style.position = "absolute";
      svg.id = "topo-filter-defs";
      svg.innerHTML = `
        <defs>
          <filter id="topo-lines" color-interpolation-filters="sRGB"
                  x="0%" y="0%" width="100%" height="100%">
            <!-- Desaturate to greyscale -->
            <feColorMatrix type="saturate" values="0" result="grey"/>
            <!-- Slight blur reduces tile-seam noise before edge detection -->
            <feGaussianBlur in="grey" stdDeviation="0.6" result="blurred"/>
            <!-- Laplacian 3×3 kernel: highlights elevation-change edges -->
            <feConvolveMatrix in="blurred" order="3"
              kernelMatrix="-1 -1 -1 -1 8 -1 -1 -1 -1"
              result="edges"/>
            <!-- Amplify edges and clamp — produces bright lines on black -->
            <feComponentTransfer in="edges">
              <feFuncR type="linear" slope="5" intercept="0"/>
              <feFuncG type="linear" slope="5" intercept="0"/>
              <feFuncB type="linear" slope="5" intercept="0"/>
            </feComponentTransfer>
          </filter>
        </defs>`;
      containerRef.current.appendChild(svg);

      const canvas = map.getCanvas();
      canvas.style.filter = "url(#topo-lines)";
    }

    map.on("load", () => {
      onMapReady?.(map);
    });

    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      document.getElementById("topo-filter-defs")?.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: "100%", height: "100%", backgroundColor: "#0D0D0D" }}
    />
  );
}
