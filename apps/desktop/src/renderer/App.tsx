import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./lib/queryClient";
import { wsManager } from "./lib/websocket";
import { useHealth, useViconConnection } from "./hooks/useSystem";
import { useSystemStore } from "./stores/systemStore";
import { connectVicon, disconnectVicon, getViconObjects, setViconOrigin } from "./lib/api";
import NavMenu from "./components/nav/NavMenu";
import HomePage from "./pages/HomePage";
import ZonesPage from "./pages/ZonesPage";
import DevicesPage from "./pages/DevicesPage";
import PluginsPage from "./pages/PluginsPage";
import MissionPage from "./pages/MissionPage";
import type { AppPage } from "./types/ui";
import type { VICONStatus } from "./types";

type DragStyle = React.CSSProperties & { WebkitAppRegion: string };

// ── VICON panel ────────────────────────────────────────────────────────────────

function VICONPanel({
  conn,
  onChanged,
}: {
  conn: VICONStatus | undefined;
  onChanged: () => void;
}) {
  const { data: objects = [], isFetched: objectsFetched } = useQuery({
    queryKey: ["vicon-objects"],
    queryFn: getViconObjects,
    enabled: conn?.connected ?? false,
    refetchInterval: 5_000,
    retry: false,
  });

  const [host, setHost] = useState(conn?.host ?? "");
  const [port, setPort] = useState(conn?.port ?? 801);
  const [connecting, setConnecting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [originLat, setOriginLat] = useState(conn?.home_lat?.toString() ?? "");
  const [originLon, setOriginLon] = useState(conn?.home_lon?.toString() ?? "");
  const [savingOrigin, setSavingOrigin] = useState(false);
  const [originErr, setOriginErr] = useState<string | null>(null);

  async function handleSaveOrigin() {
    const lat = Number(originLat);
    const lon = Number(originLon);
    if (originLat.trim() === "" || originLon.trim() === "" || Number.isNaN(lat) || Number.isNaN(lon)) {
      setOriginErr("Enter both latitude and longitude");
      return;
    }
    setSavingOrigin(true);
    setOriginErr(null);
    try {
      await setViconOrigin(lat, lon);
      onChanged();
    } catch (e) {
      setOriginErr(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setSavingOrigin(false);
    }
  }

  async function handleConnect() {
    const h = host.trim();
    if (!h) return;
    setConnecting(true);
    setErr(null);
    try {
      await connectVicon(h, port);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Connection failed");
    } finally {
      setConnecting(false);
    }
  }

  async function handleDisconnect() {
    try {
      await disconnectVicon();
      onChanged();
    } catch {}
  }

  return (
    <div
      style={{
        position: "absolute",
        top: "calc(100% + 6px)",
        right: 0,
        width: "260px",
        backgroundColor: "#1C1C1C",
        border: "1px solid #2D2D2D",
        borderRadius: "6px",
        padding: "14px",
        zIndex: 200,
        boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
      }}
    >
      <div
        style={{
          fontSize: "10px",
          fontWeight: 700,
          letterSpacing: "1px",
          color: "#666666",
          textTransform: "uppercase",
          marginBottom: "12px",
        }}
      >
        VICON System
      </div>

      <div
        style={{
          marginBottom: "14px",
          paddingBottom: "14px",
          borderBottom: "1px solid #2D2D2D",
        }}
      >
        <div
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "1px",
            color: "#666666",
            textTransform: "uppercase",
            marginBottom: "8px",
          }}
        >
          Arena Origin
        </div>
        <div style={{ fontSize: "11px", color: "#8B95A3", marginBottom: "8px" }}>
          Real-world lat/lon of the VICON arena's (0, 0) point — needed to draw
          zones/markers in VICON mode.
        </div>
        <div style={{ display: "flex", gap: "6px", marginBottom: "8px" }}>
          <input
            type="number"
            placeholder="Latitude"
            value={originLat}
            onChange={(e) => {
              setOriginLat(e.target.value);
              setOriginErr(null);
            }}
            style={{
              padding: "7px 10px",
              backgroundColor: "#141414",
              border: "1px solid #2D2D2D",
              borderRadius: "6px",
              fontSize: "12px",
              color: "#EFEFEF",
              outline: "none",
              fontFamily: "Inter, sans-serif",
              width: "50%",
              boxSizing: "border-box",
            }}
          />
          <input
            type="number"
            placeholder="Longitude"
            value={originLon}
            onChange={(e) => {
              setOriginLon(e.target.value);
              setOriginErr(null);
            }}
            style={{
              padding: "7px 10px",
              backgroundColor: "#141414",
              border: "1px solid #2D2D2D",
              borderRadius: "6px",
              fontSize: "12px",
              color: "#EFEFEF",
              outline: "none",
              fontFamily: "Inter, sans-serif",
              width: "50%",
              boxSizing: "border-box",
            }}
          />
        </div>
        {originErr && (
          <div style={{ fontSize: "11px", color: "#F05252", marginBottom: "8px" }}>
            {originErr}
          </div>
        )}
        <button
          onClick={handleSaveOrigin}
          disabled={savingOrigin}
          style={{
            width: "100%",
            padding: "7px 0",
            borderRadius: "6px",
            backgroundColor: savingOrigin ? "#2D2D2D" : "#4A9EFF",
            border: "none",
            color: savingOrigin ? "#999999" : "white",
            fontSize: "12px",
            fontWeight: 500,
            cursor: savingOrigin ? "not-allowed" : "pointer",
          }}
        >
          {savingOrigin ? "Saving…" : "Save Origin"}
        </button>
      </div>

      {conn?.connected ? (
        <>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              marginBottom: "6px",
            }}
          >
            <div
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "#3DD68C",
                flexShrink: 0,
              }}
            />
            <span style={{ fontSize: "12px", color: "#EFEFEF" }}>
              {conn.host}:{conn.port}
            </span>
          </div>
          <div style={{ marginBottom: "14px" }}>
            {!objectsFetched ? (
              <span style={{ fontSize: "11px", color: "#8B95A3" }}>
                Querying objects…
              </span>
            ) : objects.length === 0 ? (
              <span style={{ fontSize: "11px", color: "#8B95A3" }}>
                No objects visible
              </span>
            ) : (
              <div
                style={{ display: "flex", flexDirection: "column", gap: "3px" }}
              >
                {objects.map((name) => (
                  <div
                    key={name}
                    style={{
                      fontSize: "11px",
                      color: "#EFEFEF",
                      padding: "3px 7px",
                      backgroundColor: "#252A31",
                      borderRadius: "4px",
                      fontFamily: "Inter, sans-serif",
                    }}
                  >
                    {name}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button
            onClick={handleDisconnect}
            style={{
              width: "100%",
              padding: "7px 0",
              borderRadius: "6px",
              background: "none",
              border: "1px solid #F0525240",
              color: "#F05252",
              fontSize: "12px",
              cursor: "pointer",
            }}
          >
            Disconnect
          </button>
        </>
      ) : (
        <>
          {conn?.host && (
            <div
              style={{
                fontSize: "11px",
                color: "#F05252",
                marginBottom: "10px",
              }}
            >
              Not connected to {conn.host}
            </div>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
            <input
              type="text"
              placeholder="Host (e.g. 192.168.1.50)"
              value={host}
              onChange={(e) => {
                setHost(e.target.value);
                setErr(null);
              }}
              onKeyDown={(e) => e.key === "Enter" && handleConnect()}
              style={{
                padding: "7px 10px",
                backgroundColor: "#141414",
                border: "1px solid #2D2D2D",
                borderRadius: "6px",
                fontSize: "12px",
                color: "#EFEFEF",
                outline: "none",
                fontFamily: "Inter, sans-serif",
                width: "100%",
                boxSizing: "border-box",
              }}
            />
            <input
              type="number"
              placeholder="Port"
              value={port}
              onChange={(e) => setPort(Number(e.target.value))}
              style={{
                padding: "7px 10px",
                backgroundColor: "#141414",
                border: "1px solid #2D2D2D",
                borderRadius: "6px",
                fontSize: "12px",
                color: "#EFEFEF",
                outline: "none",
                fontFamily: "Inter, sans-serif",
                width: "100%",
                boxSizing: "border-box",
              }}
            />
            {err && (
              <span style={{ fontSize: "11px", color: "#F05252" }}>{err}</span>
            )}
            <button
              onClick={handleConnect}
              disabled={connecting || !host.trim()}
              style={{
                padding: "7px 0",
                borderRadius: "6px",
                backgroundColor:
                  connecting || !host.trim() ? "#2D2D2D" : "#4A9EFF",
                border: "none",
                color: connecting || !host.trim() ? "#999999" : "white",
                fontSize: "12px",
                fontWeight: 500,
                cursor: connecting || !host.trim() ? "not-allowed" : "pointer",
              }}
            >
              {connecting ? "Connecting…" : "Connect"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ── Inner app ──────────────────────────────────────────────────────────────────

function AppInner() {
  const [page, setPage] = useState<AppPage>("home");
  const [viconOpen, setViconOpen] = useState(false);

  const { data: health } = useHealth();
  const { data: viconConn, refetch: refetchVicon } = useViconConnection();
  const backendConnected = useSystemStore((s) => s.backendConnected);

  const nodeCount = health?.nodes_total ?? 0;
  const onlineCount = health?.nodes_online ?? 0;
  const viconConfigured = health?.vicon_configured ?? false;
  const viconConnected = health?.vicon_connected ?? false;

  useEffect(() => {
    wsManager.start();
    return () => wsManager.stop();
  }, []);

  const viconDotColor = viconConnected
    ? "#3DD68C"
    : viconConfigured
      ? "#F05252"
      : "#555555";

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        width: "100vw",
        backgroundColor: "#0D0D0D",
        color: "#EFEFEF",
        fontFamily: "Inter, sans-serif",
        overflow: "hidden",
      }}
    >
      {/* ── Title Bar ─────────────────────────────────────────────── */}
      <div
        style={
          {
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            height: "32px",
            padding: "0 12px",
            backgroundColor: "#0D0D0D",
            borderBottom: "1px solid #2D2D2D",
            flexShrink: 0,
            WebkitAppRegion: "drag",
          } as DragStyle
        }
      >
        {/* Logo */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
          <svg width="16" height="16" viewBox="0 0 40 40" fill="none">
            <circle cx="20" cy="20" r="12" stroke="#4A9EFF" strokeWidth="2" />
            <circle cx="20" cy="20" r="4" fill="#4A9EFF" />
            <line
              x1="20"
              y1="8"
              x2="20"
              y2="4"
              stroke="#4A9EFF"
              strokeWidth="2"
              strokeLinecap="round"
            />
            <line
              x1="32"
              y1="20"
              x2="36"
              y2="20"
              stroke="#4A9EFF"
              strokeWidth="2"
              strokeLinecap="round"
            />
          </svg>
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              letterSpacing: "2px",
              color: "white",
            }}
          >
            HENOSYNC
          </span>
        </div>

        {/* Status — no-drag so buttons work */}
        <div
          style={
            {
              display: "flex",
              alignItems: "center",
              gap: "16px",
              WebkitAppRegion: "no-drag",
            } as DragStyle
          }
        >
          {/* VICON indicator — always shown when backend connected */}
          {backendConnected && (
            <div style={{ position: "relative" }}>
              <button
                onClick={() => setViconOpen((v) => !v)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  padding: "0",
                }}
              >
                <div
                  style={{
                    width: "6px",
                    height: "6px",
                    borderRadius: "50%",
                    backgroundColor: viconDotColor,
                  }}
                />
                <span style={{ fontSize: "11px", color: "#999999" }}>
                  VICON
                </span>
              </button>

              {viconOpen && (
                <>
                  {/* Backdrop — captures outside clicks */}
                  <div
                    onClick={() => setViconOpen(false)}
                    style={{
                      position: "fixed",
                      inset: 0,
                      zIndex: 199,
                    }}
                  />
                  <VICONPanel
                    conn={viconConn}
                    onChanged={() => {
                      refetchVicon();
                      setViconOpen(false);
                    }}
                  />
                </>
              )}
            </div>
          )}

          {/* Backend connected indicator */}
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: backendConnected ? "#3DD68C" : "#F05252",
              }}
            />
            <span style={{ fontSize: "11px", color: "#999999" }}>
              {backendConnected ? "Connected" : "Connecting..."}
            </span>
          </div>

          {backendConnected && (
            <span style={{ fontSize: "11px", color: "#999999" }}>
              {onlineCount}/{nodeCount} online
            </span>
          )}
        </div>

        {/* Window controls */}
        <div
          style={{ display: "flex", WebkitAppRegion: "no-drag" } as DragStyle}
        >
          <button
            onClick={() => window.henosync?.window.minimize()}
            style={winBtnStyle}
          >
            ─
          </button>
          <button
            onClick={() => window.henosync?.window.maximize()}
            style={winBtnStyle}
          >
            □
          </button>
          <button
            onClick={() => window.henosync?.window.close()}
            style={winBtnStyle}
          >
            ✕
          </button>
        </div>
      </div>

      {/* ── Body: nav + page content ───────────────────────────────── */}
      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        <NavMenu activePage={page} onNavigate={setPage} />
        <div
          style={{
            flex: 1,
            overflow: "hidden",
            display: page === "home" ? "flex" : "none",
          }}
        >
          <HomePage />
        </div>
        <div
          style={{
            flex: 1,
            overflow: "hidden",
            display: page === "zones" ? "flex" : "none",
          }}
        >
          <ZonesPage />
        </div>
        <div
          style={{
            flex: 1,
            overflow: "hidden",
            display: page === "devices" ? "flex" : "none",
          }}
        >
          <DevicesPage />
        </div>
        <div
          style={{
            flex: 1,
            overflow: "hidden",
            display: page === "plugins" ? "flex" : "none",
          }}
        >
          <PluginsPage />
        </div>
        <div
          style={{
            flex: 1,
            overflow: "hidden",
            display: page === "mission" ? "flex" : "none",
          }}
        >
          <MissionPage />
        </div>
      </div>
    </div>
  );
}

// ── Root ───────────────────────────────────────────────────────────────────────

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AppInner />
    </QueryClientProvider>
  );
}

const winBtnStyle: React.CSSProperties = {
  width: "40px",
  height: "32px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  fontSize: "12px",
  color: "#999999",
  backgroundColor: "transparent",
  border: "none",
  cursor: "pointer",
  transition: "background-color 150ms",
};
