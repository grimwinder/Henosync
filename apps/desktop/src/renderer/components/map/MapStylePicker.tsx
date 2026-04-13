import { useState, useEffect, useRef } from "react";
import {
  Layers,
  Map,
  Globe,
  Mountain,
  ScanLine,
  Moon,
  Sun,
  Crosshair,
} from "lucide-react";
import type { MapBase, MapTheme } from "./MissionMap";

// ── Option definitions ─────────────────────────────────────────────────────────

const BASE_OPTIONS: { id: MapBase; label: string; icon: React.ReactNode }[] = [
  { id: "standard", label: "Standard", icon: <Map size={15} /> },
  { id: "satellite", label: "Satellite", icon: <Globe size={15} /> },
  { id: "terrain", label: "Terrain", icon: <Mountain size={15} /> },
  { id: "topo", label: "Topo", icon: <ScanLine size={15} /> },
];

// ── Props ──────────────────────────────────────────────────────────────────────

interface MapStylePickerProps {
  mapBase: MapBase;
  mapTheme: MapTheme;
  onChangeBase: (base: MapBase) => void;
  onChangeTheme: (theme: MapTheme) => void;
  /** Where the trigger button sits on the map */
  position?: "top-center" | "top-right";
  /** Optional: render a center-on-hub button alongside the layers button */
  onCenterHub?: () => void;
}

// ── Component ──────────────────────────────────────────────────────────────────

export default function MapStylePicker({
  mapBase,
  mapTheme,
  onChangeBase,
  onChangeTheme,
  position = "top-center",
  onCenterHub,
}: MapStylePickerProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const triggerStyle: React.CSSProperties =
    position === "top-center"
      ? {
          position: "absolute",
          top: "12px",
          left: "50%",
          transform: "translateX(-50%)",
          zIndex: 20,
        }
      : {
          position: "absolute",
          top: "12px",
          right: "12px",
          zIndex: 20,
        };

  const popupAlign: React.CSSProperties =
    position === "top-center"
      ? { left: "50%", transform: "translateX(-50%)" }
      : { right: 0 };

  const btnStyle = (active: boolean): React.CSSProperties => ({
    width: "32px",
    height: "32px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    borderRadius: "8px",
    backgroundColor: active ? "#4A9EFF22" : "#141414",
    border: `1px solid ${active ? "#4A9EFF" : "#2D2D2D"}`,
    color: active ? "#4A9EFF" : "#999999",
    cursor: "pointer",
    boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
    transition: "all 150ms",
  });

  function addHover(btn: HTMLButtonElement, active: boolean) {
    if (!active) {
      btn.style.backgroundColor = "#1C1C1C";
      btn.style.color = "#EFEFEF";
    }
  }
  function removeHover(btn: HTMLButtonElement, active: boolean) {
    if (!active) {
      btn.style.backgroundColor = "#141414";
      btn.style.color = "#999999";
    }
  }

  return (
    <div ref={ref} style={triggerStyle}>
      {/* Button row: optional hub button + layers button */}
      <div style={{ display: "flex", gap: "6px" }}>
        {onCenterHub && (
          <button
            onClick={onCenterHub}
            title="Center on hub"
            style={btnStyle(false)}
            onMouseEnter={(e) =>
              addHover(e.currentTarget as HTMLButtonElement, false)
            }
            onMouseLeave={(e) =>
              removeHover(e.currentTarget as HTMLButtonElement, false)
            }
          >
            <Crosshair size={15} />
          </button>
        )}

        {/* Layers / map style button */}
        <button
          onClick={() => setOpen((v) => !v)}
          title="Map style"
          style={btnStyle(open)}
          onMouseEnter={(e) =>
            addHover(e.currentTarget as HTMLButtonElement, open)
          }
          onMouseLeave={(e) =>
            removeHover(e.currentTarget as HTMLButtonElement, open)
          }
        >
          <Layers size={15} />
        </button>
      </div>

      {/* Popup */}
      {open && (
        <div
          style={{
            position: "absolute",
            top: "calc(100% + 8px)",
            ...popupAlign,
            backgroundColor: "#141414",
            border: "1px solid #2D2D2D",
            borderRadius: "10px",
            padding: "14px",
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
            width: "200px",
            display: "flex",
            flexDirection: "column",
            gap: "12px",
          }}
        >
          {/* Map type */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span
              style={{
                fontSize: "10px",
                fontWeight: 600,
                letterSpacing: "0.8px",
                color: "#666666",
                textTransform: "uppercase",
              }}
            >
              Map Type
            </span>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "6px",
              }}
            >
              {BASE_OPTIONS.map(({ id, label, icon }) => {
                const active = mapBase === id;
                return (
                  <button
                    key={id}
                    onClick={() => {
                      onChangeBase(id);
                      setOpen(false);
                    }}
                    style={{
                      display: "flex",
                      flexDirection: "column",
                      alignItems: "center",
                      gap: "5px",
                      padding: "10px 6px",
                      borderRadius: "7px",
                      border: `1px solid ${active ? "#4A9EFF" : "#2D2D2D"}`,
                      backgroundColor: active ? "#4A9EFF18" : "#0D0D0D",
                      color: active ? "#4A9EFF" : "#999999",
                      cursor: "pointer",
                      fontSize: "10px",
                      fontWeight: 500,
                      transition: "all 120ms",
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        (
                          e.currentTarget as HTMLButtonElement
                        ).style.backgroundColor = "#1C1C1C";
                        (e.currentTarget as HTMLButtonElement).style.color =
                          "#EFEFEF";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        (
                          e.currentTarget as HTMLButtonElement
                        ).style.backgroundColor = "#0D0D0D";
                        (e.currentTarget as HTMLButtonElement).style.color =
                          "#999999";
                      }
                    }}
                  >
                    {icon}
                    {label}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Divider */}
          <div style={{ height: "1px", backgroundColor: "#2D2D2D" }} />

          {/* Theme toggle */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <span
              style={{
                fontSize: "10px",
                fontWeight: 600,
                letterSpacing: "0.8px",
                color: "#666666",
                textTransform: "uppercase",
              }}
            >
              Theme
            </span>
            <div style={{ display: "flex", gap: "6px" }}>
              {(["dark", "light"] as MapTheme[]).map((t) => {
                const active = mapTheme === t;
                return (
                  <button
                    key={t}
                    onClick={() => {
                      onChangeTheme(t);
                      setOpen(false);
                    }}
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: "5px",
                      padding: "7px 0",
                      borderRadius: "7px",
                      border: `1px solid ${active ? "#4A9EFF" : "#2D2D2D"}`,
                      backgroundColor: active ? "#4A9EFF18" : "#0D0D0D",
                      color: active ? "#4A9EFF" : "#999999",
                      cursor: "pointer",
                      fontSize: "11px",
                      fontWeight: 500,
                      transition: "all 120ms",
                    }}
                    onMouseEnter={(e) => {
                      if (!active) {
                        (
                          e.currentTarget as HTMLButtonElement
                        ).style.backgroundColor = "#1C1C1C";
                        (e.currentTarget as HTMLButtonElement).style.color =
                          "#EFEFEF";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!active) {
                        (
                          e.currentTarget as HTMLButtonElement
                        ).style.backgroundColor = "#0D0D0D";
                        (e.currentTarget as HTMLButtonElement).style.color =
                          "#999999";
                      }
                    }}
                  >
                    {t === "dark" ? <Moon size={11} /> : <Sun size={11} />}
                    {t === "dark" ? "Dark" : "Light"}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
