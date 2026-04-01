/**
 * MarkerLayer — renders MapMarkers as distinct HTML markers on a MapLibre map.
 * Each marker type has its own icon shape so it reads differently from zone vertex dots.
 * Clicking a marker selects it; the selected marker shows a glow ring.
 */
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import { useMarkerStore } from "../../stores/markerStore";
import { useZoneStore } from "../../stores/zoneStore";
import type { MarkerType, MapMarker } from "../../types";

const MARKER_TYPE_COLORS: Record<MarkerType, string> = {
  home_position: "#3DD68C",
  waypoint: "#4A9EFF",
  reference: "#A78BFA",
  hazard: "#F05252",
  custom: "#F5A623",
};

const MARKER_TYPE_ICONS: Record<MarkerType, string> = {
  home_position: "⌂",
  waypoint: "◆",
  reference: "✦",
  hazard: "⚠",
  custom: "●",
};

function createMarkerElement(
  marker: MapMarker,
  selected: boolean,
): HTMLElement {
  const color =
    marker.color || MARKER_TYPE_COLORS[marker.marker_type] || "#4A9EFF";
  const icon = MARKER_TYPE_ICONS[marker.marker_type] || "●";

  const wrap = document.createElement("div");
  wrap.style.cssText = [
    "display:flex;flex-direction:column;align-items:center",
    "pointer-events:auto;cursor:pointer",
  ].join(";");

  // Selection ring
  if (selected) {
    const ring = document.createElement("div");
    ring.style.cssText = [
      "position:absolute;width:40px;height:40px;border-radius:50%",
      `border:2px solid ${color};opacity:0.5`,
      "top:-6px;left:50%;transform:translateX(-50%)",
      "pointer-events:none",
      `box-shadow:0 0 10px ${color}88`,
    ].join(";");
    wrap.style.position = "relative";
    wrap.appendChild(ring);
  }

  // Pin body (rotated square → teardrop pointing down)
  const pin = document.createElement("div");
  pin.style.cssText = [
    "width:28px;height:28px",
    `background:${color};border:2px solid #0D0F12`,
    selected ? "border-radius:50% 50% 50% 0" : "border-radius:50% 50% 50% 0",
    "transform:rotate(-45deg)",
    "display:flex;align-items:center;justify-content:center",
    `box-shadow:0 2px 8px rgba(0,0,0,0.5)${selected ? `,0 0 12px ${color}88` : ""}`,
    "flex-shrink:0",
  ].join(";");

  const iconEl = document.createElement("div");
  iconEl.style.cssText = [
    "transform:rotate(45deg)",
    "color:#0D0F12;font-size:12px;line-height:1",
    "display:flex;align-items:center;justify-content:center",
    "width:100%;height:100%",
  ].join(";");
  iconEl.textContent = icon;
  pin.appendChild(iconEl);

  // Label
  const label = document.createElement("div");
  label.style.cssText = [
    `background:${color};color:#0D0F12`,
    "font-size:9px;font-weight:700",
    "font-family:Inter,sans-serif",
    "padding:2px 5px;border-radius:3px",
    "white-space:nowrap;margin-top:3px",
    `border:1.5px solid #0D0F12`,
    `box-shadow:0 1px 4px rgba(0,0,0,0.4)${selected ? `,0 0 8px ${color}66` : ""}`,
    "max-width:90px;overflow:hidden;text-overflow:ellipsis",
  ].join(";");
  label.textContent = marker.name;

  wrap.appendChild(pin);
  wrap.appendChild(label);
  return wrap;
}

interface MarkerLayerProps {
  map: maplibregl.Map;
}

export default function MarkerLayer({ map }: MarkerLayerProps) {
  const markers = useMarkerStore((s) => s.markers);
  const selectedMarkerId = useMarkerStore((s) => s.selectedMarkerId);
  const setSelectedMarker = useMarkerStore((s) => s.setSelectedMarker);
  const setSelectedZone = useZoneStore((s) => s.setSelectedZone);
  const mapMarkersRef = useRef<Record<string, maplibregl.Marker>>({});

  useEffect(() => {
    const existing = mapMarkersRef.current;
    const currentIds = new Set(Object.keys(markers));

    // Remove stale markers
    for (const id of Object.keys(existing)) {
      if (!currentIds.has(id)) {
        existing[id].remove();
        delete existing[id];
      }
    }

    // Rebuild all (handles selection state changes too)
    for (const marker of Object.values(markers)) {
      existing[marker.id]?.remove();
      const selected = marker.id === selectedMarkerId;
      const el = createMarkerElement(marker, selected);
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        setSelectedZone(null);
        setSelectedMarker(selected ? null : marker.id);
      });
      const m = new maplibregl.Marker({ element: el, anchor: "bottom" })
        .setLngLat([marker.lon, marker.lat])
        .addTo(map);
      existing[marker.id] = m;
    }
  }, [map, markers, selectedMarkerId, setSelectedMarker, setSelectedZone]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      for (const m of Object.values(mapMarkersRef.current)) m.remove();
      mapMarkersRef.current = {};
    };
  }, []);

  return null;
}
