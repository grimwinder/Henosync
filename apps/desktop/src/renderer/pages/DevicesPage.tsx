import { useState, useMemo } from "react";
import { Plus, Search, RefreshCw, Trash2, Cpu } from "lucide-react";
import { useNodeStore } from "../stores/nodeStore";
import { useNodes, useRemoveNode, useReconnectNode } from "../hooks/useNodes";
import DeviceIcon from "../components/fleet/DeviceIcon";
import AddNodeModal from "../components/fleet/AddNodeModal";
import type { Node, NodeStatus } from "../types";

// ── Helpers ────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<NodeStatus, string> = {
  online: "#3DD68C",
  connecting: "#F5A623",
  degraded: "#F5A623",
  offline: "#8B95A3",
  error: "#F05252",
};

const STATUS_LABEL: Record<NodeStatus, string> = {
  online: "Online",
  connecting: "Connecting…",
  degraded: "Degraded",
  offline: "Offline",
  error: "Error",
};

function fmtDate(iso: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString();
}

function fmtNum(v: number | null | undefined, unit = "", dp = 1) {
  if (v == null) return "—";
  return `${Number.isInteger(v) ? v : v.toFixed(dp)} ${unit}`.trim();
}

function fmtVal(v: unknown): string {
  if (typeof v === "number")
    return Number.isInteger(v) ? String(v) : v.toFixed(3);
  if (typeof v === "boolean") return v ? "true" : "false";
  return String(v);
}

// ── Shared sub-components ──────────────────────────────────────────────────────

function StatusDot({ status }: { status: NodeStatus }) {
  return (
    <div
      style={{
        width: "7px",
        height: "7px",
        borderRadius: "50%",
        backgroundColor: STATUS_COLOR[status],
        flexShrink: 0,
      }}
    />
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
    <div style={{ marginBottom: "24px" }}>
      <div
        style={{
          fontSize: "10px",
          fontWeight: 600,
          letterSpacing: "1px",
          color: "#8B95A3",
          textTransform: "uppercase",
          marginBottom: "8px",
        }}
      >
        {title}
      </div>
      {children}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: React.ReactNode }) {
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

// ── Left sidebar row ───────────────────────────────────────────────────────────

function DeviceRow({ node }: { node: Node }) {
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const setSelectedNode = useNodeStore((s) => s.setSelectedNode);
  const selected = selectedNodeId === node.id;

  return (
    <button
      onClick={() => setSelectedNode(selected ? null : node.id)}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "10px 14px",
        backgroundColor: selected ? "#1C1F24" : "transparent",
        border: "none",
        borderBottom: "1px solid #2A2F38",
        cursor: "pointer",
        display: "flex",
        alignItems: "center",
        gap: "10px",
        transition: "background-color 150ms",
      }}
      onMouseEnter={(e) => {
        if (!selected)
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "#1C1F24";
      }}
      onMouseLeave={(e) => {
        if (!selected)
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "transparent";
      }}
    >
      <StatusDot status={node.status} />
      <DeviceIcon
        category={node.specs?.category}
        size={20}
        color={selected ? "#4A9EFF" : "#8B95A3"}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 500,
            color: "#E8EAED",
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
            color: STATUS_COLOR[node.status],
            marginTop: "2px",
          }}
        >
          {STATUS_LABEL[node.status]}
        </div>
      </div>
    </button>
  );
}

// ── Device config panel (main area) ───────────────────────────────────────────

function DeviceConfigPanel({ node }: { node: Node }) {
  const [confirmDelete, setConfirmDelete] = useState(false);
  const setSelectedNode = useNodeStore((s) => s.setSelectedNode);
  const { mutate: removeNode, isPending: isRemoving } = useRemoveNode();
  const { mutate: reconnect, isPending: isReconnecting } = useReconnectNode();

  const canReconnect =
    node.status === "offline" ||
    node.status === "error" ||
    node.status === "degraded";

  const configEntries = Object.entries(node.config ?? {});
  const telemetryEntries = Object.entries(node.telemetry ?? {}).filter(
    ([, v]) => v != null,
  );

  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* ── Hero ──────────────────────────────────────────────────────────── */}
      <div
        style={{
          padding: "24px 32px 20px",
          borderBottom: "1px solid #2A2F38",
          backgroundColor: "#0D0F12",
          display: "flex",
          alignItems: "center",
          gap: "20px",
          flexShrink: 0,
        }}
      >
        <DeviceIcon category={node.specs?.category} size={56} color="#4A9EFF" />
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontSize: "18px",
              fontWeight: 600,
              color: "#E8EAED",
              marginBottom: "8px",
            }}
          >
            {node.name}
          </div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: "8px",
              flexWrap: "wrap",
            }}
          >
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

            {/* Reconnect button */}
            {canReconnect && (
              <button
                onClick={() => reconnect(node.id)}
                disabled={isReconnecting}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "5px",
                  padding: "3px 10px",
                  borderRadius: "12px",
                  backgroundColor: "transparent",
                  border: "1px solid #4A9EFF40",
                  color: isReconnecting ? "#8B95A3" : "#4A9EFF",
                  fontSize: "11px",
                  fontWeight: 500,
                  cursor: isReconnecting ? "not-allowed" : "pointer",
                  transition: "background-color 150ms",
                }}
                onMouseEnter={(e) => {
                  if (!isReconnecting)
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "#4A9EFF18";
                }}
                onMouseLeave={(e) => {
                  if (!isReconnecting)
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "transparent";
                }}
              >
                <RefreshCw
                  size={11}
                  style={
                    isReconnecting
                      ? { animation: "spin 1s linear infinite" }
                      : {}
                  }
                />
                {isReconnecting ? "Reconnecting…" : "Reconnect"}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Scrollable body ───────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px 40px" }}>
        {/* Identity */}
        <Section title="Identity">
          <InfoRow label="Device ID" value={node.id} />
          <InfoRow label="Plugin" value={node.plugin_id} />
          <InfoRow label="Category" value={node.specs?.category ?? "—"} />
          <InfoRow label="Last Seen" value={fmtDate(node.last_seen)} />
        </Section>

        {/* Connection Config */}
        <Section title="Connection Config">
          {configEntries.length === 0 ? (
            <p
              style={{
                fontSize: "11px",
                color: "#8B95A3",
                fontStyle: "italic",
                margin: 0,
                paddingBottom: "4px",
              }}
            >
              No configuration parameters for this plugin.
            </p>
          ) : (
            configEntries.map(([key, val]) => (
              <InfoRow key={key} label={key} value={fmtVal(val)} />
            ))
          )}
        </Section>

        {/* Specifications */}
        {node.specs && (
          <Section title="Specifications">
            {node.specs.max_speed_ms != null && (
              <InfoRow
                label="Max Speed"
                value={fmtNum(node.specs.max_speed_ms, "m/s")}
              />
            )}
            {node.specs.max_range_m != null && (
              <InfoRow
                label="Max Range"
                value={fmtNum(node.specs.max_range_m, "m", 0)}
              />
            )}
            {node.specs.max_altitude_m != null && (
              <InfoRow
                label="Max Altitude"
                value={fmtNum(node.specs.max_altitude_m, "m", 0)}
              />
            )}
            {node.specs.min_altitude_m != null && (
              <InfoRow
                label="Min Altitude"
                value={fmtNum(node.specs.min_altitude_m, "m", 0)}
              />
            )}
            {node.specs.weight_kg != null && (
              <InfoRow
                label="Weight"
                value={fmtNum(node.specs.weight_kg, "kg")}
              />
            )}
            {node.specs.length_m != null && (
              <InfoRow
                label="Length"
                value={fmtNum(node.specs.length_m, "m")}
              />
            )}
            {node.specs.width_m != null && (
              <InfoRow label="Width" value={fmtNum(node.specs.width_m, "m")} />
            )}
            {node.specs.height_m != null && (
              <InfoRow
                label="Height"
                value={fmtNum(node.specs.height_m, "m")}
              />
            )}
            {node.specs.battery_capacity_wh != null && (
              <InfoRow
                label="Battery Capacity"
                value={fmtNum(node.specs.battery_capacity_wh, "Wh", 0)}
              />
            )}
            {node.specs.endurance_minutes != null && (
              <InfoRow
                label="Endurance"
                value={fmtNum(node.specs.endurance_minutes, "min", 0)}
              />
            )}
            <InfoRow
              label="Has GPS"
              value={node.specs.has_gps ? "Yes" : "No"}
            />
            <InfoRow
              label="Coordinate Frame"
              value={node.specs.coordinate_frame || "—"}
            />
          </Section>
        )}

        {/* Capabilities */}
        {node.capabilities.length > 0 && (
          <Section title="Capabilities">
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {node.capabilities.map((cap) => (
                <div
                  key={cap.id}
                  title={
                    cap.destructive
                      ? `${cap.label} — destructive operation`
                      : cap.label
                  }
                  style={{
                    padding: "3px 8px",
                    borderRadius: "4px",
                    backgroundColor: cap.destructive
                      ? "#F0525218"
                      : "#4A9EFF14",
                    border: `1px solid ${cap.destructive ? "#F0525240" : "#4A9EFF30"}`,
                    fontSize: "10px",
                    fontWeight: 500,
                    color: cap.destructive ? "#F05252" : "#4A9EFF",
                    fontFamily: "JetBrains Mono, monospace",
                    cursor: "default",
                  }}
                >
                  {cap.label}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Live Status */}
        <Section title="Live Status">
          <InfoRow
            label="Battery"
            value={
              node.battery_percent != null
                ? `${Math.round(node.battery_percent)}%`
                : "—"
            }
          />
          <InfoRow
            label="Signal"
            value={
              node.signal_strength != null
                ? `${Math.round(node.signal_strength)}%`
                : "—"
            }
          />
          <InfoRow
            label="Latitude"
            value={node.position.lat !== 0 ? node.position.lat.toFixed(6) : "—"}
          />
          <InfoRow
            label="Longitude"
            value={node.position.lon !== 0 ? node.position.lon.toFixed(6) : "—"}
          />
          <InfoRow
            label="Altitude"
            value={
              node.position.alt !== 0
                ? `${node.position.alt.toFixed(1)} m`
                : "—"
            }
          />
          {node.position.heading != null && (
            <InfoRow
              label="Heading"
              value={`${node.position.heading.toFixed(1)}°`}
            />
          )}
        </Section>

        {/* Telemetry */}
        {telemetryEntries.length > 0 && (
          <Section title="Telemetry">
            {telemetryEntries.map(([key, val]) => (
              <InfoRow key={key} label={key} value={fmtVal(val)} />
            ))}
          </Section>
        )}

        {/* Danger zone */}
        <div
          style={{
            paddingTop: "20px",
            borderTop: "1px solid #2A2F38",
          }}
        >
          <div
            style={{
              fontSize: "10px",
              fontWeight: 600,
              letterSpacing: "1px",
              color: "#8B95A3",
              textTransform: "uppercase",
              marginBottom: "12px",
            }}
          >
            Danger Zone
          </div>
          {confirmDelete ? (
            <div>
              <p
                style={{
                  fontSize: "12px",
                  color: "#E8EAED",
                  marginBottom: "14px",
                  lineHeight: "1.6",
                }}
              >
                Remove <strong>{node.name}</strong> from Henosync? This action
                cannot be undone.
              </p>
              <div style={{ display: "flex", gap: "8px" }}>
                <button
                  onClick={() => setConfirmDelete(false)}
                  style={{
                    flex: 1,
                    padding: "8px 0",
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
                  onClick={() =>
                    removeNode(node.id, {
                      onSuccess: () => setSelectedNode(null),
                    })
                  }
                  style={{
                    flex: 1,
                    padding: "8px 0",
                    borderRadius: "6px",
                    backgroundColor: isRemoving ? "#2A2F38" : "#F05252",
                    border: "none",
                    color: isRemoving ? "#8B95A3" : "white",
                    fontSize: "12px",
                    fontWeight: 500,
                    cursor: isRemoving ? "not-allowed" : "pointer",
                  }}
                >
                  {isRemoving ? "Removing…" : "Remove Device"}
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setConfirmDelete(true)}
              style={{
                padding: "8px 16px",
                borderRadius: "6px",
                background: "none",
                border: "1px solid #F0525240",
                color: "#F05252",
                fontSize: "12px",
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
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
              Remove Device
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ── DevicesPage ────────────────────────────────────────────────────────────────

type FilterTab = "all" | "online" | "offline";

export default function DevicesPage() {
  const [showAddModal, setShowAddModal] = useState(false);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<FilterTab>("all");

  useNodes(); // keep store fresh

  const nodes = useNodeStore((s) => Object.values(s.nodes));
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const selectedNode = useNodeStore((s) =>
    selectedNodeId ? (s.nodes[selectedNodeId] ?? null) : null,
  );

  const online = nodes.filter((n) => n.status === "online").length;

  const filtered = useMemo(() => {
    let list = nodes;
    if (filter === "online") list = list.filter((n) => n.status === "online");
    if (filter === "offline")
      list = list.filter(
        (n) => n.status !== "online" && n.status !== "connecting",
      );
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (n) =>
          n.name.toLowerCase().includes(q) ||
          n.plugin_id.toLowerCase().includes(q),
      );
    }
    return list;
  }, [nodes, filter, search]);

  return (
    <div
      style={{
        display: "flex",
        flex: 1,
        overflow: "hidden",
        backgroundColor: "#0D0F12",
      }}
    >
      {/* ── Left sidebar ────────────────────────────────────────────────── */}
      <div
        style={{
          width: "260px",
          flexShrink: 0,
          backgroundColor: "#141619",
          borderRight: "1px solid #2A2F38",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            height: "36px",
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "0 8px 0 14px",
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
            Devices
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "11px", color: "#8B95A3" }}>
              {online}/{nodes.length}
            </span>
            <button
              title="Add device"
              onClick={() => setShowAddModal(true)}
              style={{
                width: "22px",
                height: "22px",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                borderRadius: "4px",
                border: "none",
                backgroundColor: "transparent",
                color: "#8B95A3",
                cursor: "pointer",
                transition: "background-color 150ms, color 150ms",
              }}
              onMouseEnter={(e) => {
                const b = e.currentTarget as HTMLButtonElement;
                b.style.backgroundColor = "#252A31";
                b.style.color = "#4A9EFF";
              }}
              onMouseLeave={(e) => {
                const b = e.currentTarget as HTMLButtonElement;
                b.style.backgroundColor = "transparent";
                b.style.color = "#8B95A3";
              }}
            >
              <Plus size={13} />
            </button>
          </div>
        </div>

        {/* Search */}
        <div
          style={{
            padding: "8px 10px",
            borderBottom: "1px solid #2A2F38",
            flexShrink: 0,
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          <Search size={12} color="#8B95A3" style={{ flexShrink: 0 }} />
          <input
            type="text"
            placeholder="Search devices…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              flex: 1,
              background: "none",
              border: "none",
              outline: "none",
              fontSize: "12px",
              color: "#E8EAED",
              fontFamily: "Inter, sans-serif",
            }}
          />
        </div>

        {/* Filter tabs */}
        <div
          style={{
            display: "flex",
            flexShrink: 0,
            borderBottom: "1px solid #2A2F38",
          }}
        >
          {(["all", "online", "offline"] as FilterTab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setFilter(tab)}
              style={{
                flex: 1,
                padding: "6px 0",
                border: "none",
                background: "none",
                fontSize: "10px",
                fontWeight: 500,
                letterSpacing: "0.5px",
                color: filter === tab ? "#4A9EFF" : "#8B95A3",
                borderBottom: `2px solid ${filter === tab ? "#4A9EFF" : "transparent"}`,
                cursor: "pointer",
                transition: "color 150ms",
              }}
            >
              {tab.charAt(0).toUpperCase() + tab.slice(1)}
            </button>
          ))}
        </div>

        {/* Device list */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {filtered.length === 0 ? (
            <div
              style={{
                padding: "24px 14px",
                textAlign: "center",
                color: "#8B95A3",
                fontSize: "11px",
                lineHeight: "1.6",
              }}
            >
              {nodes.length === 0 ? (
                <>
                  No devices added.
                  <br />
                  Click <strong style={{ color: "#4A9EFF" }}>+</strong> to add
                  one.
                </>
              ) : (
                "No devices match the filter."
              )}
            </div>
          ) : (
            filtered.map((node) => <DeviceRow key={node.id} node={node} />)
          )}
        </div>
      </div>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>
        {selectedNode ? (
          <DeviceConfigPanel node={selectedNode} />
        ) : (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "12px",
            }}
          >
            <Cpu size={40} color="#2A2F38" />
            <span style={{ fontSize: "13px", color: "#8B95A3" }}>
              Select a device to view its configuration
            </span>
            {nodes.length === 0 && (
              <button
                onClick={() => setShowAddModal(true)}
                style={{
                  marginTop: "8px",
                  display: "flex",
                  alignItems: "center",
                  gap: "6px",
                  padding: "8px 16px",
                  borderRadius: "6px",
                  backgroundColor: "#4A9EFF",
                  border: "none",
                  color: "white",
                  fontSize: "12px",
                  fontWeight: 500,
                  cursor: "pointer",
                }}
              >
                <Plus size={13} />
                Add Device
              </button>
            )}
          </div>
        )}
      </div>

      {showAddModal && <AddNodeModal onClose={() => setShowAddModal(false)} />}

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to   { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
