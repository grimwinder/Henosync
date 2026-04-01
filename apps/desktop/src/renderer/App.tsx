import { useEffect, useState } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./lib/queryClient";
import { wsManager } from "./lib/websocket";
import { useHealth } from "./hooks/useSystem";
import { useSystemStore } from "./stores/systemStore";
import NavMenu from "./components/nav/NavMenu";
import HomePage from "./pages/HomePage";
import ZonesPage from "./pages/ZonesPage";
import type { AppPage } from "./types/ui";

type DragStyle = React.CSSProperties & { WebkitAppRegion: string };

// ── Inner app ──────────────────────────────────────────────────────────────────

function AppInner() {
  const [page, setPage] = useState<AppPage>("home");
  const { data: health } = useHealth();
  const backendConnected = useSystemStore((s) => s.backendConnected);
  const nodeCount = health?.nodes_total ?? 0;
  const onlineCount = health?.nodes_online ?? 0;

  useEffect(() => {
    wsManager.start();
    return () => wsManager.stop();
  }, []);

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100vh",
        width: "100vw",
        backgroundColor: "#0D0F12",
        color: "#E8EAED",
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
            backgroundColor: "#141619",
            borderBottom: "1px solid #2A2F38",
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

        {/* Status */}
        <div style={{ display: "flex", alignItems: "center", gap: "16px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: backendConnected ? "#3DD68C" : "#F05252",
              }}
            />
            <span style={{ fontSize: "11px", color: "#8B95A3" }}>
              {backendConnected ? "Connected" : "Connecting..."}
            </span>
          </div>
          {backendConnected && (
            <span style={{ fontSize: "11px", color: "#8B95A3" }}>
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
            style={winBtnStyle(false)}
          >
            ─
          </button>
          <button
            onClick={() => window.henosync?.window.maximize()}
            style={winBtnStyle(false)}
          >
            □
          </button>
          <button
            onClick={() => window.henosync?.window.close()}
            style={winBtnStyle(true)}
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

function winBtnStyle(danger: boolean): React.CSSProperties {
  return {
    width: "40px",
    height: "32px",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: "12px",
    color: "#8B95A3",
    backgroundColor: "transparent",
    border: "none",
    cursor: "pointer",
    transition: "background-color 150ms",
  };
}
