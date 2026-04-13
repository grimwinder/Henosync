import { useState, useEffect, useRef } from "react";
import {
  Pentagon,
  Circle,
  Combine,
  Eye,
  EyeOff,
  MapPin,
  Ruler,
  LocateFixed,
  BookmarkPlus,
  FolderOpen,
  Trash2,
  Check,
  X,
  Loader,
} from "lucide-react";
import type { DrawMode } from "../../pages/ZonesPage";
import { useZoneStore } from "../../stores/zoneStore";
import { useMarkerStore } from "../../stores/markerStore";
import { useMapLayouts, type MapLayout } from "../../hooks/useMapLayouts";

// ── Helpers ────────────────────────────────────────────────────────────────────

function formatSavedAt(iso: string): string {
  const d = new Date(iso);
  return (
    d.toLocaleDateString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
    }) +
    " · " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
  );
}

// ── Tool button ────────────────────────────────────────────────────────────────

interface ToolButtonProps {
  icon: React.ReactNode;
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

function ToolButton({
  icon,
  label,
  active = false,
  disabled = false,
  onClick,
}: ToolButtonProps) {
  return (
    <button
      onClick={onClick}
      title={label}
      disabled={disabled}
      style={{
        width: "32px",
        height: "32px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "5px",
        border: `1px solid ${active ? "#4A9EFF" : "transparent"}`,
        backgroundColor: active ? "#4A9EFF22" : "transparent",
        color: disabled ? "#3A3F48" : active ? "#4A9EFF" : "#8B95A3",
        cursor: disabled ? "default" : "pointer",
        transition: "all 150ms",
        flexShrink: 0,
      }}
      onMouseEnter={(e) => {
        if (!active && !disabled) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "#1C1F24";
          (e.currentTarget as HTMLButtonElement).style.color = "#E8EAED";
        }
      }}
      onMouseLeave={(e) => {
        if (!active && !disabled) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "transparent";
          (e.currentTarget as HTMLButtonElement).style.color = "#8B95A3";
        }
      }}
    >
      {icon}
    </button>
  );
}

function Divider() {
  return (
    <div
      style={{
        width: "1px",
        height: "20px",
        backgroundColor: "#2A2F38",
        margin: "0 2px",
        flexShrink: 0,
      }}
    />
  );
}

// ── Save-as popup ──────────────────────────────────────────────────────────────

function SavePopup({
  onSave,
  onClose,
}: {
  onSave: (name: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function commit() {
    if (!name.trim()) return;
    onSave(name.trim());
    onClose();
  }

  return (
    <div
      style={{
        position: "absolute",
        top: "calc(100% + 8px)",
        right: 0,
        width: "220px",
        backgroundColor: "#141619",
        border: "1px solid #2A2F38",
        borderRadius: "8px",
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        padding: "10px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        zIndex: 30,
      }}
    >
      <span
        style={{
          fontSize: "10px",
          fontWeight: 700,
          letterSpacing: "0.8px",
          color: "#555F6E",
        }}
      >
        SAVE MAP AS
      </span>
      <input
        ref={inputRef}
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") onClose();
        }}
        placeholder="Map name…"
        style={{
          backgroundColor: "#0D0F12",
          border: "1px solid #2A2F38",
          borderRadius: "5px",
          color: "#E8EAED",
          fontSize: "12px",
          padding: "6px 8px",
          outline: "none",
        }}
      />
      <div style={{ display: "flex", gap: "6px" }}>
        <button
          onClick={onClose}
          style={{
            flex: 1,
            padding: "6px",
            borderRadius: "5px",
            border: "1px solid #2A2F38",
            backgroundColor: "transparent",
            color: "#8B95A3",
            fontSize: "11px",
            cursor: "pointer",
          }}
        >
          Cancel
        </button>
        <button
          onClick={commit}
          disabled={!name.trim()}
          style={{
            flex: 1,
            padding: "6px",
            borderRadius: "5px",
            border: `1px solid ${name.trim() ? "#4A9EFF55" : "#2A2F38"}`,
            backgroundColor: name.trim() ? "#4A9EFF18" : "transparent",
            color: name.trim() ? "#4A9EFF" : "#3A3F48",
            fontSize: "11px",
            fontWeight: 600,
            cursor: name.trim() ? "pointer" : "default",
          }}
        >
          Save
        </button>
      </div>
    </div>
  );
}

// ── Open popup ─────────────────────────────────────────────────────────────────

function OpenPopup({
  layouts,
  loadingId,
  onLoad,
  onDelete,
  onClose,
}: {
  layouts: MapLayout[];
  loadingId: string | null;
  onLoad: (layout: MapLayout) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  const [confirmId, setConfirmId] = useState<string | null>(null);

  return (
    <div
      style={{
        position: "absolute",
        top: "calc(100% + 8px)",
        right: 0,
        width: "280px",
        backgroundColor: "#141619",
        border: "1px solid #2A2F38",
        borderRadius: "8px",
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        zIndex: 30,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "9px 12px",
          borderBottom: "1px solid #2A2F38",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "0.8px",
            color: "#555F6E",
          }}
        >
          SAVED MAPS
        </span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "#555F6E",
            cursor: "pointer",
            display: "flex",
            padding: 0,
          }}
        >
          <X size={12} />
        </button>
      </div>

      {/* Layout list */}
      <div style={{ maxHeight: "320px", overflowY: "auto" }}>
        {layouts.length === 0 ? (
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              fontSize: "12px",
              color: "#555F6E",
              lineHeight: 1.5,
            }}
          >
            No saved maps yet.
            <br />
            Use Save As to create one.
          </div>
        ) : (
          layouts.map((layout) => {
            const isLoading = loadingId === layout.id;
            const isConfirming = confirmId === layout.id;

            return (
              <div
                key={layout.id}
                style={{
                  padding: "10px 12px",
                  borderBottom: "1px solid #1C1F24",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                  backgroundColor: isLoading ? "#141619" : "transparent",
                }}
              >
                {isConfirming ? (
                  /* Delete confirmation */
                  <div
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                    }}
                  >
                    <span
                      style={{
                        flex: 1,
                        fontSize: "11px",
                        color: "#8B95A3",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Delete "{layout.name}"?
                    </span>
                    <button
                      onClick={() => setConfirmId(null)}
                      style={{
                        fontSize: "10px",
                        padding: "2px 7px",
                        borderRadius: "4px",
                        border: "1px solid #2A2F38",
                        backgroundColor: "transparent",
                        color: "#8B95A3",
                        cursor: "pointer",
                        flexShrink: 0,
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        onDelete(layout.id);
                        setConfirmId(null);
                      }}
                      style={{
                        fontSize: "10px",
                        padding: "2px 7px",
                        borderRadius: "4px",
                        border: "1px solid #F05252",
                        backgroundColor: "#F0525222",
                        color: "#F05252",
                        cursor: "pointer",
                        flexShrink: 0,
                      }}
                    >
                      Delete
                    </button>
                  </div>
                ) : (
                  <>
                    {/* Info */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: "12px",
                          fontWeight: 600,
                          color: isLoading ? "#555F6E" : "#E8EAED",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {layout.name}
                      </div>
                      <div
                        style={{
                          fontSize: "10px",
                          color: "#555F6E",
                          marginTop: "2px",
                        }}
                      >
                        {formatSavedAt(layout.savedAt)}
                      </div>
                      <div
                        style={{
                          fontSize: "10px",
                          color: "#3A3F48",
                          marginTop: "1px",
                        }}
                      >
                        {layout.zones.length} zone
                        {layout.zones.length !== 1 ? "s" : ""}
                        {" · "}
                        {layout.markers.length} marker
                        {layout.markers.length !== 1 ? "s" : ""}
                      </div>
                    </div>

                    {/* Actions */}
                    {isLoading ? (
                      <Loader
                        size={14}
                        color="#555F6E"
                        style={{
                          animation: "spin 1s linear infinite",
                          flexShrink: 0,
                        }}
                      />
                    ) : (
                      <div
                        style={{ display: "flex", gap: "2px", flexShrink: 0 }}
                      >
                        <button
                          onClick={() => {
                            onLoad(layout);
                            onClose();
                          }}
                          disabled={loadingId !== null}
                          title="Load this map"
                          style={{
                            display: "flex",
                            alignItems: "center",
                            gap: "4px",
                            padding: "4px 8px",
                            borderRadius: "5px",
                            border: "1px solid #2A2F38",
                            backgroundColor: "transparent",
                            color: loadingId ? "#3A3F48" : "#8B95A3",
                            fontSize: "11px",
                            cursor: loadingId ? "default" : "pointer",
                            transition: "all 100ms",
                          }}
                          onMouseEnter={(e) => {
                            if (!loadingId) {
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.backgroundColor = "#1C1F24";
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.color = "#E8EAED";
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (!loadingId) {
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.backgroundColor = "transparent";
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.color = "#8B95A3";
                            }
                          }}
                        >
                          <Check size={11} />
                          Load
                        </button>
                        <button
                          onClick={() => setConfirmId(layout.id)}
                          disabled={loadingId !== null}
                          title="Delete"
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            width: "26px",
                            height: "26px",
                            borderRadius: "5px",
                            border: "none",
                            backgroundColor: "transparent",
                            color: loadingId ? "#3A3F48" : "#8B95A3",
                            cursor: loadingId ? "default" : "pointer",
                            transition: "all 100ms",
                          }}
                          onMouseEnter={(e) => {
                            if (!loadingId) {
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.color = "#F05252";
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.backgroundColor = "#F0525210";
                            }
                          }}
                          onMouseLeave={(e) => {
                            if (!loadingId) {
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.color = "#8B95A3";
                              (
                                e.currentTarget as HTMLButtonElement
                              ).style.backgroundColor = "transparent";
                            }
                          }}
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })
        )}
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

// ── Toolbar ────────────────────────────────────────────────────────────────────

interface MapToolbarProps {
  drawMode: DrawMode;
  onSetDrawMode: (mode: DrawMode) => void;
  onFlyToHub: () => void;
}

export default function MapToolbar({
  drawMode,
  onSetDrawMode,
  onFlyToHub,
}: MapToolbarProps) {
  const showVertexMarkers = useZoneStore((s) => s.showVertexMarkers);
  const setShowVertexMarkers = useZoneStore((s) => s.setShowVertexMarkers);
  const zones = useZoneStore((s) => Object.values(s.zones));
  const markers = useMarkerStore((s) => Object.values(s.markers));

  const { layouts, loadingId, save, remove, load } = useMapLayouts();

  const [activePopup, setActivePopup] = useState<"save" | "open" | null>(null);
  const popupRef = useRef<HTMLDivElement>(null);

  // Close popup on outside click
  useEffect(() => {
    if (!activePopup) return;
    function onDown(e: MouseEvent) {
      if (popupRef.current && !popupRef.current.contains(e.target as Node)) {
        setActivePopup(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [activePopup]);

  const hasContent = zones.length > 0 || markers.length > 0;

  return (
    <div
      style={{
        position: "absolute",
        top: "12px",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 20,
        display: "flex",
        alignItems: "center",
        gap: "2px",
        backgroundColor: "#141619",
        border: "1px solid #2A2F38",
        borderRadius: "8px",
        padding: "4px",
        boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
      }}
    >
      {/* Drawing tools */}
      <ToolButton
        icon={<Pentagon size={15} />}
        label="Draw polygon zone"
        active={drawMode === "polygon"}
        onClick={() => onSetDrawMode(drawMode === "polygon" ? null : "polygon")}
      />
      <ToolButton
        icon={<Circle size={15} />}
        label="Draw circle zone"
        active={drawMode === "circle"}
        onClick={() => onSetDrawMode(drawMode === "circle" ? null : "circle")}
      />
      <ToolButton
        icon={<Combine size={15} />}
        label="Merge zones"
        active={drawMode === "merge"}
        onClick={() => onSetDrawMode(drawMode === "merge" ? null : "merge")}
      />
      <ToolButton
        icon={<MapPin size={15} />}
        label="Place marker"
        active={drawMode === "marker"}
        onClick={() => onSetDrawMode(drawMode === "marker" ? null : "marker")}
      />
      <ToolButton
        icon={<Ruler size={15} />}
        label="Measure distance"
        active={drawMode === "measure"}
        onClick={() => onSetDrawMode(drawMode === "measure" ? null : "measure")}
      />

      <Divider />

      <ToolButton
        icon={<LocateFixed size={15} />}
        label="Fly to hub"
        onClick={onFlyToHub}
      />

      <Divider />

      <ToolButton
        icon={showVertexMarkers ? <Eye size={15} /> : <EyeOff size={15} />}
        label={
          showVertexMarkers ? "Hide vertex markers" : "Show vertex markers"
        }
        onClick={() => setShowVertexMarkers(!showVertexMarkers)}
      />

      <Divider />

      {/* Save / Open — relative wrapper anchors the popups */}
      <div
        ref={popupRef}
        style={{ position: "relative", display: "flex", gap: "2px" }}
      >
        <ToolButton
          icon={<BookmarkPlus size={15} />}
          label="Save map as…"
          active={activePopup === "save"}
          disabled={!hasContent}
          onClick={() => setActivePopup(activePopup === "save" ? null : "save")}
        />
        <ToolButton
          icon={<FolderOpen size={15} />}
          label="Open saved map"
          active={activePopup === "open"}
          onClick={() => setActivePopup(activePopup === "open" ? null : "open")}
        />

        {activePopup === "save" && (
          <SavePopup
            onSave={(name) => save(name)}
            onClose={() => setActivePopup(null)}
          />
        )}
        {activePopup === "open" && (
          <OpenPopup
            layouts={layouts}
            loadingId={loadingId}
            onLoad={(layout) => load(layout)}
            onDelete={(id) => remove(id)}
            onClose={() => setActivePopup(null)}
          />
        )}
      </div>

      {/* Drawing hint */}
      {(drawMode === "polygon" || drawMode === "circle") && (
        <>
          <Divider />
          <span
            style={{
              fontSize: "10px",
              color: "#F5A623",
              paddingRight: "6px",
              whiteSpace: "nowrap",
            }}
          >
            {drawMode === "polygon"
              ? "Click to add points · Double-click to finish · Esc to cancel"
              : "Click to set centre · Click again to set radius · Esc to cancel"}
          </span>
        </>
      )}
    </div>
  );
}
