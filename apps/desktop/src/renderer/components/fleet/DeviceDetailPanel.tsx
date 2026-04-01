import { X, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNodeStore } from "../../stores/nodeStore";
import { useRemoveNode } from "../../hooks/useNodes";
import DeviceIcon from "./DeviceIcon";
import type { Node, NodeStatus } from "../../types";

// ── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<NodeStatus, string> = {
  online: "Online",
  connecting: "Connecting",
  degraded: "Degraded",
  offline: "Offline",
  error: "Error",
};

const STATUS_COLOR: Record<NodeStatus, string> = {
  online: "#3DD68C",
  connecting: "#F5A623",
  degraded: "#F5A623",
  offline: "#8B95A3",
  error: "#F05252",
};

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "baseline",
        gap: "8px",
        padding: "5px 0",
        borderBottom: "1px solid #252A31",
      }}
    >
      <span style={{ fontSize: "11px", color: "#8B95A3", flexShrink: 0 }}>
        {label}
      </span>
      <span
        style={{
          fontSize: "11px",
          color: "#E8EAED",
          fontFamily: "JetBrains Mono, monospace",
          textAlign: "right",
          wordBreak: "break-all",
        }}
      >
        {value}
      </span>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: "16px" }}>
      <div
        style={{
          fontSize: "10px",
          fontWeight: 600,
          letterSpacing: "1px",
          color: "#8B95A3",
          textTransform: "uppercase",
          marginBottom: "6px",
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

// ── Panel ──────────────────────────────────────────────────────────────────────

interface DeviceDetailPanelProps {
  node: Node;
  readOnly?: boolean;
}

export default function DeviceDetailPanel({
  node,
  readOnly = false,
}: DeviceDetailPanelProps) {
  const setSelectedNode = useNodeStore((s) => s.setSelectedNode);
  const { mutate: removeNode, isPending: isRemoving } = useRemoveNode();
  const [confirmDelete, setConfirmDelete] = useState(false);
  const category = node.specs?.category;

  const t = node.telemetry as Record<string, unknown>;
  const telemetryEntries = Object.entries(t).filter(
    ([, v]) => v !== null && v !== undefined,
  );

  // Format a telemetry value for display
  function fmt(v: unknown): string {
    if (typeof v === "number")
      return Number.isInteger(v) ? String(v) : v.toFixed(3);
    if (typeof v === "boolean") return v ? "true" : "false";
    return String(v);
  }

  function fmtDate(iso: string | null) {
    if (!iso) return "—";
    const d = new Date(iso);
    return d.toLocaleTimeString();
  }

  return (
    <div
      style={{
        width: "260px",
        height: "100%",
        backgroundColor: "#141619",
        borderLeft: "1px solid #2A2F38",
        display: "flex",
        flexDirection: "column",
        flexShrink: 0,
        animation: "slideDown 180ms ease",
      }}
    >
      {/* Keyframes injected once */}
      <style>{`
        @keyframes slideDown {
          from { opacity: 0; transform: translateY(-12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      {/* ── Header ──────────────────────────────────────────────── */}
      <div
        style={{
          height: "36px",
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 8px 0 12px",
          borderBottom: "1px solid #2A2F38",
        }}
      >
        <span
          style={{
            fontSize: "11px",
            fontWeight: 600,
            letterSpacing: "1px",
            color: "#8B95A3",
            textTransform: "uppercase",
          }}
        >
          Device Info
        </span>
        <button
          onClick={() => setSelectedNode(null)}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            color: "#8B95A3",
            display: "flex",
            padding: "4px",
            borderRadius: "4px",
          }}
          onMouseEnter={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = "#E8EAED";
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.color = "#8B95A3";
          }}
        >
          <X size={13} />
        </button>
      </div>

      {/* ── Scrollable body ─────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0", minHeight: 0 }}>
        {/* ── Hero image ────────────────────────────────────────── */}
        <div
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            padding: "24px 16px 20px",
            backgroundColor: "#0D0F12",
            borderBottom: "1px solid #2A2F38",
            gap: "12px",
          }}
        >
          <DeviceIcon category={category} size={80} color="#4A9EFF" />

          {/* Name */}
          <span
            style={{
              fontSize: "14px",
              fontWeight: 600,
              color: "#E8EAED",
              textAlign: "center",
            }}
          >
            {node.name}
          </span>

          {/* Status badge */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "3px 10px",
              borderRadius: "12px",
              backgroundColor: `${STATUS_COLOR[node.status]}18`,
              border: `1px solid ${STATUS_COLOR[node.status]}40`,
            }}
          >
            <div
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: STATUS_COLOR[node.status],
              }}
            />
            <span
              style={{
                fontSize: "11px",
                color: STATUS_COLOR[node.status],
                fontWeight: 500,
              }}
            >
              {STATUS_LABEL[node.status]}
            </span>
          </div>
        </div>

        {/* ── Info sections ────────────────────────────────────── */}
        <div style={{ padding: "14px 14px 24px" }}>
          <Section title="Identity">
            <Row label="Plugin" value={node.plugin_id} />
            <Row label="Category" value={category ?? "—"} />
            <Row label="Last Seen" value={fmtDate(node.last_seen)} />
          </Section>

          <Section title="Position">
            <Row
              label="Latitude"
              value={
                node.position.lat !== 0 ? node.position.lat.toFixed(6) : "—"
              }
            />
            <Row
              label="Longitude"
              value={
                node.position.lon !== 0 ? node.position.lon.toFixed(6) : "—"
              }
            />
            <Row
              label="Altitude"
              value={
                node.position.alt !== 0
                  ? `${node.position.alt.toFixed(1)} m`
                  : "—"
              }
            />
            {node.position.heading != null && (
              <Row
                label="Heading"
                value={`${node.position.heading.toFixed(1)}°`}
              />
            )}
          </Section>

          {node.specs && (
            <Section title="Specs">
              {node.specs.max_speed_ms != null && (
                <Row
                  label="Max Speed"
                  value={`${node.specs.max_speed_ms} m/s`}
                />
              )}
              {node.specs.weight_kg != null && (
                <Row label="Weight" value={`${node.specs.weight_kg} kg`} />
              )}
              {node.specs.endurance_minutes != null && (
                <Row
                  label="Endurance"
                  value={`${node.specs.endurance_minutes} min`}
                />
              )}
              {node.specs.capabilities.length > 0 && (
                <Row
                  label="Capabilities"
                  value={node.specs.capabilities
                    .map((c) => c.capability)
                    .join(", ")}
                />
              )}
            </Section>
          )}

          {telemetryEntries.length > 0 && (
            <Section title="Telemetry">
              {telemetryEntries.map(([key, val]) => (
                <Row key={key} label={key} value={fmt(val)} />
              ))}
            </Section>
          )}
        </div>
      </div>

      {/* ── Delete footer ───────────────────────────────────────── */}
      {!readOnly && (
        <div
          style={{
            flexShrink: 0,
            padding: "12px 14px",
            borderTop: "1px solid #2A2F38",
          }}
        >
          {confirmDelete ? (
            <div style={{ display: "flex", gap: "8px" }}>
              <button
                onClick={() => setConfirmDelete(false)}
                style={{
                  flex: 1,
                  padding: "7px 0",
                  borderRadius: "6px",
                  background: "none",
                  border: "1px solid #2A2F38",
                  color: "#8B95A3",
                  fontSize: "12px",
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>
              <button
                disabled={isRemoving}
                onClick={() => removeNode(node.id)}
                style={{
                  flex: 1,
                  padding: "7px 0",
                  borderRadius: "6px",
                  backgroundColor: isRemoving ? "#2A2F38" : "#F05252",
                  border: "none",
                  color: isRemoving ? "#8B95A3" : "white",
                  fontSize: "12px",
                  fontWeight: 500,
                  cursor: isRemoving ? "not-allowed" : "pointer",
                }}
              >
                {isRemoving ? "Deleting…" : "Confirm"}
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              style={{
                width: "100%",
                padding: "7px 0",
                borderRadius: "6px",
                background: "none",
                border: "1px solid #F0525240",
                color: "#F05252",
                fontSize: "12px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "6px",
                transition: "background-color 150ms",
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#F0525218";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "transparent";
              }}
            >
              <Trash2 size={13} />
              Delete Device
            </button>
          )}
        </div>
      )}
    </div>
  );
}
