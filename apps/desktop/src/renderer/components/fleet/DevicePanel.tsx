import { useState } from "react";
import { Plus } from "lucide-react";
import { useNodeStore } from "../../stores/nodeStore";
import { useNodes } from "../../hooks/useNodes";
import AddNodeModal from "./AddNodeModal";
import type { Node, NodeStatus } from "../../types";

// ── Status dot ─────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<NodeStatus, string> = {
  online: "#3DD68C",
  connecting: "#F5A623",
  degraded: "#F5A623",
  offline: "#8B95A3",
  error: "#F05252",
};

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

// ── Battery bar ────────────────────────────────────────────────────────────────

function BatteryBar({ percent }: { percent: number | null }) {
  if (percent === null) return null;
  const color = percent > 50 ? "#3DD68C" : percent > 20 ? "#F5A623" : "#F05252";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "5px" }}>
      <div
        style={{
          width: "36px",
          height: "4px",
          borderRadius: "2px",
          backgroundColor: "#252A31",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${Math.max(0, Math.min(100, percent))}%`,
            height: "100%",
            backgroundColor: color,
            borderRadius: "2px",
            transition: "width 500ms ease",
          }}
        />
      </div>
      <span
        style={{
          fontSize: "10px",
          color: "#8B95A3",
          fontFamily: "JetBrains Mono, monospace",
          minWidth: "28px",
        }}
      >
        {Math.round(percent)}%
      </span>
    </div>
  );
}

// ── Device card ────────────────────────────────────────────────────────────────

function DeviceCard({ node }: { node: Node }) {
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const setSelectedNode = useNodeStore((s) => s.setSelectedNode);
  const selected = selectedNodeId === node.id;

  return (
    <button
      onClick={() => setSelectedNode(selected ? null : node.id)}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "10px 12px",
        backgroundColor: selected ? "#1C1F24" : "transparent",
        border: "none",
        borderBottom: "1px solid #2A2F38",
        cursor: "pointer",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
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
      {/* Name + status */}
      <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
        <StatusDot status={node.status} />
        <span
          style={{
            fontSize: "12px",
            fontWeight: 500,
            color: "#E8EAED",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            flex: 1,
          }}
        >
          {node.name}
        </span>
      </div>

      {/* Plugin + battery */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          paddingLeft: "15px",
        }}
      >
        <span style={{ fontSize: "10px", color: "#8B95A3" }}>
          {node.plugin_id}
        </span>
        <BatteryBar percent={node.battery_percent} />
      </div>
    </button>
  );
}

// ── Panel ──────────────────────────────────────────────────────────────────────

interface DevicePanelProps {
  readOnly?: boolean;
}

export default function DevicePanel({ readOnly = false }: DevicePanelProps) {
  const [showAddModal, setShowAddModal] = useState(false);

  // Keep the list fresh from the API
  useNodes();

  const nodes = useNodeStore((s) => Object.values(s.nodes));
  const online = nodes.filter((n) => n.status === "online").length;

  return (
    <>
      <div
        style={{
          width: "220px",
          height: "100%",
          backgroundColor: "#141619",
          borderRight: "1px solid #2A2F38",
          borderBottom: "1px solid #2A2F38",
          borderBottomRightRadius: "8px",
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: "0 8px 0 12px",
            height: "36px",
            borderBottom: "1px solid #2A2F38",
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
              color: "#8B95A3",
              textTransform: "uppercase",
            }}
          >
            Fleet
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "11px", color: "#8B95A3" }}>
              {online}/{nodes.length}
            </span>
            {!readOnly && (
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
            )}
          </div>
        </div>

        {/* Device list */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {nodes.length === 0 ? (
            <div
              style={{
                padding: "24px 12px",
                textAlign: "center",
                color: "#8B95A3",
                fontSize: "11px",
                lineHeight: "1.6",
              }}
            >
              No devices added.
              <br />
              Click <strong style={{ color: "#4A9EFF" }}>+</strong> to add one.
            </div>
          ) : (
            nodes.map((node) => <DeviceCard key={node.id} node={node} />)
          )}
        </div>
      </div>

      {showAddModal && <AddNodeModal onClose={() => setShowAddModal(false)} />}
    </>
  );
}
