import { useEffect, useState } from "react";

type DragStyle = React.CSSProperties & { WebkitAppRegion: string };

export default function App() {
  const [backendUrl, setBackendUrl] = useState<string>("");
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const url = "http://127.0.0.1:8765";
    setBackendUrl(url);
    fetch(`${url}/health`)
      .then((r) => r.json())
      .then((data) => {
        if (data.status === "ok") setConnected(true);
      })
      .catch(() => setConnected(false));
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
      }}
    >
      {/* Title Bar */}
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
        {/* Left — Logo */}
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

        {/* Centre — Status */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <div
            style={{
              width: "6px",
              height: "6px",
              borderRadius: "50%",
              backgroundColor: connected ? "#3DD68C" : "#F05252",
            }}
          />
          <span style={{ fontSize: "11px", color: "#8B95A3" }}>
            {connected ? "Backend Connected" : "Connecting..."}
          </span>
        </div>

        {/* Right — Window Controls */}
        <div
          style={
            {
              display: "flex",
              WebkitAppRegion: "no-drag",
            } as DragStyle
          }
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

      {/* Main Content */}
      <div
        style={{
          display: "flex",
          flex: 1,
          alignItems: "center",
          justifyContent: "center",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <svg width="48" height="48" viewBox="0 0 40 40" fill="none">
          <circle
            cx="20"
            cy="20"
            r="18"
            stroke="#4A9EFF"
            strokeWidth="1"
            strokeDasharray="4 2"
            opacity="0.3"
          />
          <circle cx="20" cy="20" r="12" stroke="#4A9EFF" strokeWidth="1.5" />
          <circle cx="20" cy="20" r="4" fill="#4A9EFF" />
          <line
            x1="20"
            y1="8"
            x2="20"
            y2="4"
            stroke="#4A9EFF"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <line
            x1="20"
            y1="32"
            x2="20"
            y2="36"
            stroke="#4A9EFF"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <line
            x1="8"
            y1="20"
            x2="4"
            y2="20"
            stroke="#4A9EFF"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
          <line
            x1="32"
            y1="20"
            x2="36"
            y2="20"
            stroke="#4A9EFF"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>

        <div style={{ textAlign: "center" }}>
          <p
            style={{
              fontSize: "13px",
              fontWeight: 600,
              letterSpacing: "2px",
              color: "white",
              marginBottom: "4px",
            }}
          >
            HENOSYNC
          </p>
          <p style={{ fontSize: "12px", color: "#8B95A3" }}>
            {connected
              ? "Backend running — GUI coming in Phase 5"
              : "Waiting for backend..."}
          </p>
        </div>

        {connected && (
          <div
            style={{
              marginTop: "16px",
              padding: "8px 16px",
              backgroundColor: "#1C1F24",
              borderRadius: "6px",
              border: "1px solid #2A2F38",
              fontSize: "11px",
              color: "#8B95A3",
              fontFamily: "monospace",
            }}
          >
            {backendUrl}/health ✓
          </div>
        )}
      </div>
    </div>
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
