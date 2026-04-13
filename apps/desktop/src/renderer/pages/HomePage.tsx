import { useState, useRef, useEffect } from "react";
import maplibregl from "maplibre-gl";
import {
  Route,
  CheckCircle,
  AlertCircle,
  PauseCircle,
  Clock,
  Video,
  VideoOff,
  Camera,
} from "lucide-react";
import { useNodeStore } from "../stores/nodeStore";
import DevicePanel from "../components/fleet/DevicePanel";
import DeviceDetailPanel from "../components/fleet/DeviceDetailPanel";
import MissionMap, {
  type MapBase,
  type MapTheme,
} from "../components/map/MissionMap";
import MapStylePicker from "../components/map/MapStylePicker";
import NodeMarkers from "../components/map/NodeMarkers";
import HubMarker from "../components/map/HubMarker";
import { useHubLocation } from "../hooks/useHubLocation";
import { useMissionEngineStatus } from "../hooks/useSystem";
import * as api from "../lib/api";
import type { Node } from "../types";

// ── Mission status panel ───────────────────────────────────────────────────────

const STATUS_COLOR: Record<string, string> = {
  executing: "#3DD68C",
  paused: "#F5A623",
  completed: "#4A9EFF",
  aborted: "#F05252",
  failed: "#F05252",
  ready: "#999999",
  draft: "#999999",
};

const STATUS_LABEL: Record<string, string> = {
  executing: "RUNNING",
  paused: "PAUSED",
  completed: "DONE",
  aborted: "ABORTED",
  failed: "FAILED",
  ready: "READY",
  draft: "DRAFT",
};

function StatusIcon({ status }: { status: string }) {
  const props = { size: 13, strokeWidth: 2 } as const;
  if (status === "executing") return <Route {...props} color="#3DD68C" />;
  if (status === "paused") return <PauseCircle {...props} color="#F5A623" />;
  if (status === "completed") return <CheckCircle {...props} color="#4A9EFF" />;
  if (status === "aborted" || status === "failed")
    return <AlertCircle {...props} color="#F05252" />;
  return <Clock {...props} color="#999999" />;
}

function MissionStatusPanel() {
  const { data: engine } = useMissionEngineStatus();

  const hasActiveMission = !!engine?.mission_id;
  const status = engine?.status ?? "draft";
  const color = STATUS_COLOR[status] ?? "#999999";
  const label = STATUS_LABEL[status] ?? status.toUpperCase();
  const progress =
    engine && engine.total_steps > 0
      ? engine.current_step / engine.total_steps
      : 0;

  return (
    <div
      style={{
        width: "240px",
        height: "100%",
        backgroundColor: "#141414",
        borderRight: "1px solid #2D2D2D",
        borderTop: "1px solid #2D2D2D",
        borderTopRightRadius: "8px",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "0 10px 0 12px",
          height: "36px",
          backgroundColor: "#0D0D0D",
          borderBottom: "1px solid #2D2D2D",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            letterSpacing: "1px",
            color: "#999999",
            textTransform: "uppercase",
          }}
        >
          Mission
        </span>
        {hasActiveMission && (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "5px",
              padding: "2px 7px",
              borderRadius: "4px",
              backgroundColor: `${color}18`,
              border: `1px solid ${color}44`,
            }}
          >
            <StatusIcon status={status} />
            <span
              style={{
                fontSize: "9px",
                fontWeight: 700,
                color,
                letterSpacing: "0.5px",
              }}
            >
              {label}
            </span>
          </div>
        )}
      </div>

      {/* Body */}
      <div
        style={{
          padding: "10px 12px",
          display: "flex",
          flexDirection: "column",
          gap: "8px",
        }}
      >
        {!hasActiveMission ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              color: "#444444",
            }}
          >
            <Route size={14} strokeWidth={1.5} />
            <span style={{ fontSize: "11px" }}>No active mission</span>
          </div>
        ) : (
          <>
            {/* Mission name */}
            <span
              style={{
                fontSize: "12px",
                fontWeight: 600,
                color: "#EFEFEF",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {engine?.mission_name ?? "Unnamed Mission"}
            </span>

            {/* Step + percentage row */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "baseline",
              }}
            >
              <span style={{ fontSize: "10px", color: "#666666" }}>
                Step {engine?.current_step ?? 0} of {engine?.total_steps ?? 0}
              </span>
              <span style={{ fontSize: "10px", color: "#666666" }}>
                {Math.round(progress * 100)}%
              </span>
            </div>

            {/* Progress bar */}
            <div
              style={{
                height: "4px",
                borderRadius: "2px",
                backgroundColor: "#2D2D2D",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${Math.round(progress * 100)}%`,
                  borderRadius: "2px",
                  backgroundColor: color,
                  transition: "width 400ms ease",
                }}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Camera panel ───────────────────────────────────────────────────────────────

function CameraPanel({ nodes }: { nodes: Node[] }) {
  const cameraNodes = nodes.filter((n) =>
    n.specs?.capabilities?.some((c) => c.capability === "camera"),
  );

  const [selectedId, setSelectedId] = useState<string | null>(
    cameraNodes[0]?.id ?? null,
  );
  const [streamUrl, setStreamUrl] = useState<string | null>(null);
  const [loadingStream, setLoadingStream] = useState(false);

  const cameraNodeIds = cameraNodes.map((n) => n.id).join(",");

  // When camera nodes change, select first if nothing selected
  useEffect(() => {
    if (!selectedId && cameraNodes.length > 0) {
      setSelectedId(cameraNodes[0].id);
    } else if (selectedId && !cameraNodes.find((n) => n.id === selectedId)) {
      setSelectedId(cameraNodes[0]?.id ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cameraNodeIds]);

  // Fetch stream URL when selection changes
  useEffect(() => {
    if (!selectedId) {
      setStreamUrl(null);
      return;
    }
    setLoadingStream(true);
    api
      .getStreamUrl(selectedId)
      .then((r) => setStreamUrl(r.stream_url))
      .catch(() => setStreamUrl(null))
      .finally(() => setLoadingStream(false));
  }, [selectedId]);

  return (
    <div
      style={{
        width: "300px",
        height: "100%",
        backgroundColor: "#141414",
        borderLeft: "1px solid #2D2D2D",
        display: "flex",
        flexDirection: "column",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "0 12px",
          height: "36px",
          backgroundColor: "#0D0D0D",
          borderBottom: "1px solid #2D2D2D",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          flexShrink: 0,
        }}
      >
        <Video size={13} color="#999999" strokeWidth={2} />
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            letterSpacing: "1px",
            color: "#999999",
            textTransform: "uppercase",
          }}
        >
          Camera Feeds
        </span>
      </div>

      {/* Video viewport */}
      <div
        style={{
          width: "100%",
          aspectRatio: "16/9",
          backgroundColor: "#0D0D0D",
          borderBottom: "1px solid #2D2D2D",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          position: "relative",
          overflow: "hidden",
        }}
      >
        {cameraNodes.length === 0 ? (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "8px",
              color: "#444444",
            }}
          >
            <VideoOff size={28} strokeWidth={1.5} />
            <span style={{ fontSize: "11px" }}>No cameras available</span>
          </div>
        ) : loadingStream ? (
          <span style={{ fontSize: "11px", color: "#666666" }}>
            Connecting…
          </span>
        ) : streamUrl ? (
          <img
            src={streamUrl}
            alt="Camera feed"
            style={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={() => setStreamUrl(null)}
          />
        ) : (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              gap: "8px",
              color: "#444444",
            }}
          >
            <VideoOff size={28} strokeWidth={1.5} />
            <span style={{ fontSize: "11px" }}>No stream available</span>
          </div>
        )}

        {/* Selected camera label */}
        {streamUrl && selectedId && (
          <div
            style={{
              position: "absolute",
              bottom: "6px",
              left: "8px",
              backgroundColor: "#0D0D0D99",
              borderRadius: "4px",
              padding: "2px 7px",
              fontSize: "10px",
              color: "#EFEFEF",
              fontFamily: "Inter, sans-serif",
            }}
          >
            {nodes.find((n) => n.id === selectedId)?.name ??
              selectedId.slice(0, 6).toUpperCase()}
          </div>
        )}
      </div>

      {/* Camera list */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Section label */}
        <div
          style={{
            padding: "8px 12px 4px",
            fontSize: "10px",
            fontWeight: 600,
            letterSpacing: "0.8px",
            color: "#666666",
            textTransform: "uppercase",
            flexShrink: 0,
          }}
        >
          Available
        </div>

        {cameraNodes.length === 0 ? (
          <div
            style={{
              padding: "16px 12px",
              fontSize: "11px",
              color: "#444444",
              display: "flex",
              alignItems: "center",
              gap: "8px",
            }}
          >
            <Camera size={14} strokeWidth={1.5} />
            No camera-equipped devices detected
          </div>
        ) : (
          cameraNodes.map((node) => {
            const isSelected = node.id === selectedId;
            const isOnline = node.status === "online";
            return (
              <button
                key={node.id}
                onClick={() => setSelectedId(node.id)}
                style={{
                  width: "100%",
                  textAlign: "left",
                  padding: "8px 12px",
                  backgroundColor: isSelected ? "#1C1C1C" : "transparent",
                  border: "none",
                  borderBottom: "1px solid #2D2D2D",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  transition: "background-color 150ms",
                }}
                onMouseEnter={(e) => {
                  if (!isSelected)
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "#191919";
                }}
                onMouseLeave={(e) => {
                  if (!isSelected)
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "transparent";
                }}
              >
                {/* Status dot */}
                <div
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    backgroundColor: isOnline ? "#3DD68C" : "#444444",
                    flexShrink: 0,
                  }}
                />

                {/* Name + id */}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: "12px",
                      fontWeight: isSelected ? 600 : 400,
                      color: isSelected ? "#EFEFEF" : "#999999",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {node.name}
                  </div>
                  <div
                    style={{
                      fontSize: "10px",
                      color: "#666666",
                      fontFamily: "Inter, sans-serif",
                    }}
                  >
                    {node.id.slice(0, 6).toUpperCase()}
                  </div>
                </div>

                {/* Active indicator */}
                {isSelected && (
                  <div
                    style={{
                      width: "6px",
                      height: "6px",
                      borderRadius: "50%",
                      backgroundColor: "#4A9EFF",
                      flexShrink: 0,
                    }}
                  />
                )}
              </button>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── Top-right toolbar button ───────────────────────────────────────────────────

function ToolbarButton({
  title,
  onClick,
  active,
  children,
}: {
  title: string;
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
}) {
  const [hovered, setHovered] = useState(false);
  return (
    <button
      title={title}
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        width: "32px",
        height: "32px",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "6px",
        border: active ? "1px solid #4A9EFF44" : "1px solid #2D2D2D",
        backgroundColor: active ? "#4A9EFF18" : hovered ? "#1C1C1C" : "#141414",
        color: active ? "#4A9EFF" : hovered ? "#EFEFEF" : "#999999",
        cursor: "pointer",
        transition: "background-color 150ms, color 150ms, border-color 150ms",
      }}
    >
      {children}
    </button>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function HomePage() {
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const nodes = useNodeStore((s) => s.nodes);
  const nodesArr = Object.values(nodes);
  const selectedNode = selectedNodeId ? nodes[selectedNodeId] : null;
  const hubLocation = useHubLocation();

  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);

  const [mapBase, setMapBase] = useState<MapBase>("standard");
  const [mapTheme, setMapTheme] = useState<MapTheme>("dark");
  const [savedView, setSavedView] = useState<{
    center: [number, number];
    zoom: number;
  } | null>(null);

  const [showCameraPanel, setShowCameraPanel] = useState(false);

  function handleMapReady(m: maplibregl.Map) {
    mapRef.current = m;
    setMap(m);
  }

  function saveAndSwitch(base: MapBase, theme: MapTheme) {
    if (mapRef.current) {
      const c = mapRef.current.getCenter();
      setSavedView({ center: [c.lng, c.lat], zoom: mapRef.current.getZoom() });
    }
    setMap(null);
    setMapBase(base);
    setMapTheme(theme);
  }

  function centerOnHub() {
    if (!mapRef.current || !hubLocation) return;
    mapRef.current.flyTo({
      center: hubLocation,
      zoom: 15,
      duration: 1000,
    });
  }

  const styleKey = `${mapBase}-${mapTheme}`;

  return (
    <div
      style={{
        display: "flex",
        flex: 1,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Map fills the entire background */}
      <div style={{ position: "absolute", inset: 0 }}>
        <MissionMap
          key={styleKey}
          mapBase={mapBase}
          mapTheme={mapTheme}
          initialCenter={savedView?.center}
          initialZoom={savedView?.zoom}
          onMapReady={handleMapReady}
        />
        {map && <NodeMarkers map={map} />}
        {map && <HubMarker map={map} location={hubLocation} />}
      </div>

      {/* Map style picker — top-center, with hub button */}
      <MapStylePicker
        mapBase={mapBase}
        mapTheme={mapTheme}
        onChangeBase={(base) => saveAndSwitch(base, mapTheme)}
        onChangeTheme={(theme) => saveAndSwitch(mapBase, theme)}
        position="top-center"
        onCenterHub={centerOnHub}
      />

      {/* Top-right toolbar — camera button, shifts left when panel is open */}
      <div
        style={{
          position: "absolute",
          top: "12px",
          right: showCameraPanel ? "310px" : "10px",
          zIndex: 20,
          display: "flex",
          gap: "6px",
        }}
      >
        <ToolbarButton
          title="Camera feeds"
          onClick={() => setShowCameraPanel((v) => !v)}
          active={showCameraPanel}
        >
          <Video size={15} strokeWidth={2} />
        </ToolbarButton>
      </div>

      {/* Left column: fleet panel (top half) + mission panel (bottom) */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          bottom: 0,
          zIndex: 10,
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          pointerEvents: "none",
        }}
      >
        <div style={{ height: "50%", pointerEvents: "auto" }}>
          <DevicePanel readOnly />
        </div>
        <div style={{ height: "50%", pointerEvents: "auto" }}>
          <MissionStatusPanel />
        </div>
      </div>

      {/* Device detail panel — attached to the right of the fleet panel */}
      {selectedNode && (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: "240px",
            height: "100%",
            zIndex: 10,
          }}
        >
          <DeviceDetailPanel node={selectedNode} readOnly />
        </div>
      )}

      {/* Camera panel — right edge, full height */}
      {showCameraPanel && (
        <div
          style={{
            position: "absolute",
            top: 0,
            right: 0,
            height: "100%",
            zIndex: 10,
          }}
        >
          <CameraPanel nodes={nodesArr} />
        </div>
      )}
    </div>
  );
}
