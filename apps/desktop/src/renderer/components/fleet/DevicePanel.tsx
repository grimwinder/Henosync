import { useState } from "react";
import {
  Plus,
  MapPin,
  Camera,
  ScanLine,
  Waves,
  Thermometer,
  Activity,
  Navigation,
  Volume2,
  Lightbulb,
  Package,
  Wrench,
  Battery,
  Zap,
} from "lucide-react";
import { useNodeStore } from "../../stores/nodeStore";
import { useNodes } from "../../hooks/useNodes";
import AddNodeModal from "./AddNodeModal";
import DeviceIcon from "./DeviceIcon";
import type {
  Node,
  NodeStatus,
  DeviceCategory,
  DeviceCapability,
} from "../../types";

// ── Lookups ─────────────────────────────────────────────────────────────────────

const STATUS_COLOR: Record<NodeStatus, string> = {
  online: "#3DD68C",
  connecting: "#F5A623",
  degraded: "#F5A623",
  offline: "#999999",
  error: "#F05252",
};

const STATUS_BADGE: Record<NodeStatus, string> = {
  online: "ON",
  connecting: "…",
  degraded: "DG",
  offline: "—",
  error: "ER",
};

const CATEGORY_LABEL: Record<DeviceCategory, string> = {
  drone: "Quadcopter",
  plane: "Fixed-Wing UAV",
  agv: "Ground Vehicle",
  boat: "Surface Vessel",
  rov: "Underwater ROV",
  arm: "Robotic Arm",
  unknown: "Unknown",
};

const CAPABILITY_ICON: Record<DeviceCapability, React.ReactNode> = {
  camera: <Camera size={12} />,
  gps: <MapPin size={12} />,
  lidar: <ScanLine size={12} />,
  sonar: <Waves size={12} />,
  thermal: <Thermometer size={12} />,
  imu: <Activity size={12} />,
  move_2d: <Navigation size={12} />,
  move_3d: <Navigation size={12} />,
  horn: <Volume2 size={12} />,
  lights: <Lightbulb size={12} />,
  payload: <Package size={12} />,
  arm_tool: <Wrench size={12} />,
  battery: <Battery size={12} />,
  charging: <Zap size={12} />,
};

const CAPABILITY_LABEL: Record<DeviceCapability, string> = {
  camera: "Camera",
  gps: "GPS",
  lidar: "LiDAR",
  sonar: "Sonar",
  thermal: "Thermal",
  imu: "IMU",
  move_2d: "2D Motion",
  move_3d: "3D Motion",
  horn: "Horn",
  lights: "Lights",
  payload: "Payload",
  arm_tool: "Arm Tool",
  battery: "Battery",
  charging: "Charging",
};

// ── Capability badge ─────────────────────────────────────────────────────────────

function CapabilityBadge({
  cap,
  color,
}: {
  cap: DeviceCapability;
  color: string;
}) {
  return (
    <div
      title={CAPABILITY_LABEL[cap]}
      style={{
        width: "22px",
        height: "22px",
        borderRadius: "5px",
        backgroundColor: `${color}18`,
        border: `1px solid ${color}40`,
        color: color,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      {CAPABILITY_ICON[cap]}
    </div>
  );
}

// ── Device card ────────────────────────────────────────────────────────────────

function DeviceCard({ node }: { node: Node }) {
  const selectedNodeId = useNodeStore((s) => s.selectedNodeId);
  const setSelectedNode = useNodeStore((s) => s.setSelectedNode);
  const selected = selectedNodeId === node.id;

  const category = node.specs?.category ?? "unknown";
  const capabilities = node.specs?.capabilities ?? [];
  const statusColor = STATUS_COLOR[node.status];
  const shortId = node.id.slice(0, 6).toUpperCase();

  return (
    <button
      onClick={() => setSelectedNode(selected ? null : node.id)}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "10px 12px",
        backgroundColor: selected ? "#1C1C1C" : "transparent",
        border: "none",
        borderBottom: "1px solid #2D2D2D",
        cursor: "pointer",
        display: "flex",
        flexDirection: "row",
        alignItems: "center",
        gap: "10px",
        transition: "background-color 150ms",
      }}
      onMouseEnter={(e) => {
        if (!selected)
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "#1C1C1C";
      }}
      onMouseLeave={(e) => {
        if (!selected)
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "transparent";
      }}
    >
      {/* Device type icon */}
      <div style={{ flexShrink: 0 }}>
        <DeviceIcon category={category} size={36} color="#EFEFEF" />
      </div>

      {/* Right content */}
      <div
        style={{
          flex: 1,
          minWidth: 0,
          display: "flex",
          flexDirection: "column",
          gap: "3px",
        }}
      >
        {/* Name + status badge */}
        <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
          <span
            style={{
              fontSize: "12px",
              fontWeight: 600,
              color: "#EFEFEF",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              flex: 1,
            }}
          >
            {node.name}
          </span>
          <div
            style={{
              minWidth: "22px",
              height: "18px",
              paddingInline: "4px",
              borderRadius: "4px",
              backgroundColor: `${statusColor}22`,
              border: `1px solid ${statusColor}55`,
              color: statusColor,
              fontSize: "9px",
              fontWeight: 700,
              fontFamily: "Inter, sans-serif",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexShrink: 0,
              letterSpacing: "0.5px",
            }}
          >
            {STATUS_BADGE[node.status]}
          </div>
        </div>

        {/* Category label */}
        <span style={{ fontSize: "10px", color: "#999999" }}>
          {CATEGORY_LABEL[category]}
        </span>

        {/* Capabilities + short ID */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginTop: "2px",
          }}
        >
          <div style={{ display: "flex", gap: "4px", flexWrap: "wrap" }}>
            {capabilities.slice(0, 5).map((cs) => (
              <CapabilityBadge
                key={cs.capability}
                cap={cs.capability}
                color="#666666"
              />
            ))}
          </div>
          <span
            style={{
              fontSize: "9px",
              color: "#666666",
              fontFamily: "Inter, sans-serif",
              flexShrink: 0,
              marginLeft: "6px",
            }}
          >
            {shortId}
          </span>
        </div>

        {/* Battery bar */}
        {node.battery_percent !== null &&
          node.battery_percent !== undefined && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                marginTop: "4px",
              }}
            >
              <div
                style={{
                  flex: 1,
                  height: "3px",
                  borderRadius: "2px",
                  backgroundColor: "#2D2D2D",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${Math.min(100, Math.max(0, node.battery_percent))}%`,
                    borderRadius: "2px",
                    backgroundColor:
                      node.battery_percent > 50
                        ? "#3DD68C"
                        : node.battery_percent > 20
                          ? "#F5A623"
                          : "#F05252",
                    transition: "width 400ms ease",
                  }}
                />
              </div>
              <span
                style={{
                  fontSize: "9px",
                  color: "#666666",
                  fontFamily: "Inter, sans-serif",
                  flexShrink: 0,
                  minWidth: "24px",
                  textAlign: "right",
                }}
              >
                {Math.round(node.battery_percent)}%
              </span>
            </div>
          )}
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
          width: "240px",
          height: "100%",
          backgroundColor: "#141414",
          borderRight: "1px solid #2D2D2D",
          borderBottom: "1px solid #2D2D2D",
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
            Fleet
          </span>
          <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
            <span style={{ fontSize: "11px", color: "#999999" }}>
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
                  color: "#999999",
                  cursor: "pointer",
                  transition: "background-color 150ms, color 150ms",
                }}
                onMouseEnter={(e) => {
                  const b = e.currentTarget as HTMLButtonElement;
                  b.style.backgroundColor = "#242424";
                  b.style.color = "#4A9EFF";
                }}
                onMouseLeave={(e) => {
                  const b = e.currentTarget as HTMLButtonElement;
                  b.style.backgroundColor = "transparent";
                  b.style.color = "#999999";
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
                color: "#999999",
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
