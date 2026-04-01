/**
 * HubMarker — renders a fixed, visually distinct "device hub" icon on the map.
 * The hub is the operator station running Henosync.
 */
import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";

function createHubElement(): HTMLElement {
  const wrap = document.createElement("div");
  wrap.style.cssText = [
    "display:flex;flex-direction:column;align-items:center",
    "pointer-events:none",
  ].join(";");

  // Outer pulse ring
  const ring = document.createElement("div");
  ring.style.cssText = [
    "position:absolute",
    "width:44px;height:44px;border-radius:50%",
    "border:1.5px solid #4A9EFF",
    "opacity:0.35",
    "top:50%;left:50%;transform:translate(-50%,-50%)",
    "animation:hub-ping 2.4s ease-out infinite",
  ].join(";");

  // Inject keyframes once
  if (!document.getElementById("hub-ping-style")) {
    const style = document.createElement("style");
    style.id = "hub-ping-style";
    style.textContent = `
      @keyframes hub-ping {
        0%   { transform: translate(-50%,-50%) scale(1);   opacity: 0.35; }
        70%  { transform: translate(-50%,-50%) scale(1.8); opacity: 0; }
        100% { transform: translate(-50%,-50%) scale(1.8); opacity: 0; }
      }
    `;
    document.head.appendChild(style);
  }

  // Main circle body
  const body = document.createElement("div");
  body.style.cssText = [
    "width:28px;height:28px;border-radius:50%",
    "background:#0D1A2D;border:2px solid #4A9EFF",
    "display:flex;align-items:center;justify-content:center",
    "box-shadow:0 0 12px #4A9EFF66,0 2px 8px rgba(0,0,0,0.6)",
    "position:relative",
  ].join(";");

  // WiFi/antenna SVG icon inside
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("width", "14");
  svg.setAttribute("height", "14");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "#4A9EFF");
  svg.setAttribute("stroke-width", "2");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  // Wifi arcs (top two) + dot
  const arc1 = document.createElementNS("http://www.w3.org/2000/svg", "path");
  arc1.setAttribute("d", "M5 12.55a11 11 0 0 1 14.08 0");
  const arc2 = document.createElementNS("http://www.w3.org/2000/svg", "path");
  arc2.setAttribute("d", "M1.42 9a16 16 0 0 1 21.16 0");
  const arc3 = document.createElementNS("http://www.w3.org/2000/svg", "path");
  arc3.setAttribute("d", "M8.53 16.11a6 6 0 0 1 6.95 0");
  const dot = document.createElementNS("http://www.w3.org/2000/svg", "line");
  dot.setAttribute("x1", "12");
  dot.setAttribute("y1", "20");
  dot.setAttribute("x2", "12.01");
  dot.setAttribute("y2", "20");
  dot.setAttribute("stroke-width", "3");
  svg.appendChild(arc1);
  svg.appendChild(arc2);
  svg.appendChild(arc3);
  svg.appendChild(dot);
  body.appendChild(ring);
  body.appendChild(svg);

  // Label
  const label = document.createElement("div");
  label.style.cssText = [
    "background:#0D1A2D;color:#4A9EFF",
    "font-size:9px;font-weight:700",
    "font-family:Inter,sans-serif;letter-spacing:0.5px",
    "padding:2px 6px;border-radius:3px;margin-top:4px",
    "border:1px solid #4A9EFF44",
    "box-shadow:0 1px 4px rgba(0,0,0,0.5)",
    "white-space:nowrap",
  ].join(";");
  label.textContent = "HUB";

  wrap.appendChild(body);
  wrap.appendChild(label);
  return wrap;
}

interface HubMarkerProps {
  map: maplibregl.Map;
  location: [number, number]; // [lng, lat]
}

export default function HubMarker({ map, location }: HubMarkerProps) {
  const markerRef = useRef<maplibregl.Marker | null>(null);

  // Create marker once
  useEffect(() => {
    const el = createHubElement();
    markerRef.current = new maplibregl.Marker({ element: el, anchor: "center" })
      .setLngLat(location)
      .addTo(map);

    return () => {
      markerRef.current?.remove();
      markerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [map]);

  // Update position when geolocation resolves
  useEffect(() => {
    markerRef.current?.setLngLat(location);
  }, [location]);

  return null;
}
