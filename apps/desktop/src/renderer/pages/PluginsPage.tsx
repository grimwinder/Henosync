import { useState } from "react";
import { Plug, Cpu, Zap } from "lucide-react";
import { useDevicePlugins, useControlPlugins } from "../hooks/usePlugins";
import type { PluginManifest, ControlPluginInfo } from "../types";

const CAPABILITY_LABEL: Record<string, string> = {
  move_2d: "Move 2D",
  move_3d: "Move 3D",
  gps: "GPS",
  lidar: "LiDAR",
  camera: "Camera",
  sonar: "Sonar",
  imu: "IMU",
  thermal: "Thermal",
  horn: "Horn",
  lights: "Lights",
  payload: "Payload",
  arm_tool: "Arm Tool",
  battery: "Battery",
  charging: "Charging",
};

const CATEGORY_LABEL: Record<string, string> = {
  drone: "Drone",
  plane: "Plane",
  agv: "Ground Vehicle",
  boat: "Boat",
  rov: "ROV",
  arm: "Robotic Arm",
  unknown: "Unknown",
};

// ── Shared layout primitives ───────────────────────────────────────────────────

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: "28px" }}>
      <div
        style={{
          fontSize: "10px",
          fontWeight: 600,
          letterSpacing: "1px",
          color: "#999999",
          textTransform: "uppercase",
          marginBottom: "12px",
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
        borderBottom: "1px solid #242424",
      }}
    >
      <span style={{ fontSize: "11px", color: "#999999", flexShrink: 0 }}>
        {label}
      </span>
      <span
        style={{
          fontSize: "11px",
          color: "#EFEFEF",
          fontFamily: "Inter, sans-serif",
          textAlign: "right",
          wordBreak: "break-all",
        }}
      >
        {value}
      </span>
    </div>
  );
}

function Chip({ label, color = "#4A9EFF" }: { label: string; color?: string }) {
  return (
    <div
      style={{
        padding: "3px 8px",
        borderRadius: "4px",
        backgroundColor: `${color}14`,
        border: `1px solid ${color}30`,
        fontSize: "10px",
        fontWeight: 500,
        color,
        fontFamily: "Inter, sans-serif",
        cursor: "default",
        whiteSpace: "nowrap",
      }}
    >
      {label}
    </div>
  );
}

// ── Left sidebar primitives ────────────────────────────────────────────────────

function SidebarSectionHeader({
  label,
  count,
  accentColor,
}: {
  label: string;
  count: number;
  accentColor: string;
}) {
  return (
    <div
      style={{
        padding: "8px 14px 6px",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        borderBottom: "1px solid #2D2D2D",
        backgroundColor: "#0D0D0D",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <div
          style={{
            width: "4px",
            height: "12px",
            borderRadius: "2px",
            backgroundColor: accentColor,
          }}
        />
        <span
          style={{
            fontSize: "10px",
            fontWeight: 600,
            letterSpacing: "1px",
            color: "#999999",
            textTransform: "uppercase",
          }}
        >
          {label}
        </span>
      </div>
      <span
        style={{
          fontSize: "10px",
          color: "#999999",
          backgroundColor: "#242424",
          padding: "1px 6px",
          borderRadius: "8px",
        }}
      >
        {count}
      </span>
    </div>
  );
}

type PluginKind = "device" | "control";

interface PluginRowProps {
  name: string;
  version: string;
  description: string;
  kind: PluginKind;
  selected: boolean;
  onClick: () => void;
}

function PluginRow({
  name,
  version,
  description,
  kind,
  selected,
  onClick,
}: PluginRowProps) {
  const accentColor = kind === "device" ? "#4A9EFF" : "#A78BFA";
  return (
    <button
      onClick={onClick}
      style={{
        width: "100%",
        textAlign: "left",
        padding: "10px 14px",
        backgroundColor: selected ? "#1C1C1C" : "transparent",
        border: "none",
        borderBottom: "1px solid #2D2D2D",
        cursor: "pointer",
        display: "flex",
        alignItems: "flex-start",
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
      {/* Kind accent bar */}
      <div
        style={{
          width: "3px",
          alignSelf: "stretch",
          borderRadius: "2px",
          backgroundColor: selected ? accentColor : "#242424",
          flexShrink: 0,
          transition: "background-color 150ms",
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 500,
            color: selected ? "#EFEFEF" : "#C8CAD0",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            marginBottom: "2px",
          }}
        >
          {name}
        </div>
        <div
          style={{ fontSize: "10px", color: "#999999", marginBottom: "3px" }}
        >
          v{version}
        </div>
        <div
          style={{
            fontSize: "10px",
            color: "#999999",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {description}
        </div>
      </div>
    </button>
  );
}

// ── Plugin hero header (shared) ────────────────────────────────────────────────

function PluginHero({
  name,
  description,
  kind,
}: {
  name: string;
  description: string;
  kind: PluginKind;
}) {
  const isDevice = kind === "device";
  const accentColor = isDevice ? "#4A9EFF" : "#A78BFA";
  const badgeLabel = isDevice ? "DEVICE PLUGIN" : "CONTROL PLUGIN";
  const Icon = isDevice ? Cpu : Zap;

  return (
    <div
      style={{
        padding: "24px 32px 20px",
        borderBottom: "1px solid #2D2D2D",
        backgroundColor: "#0D0D0D",
        flexShrink: 0,
        display: "flex",
        alignItems: "flex-start",
        gap: "16px",
      }}
    >
      <div
        style={{
          width: "44px",
          height: "44px",
          borderRadius: "10px",
          backgroundColor: `${accentColor}18`,
          border: `1px solid ${accentColor}30`,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
        }}
      >
        <Icon size={20} color={accentColor} />
      </div>
      <div style={{ flex: 1 }}>
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "10px",
            flexWrap: "wrap",
            marginBottom: "6px",
          }}
        >
          <span style={{ fontSize: "18px", fontWeight: 600, color: "#EFEFEF" }}>
            {name}
          </span>
          <span
            style={{
              padding: "2px 8px",
              borderRadius: "4px",
              fontSize: "10px",
              fontWeight: 600,
              backgroundColor: `${accentColor}18`,
              border: `1px solid ${accentColor}30`,
              color: accentColor,
              letterSpacing: "0.5px",
            }}
          >
            {badgeLabel}
          </span>
        </div>
        <div style={{ fontSize: "12px", color: "#999999", lineHeight: 1.6 }}>
          {description}
        </div>
      </div>
    </div>
  );
}

// ── Device Plugin Panel ────────────────────────────────────────────────────────

function DevicePluginPanel({ plugin }: { plugin: PluginManifest }) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <PluginHero
        name={plugin.name}
        description={plugin.description}
        kind="device"
      />

      <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px 48px" }}>
        {/* Plugin Details */}
        <Section title="Plugin Details">
          <InfoRow label="Plugin ID" value={plugin.id} />
          <InfoRow label="Version" value={plugin.version} />
          <InfoRow label="Author" value={plugin.author} />
          <InfoRow label="Transport" value={plugin.transport} />
          <InfoRow label="SDK Version" value={plugin.sdk_version} />
        </Section>

        {/* Compatible device types */}
        {plugin.node_types.length > 0 && (
          <Section title="Compatible Device Types">
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {plugin.node_types.map((t) => (
                <Chip key={t} label={t} color="#4A9EFF" />
              ))}
            </div>
          </Section>
        )}

        {/* Provided capabilities */}
        {plugin.capabilities.length > 0 && (
          <Section title="Provided Capabilities">
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {plugin.capabilities.map((cap) => (
                <Chip
                  key={cap.id}
                  label={cap.label}
                  color={cap.destructive ? "#F05252" : "#3DD68C"}
                />
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

// ── Control Plugin Panel ───────────────────────────────────────────────────────

function ControlPluginPanel({ plugin }: { plugin: ControlPluginInfo }) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      <PluginHero
        name={plugin.name}
        description={plugin.description}
        kind="control"
      />

      <div style={{ flex: 1, overflowY: "auto", padding: "24px 32px 48px" }}>
        {/* Plugin Details */}
        <Section title="Plugin Details">
          <InfoRow label="Plugin ID" value={plugin.id} />
          <InfoRow label="Version" value={plugin.version} />
          <InfoRow label="Author" value={plugin.author} />
          <InfoRow label="Operation Name" value={plugin.operation_name} />
          <InfoRow label="Priority" value={String(plugin.priority)} />
        </Section>

        {/* Required capabilities */}
        {plugin.required_capabilities.length > 0 && (
          <Section title="Required Device Capabilities">
            <p
              style={{
                fontSize: "11px",
                color: "#999999",
                lineHeight: 1.6,
                marginBottom: "10px",
              }}
            >
              Devices assigned to this operation must provide all of the
              following capabilities.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {plugin.required_capabilities.map((cap) => (
                <Chip
                  key={cap}
                  label={CAPABILITY_LABEL[cap] ?? cap}
                  color="#A78BFA"
                />
              ))}
            </div>
          </Section>
        )}

        {/* Compatible device categories */}
        {plugin.supported_categories.length > 0 && (
          <Section title="Compatible Device Types">
            <div style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {plugin.supported_categories.map((cat) => (
                <Chip
                  key={cat}
                  label={CATEGORY_LABEL[cat] ?? cat}
                  color="#F5A623"
                />
              ))}
            </div>
          </Section>
        )}
      </div>
    </div>
  );
}

// ── PluginsPage ────────────────────────────────────────────────────────────────

type SelectedEntry =
  | { kind: "device"; id: string }
  | { kind: "control"; id: string }
  | null;

export default function PluginsPage() {
  const [selected, setSelected] = useState<SelectedEntry>(null);

  const { data: devicePlugins = [], isLoading: loadingDevice } =
    useDevicePlugins();
  const { data: controlPlugins = [], isLoading: loadingControl } =
    useControlPlugins();

  const isLoading = loadingDevice || loadingControl;

  const selectedDevicePlugin =
    selected?.kind === "device"
      ? (devicePlugins.find((p) => p.id === selected.id) ?? null)
      : null;

  const selectedControlPlugin =
    selected?.kind === "control"
      ? (controlPlugins.find((p) => p.id === selected.id) ?? null)
      : null;

  return (
    <div
      style={{
        display: "flex",
        flex: 1,
        overflow: "hidden",
        backgroundColor: "#0D0D0D",
      }}
    >
      {/* ── Left sidebar ────────────────────────────────────────────────── */}
      <div
        style={{
          width: "240px",
          flexShrink: 0,
          backgroundColor: "#141414",
          borderRight: "1px solid #2D2D2D",
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
            padding: "0 14px",
            borderBottom: "1px solid #2D2D2D",
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
            Plugins
          </span>
        </div>

        {/* Plugin list */}
        <div style={{ flex: 1, overflowY: "auto" }}>
          {isLoading ? (
            <div
              style={{
                padding: "24px 14px",
                textAlign: "center",
                color: "#999999",
                fontSize: "11px",
              }}
            >
              Loading plugins…
            </div>
          ) : (
            <>
              {/* Device plugins section */}
              <SidebarSectionHeader
                label="Device Plugins"
                count={devicePlugins.length}
                accentColor="#4A9EFF"
              />
              {devicePlugins.length === 0 ? (
                <div
                  style={{
                    padding: "12px 14px 16px",
                    fontSize: "11px",
                    color: "#999999",
                    fontStyle: "italic",
                    borderBottom: "1px solid #2D2D2D",
                  }}
                >
                  No device plugins installed.
                </div>
              ) : (
                devicePlugins.map((p) => (
                  <PluginRow
                    key={p.id}
                    name={p.name}
                    version={p.version}
                    description={p.description}
                    kind="device"
                    selected={
                      selected?.kind === "device" && selected.id === p.id
                    }
                    onClick={() => setSelected({ kind: "device", id: p.id })}
                  />
                ))
              )}

              {/* Control plugins section */}
              <SidebarSectionHeader
                label="Control Plugins"
                count={controlPlugins.length}
                accentColor="#A78BFA"
              />
              {controlPlugins.length === 0 ? (
                <div
                  style={{
                    padding: "12px 14px 16px",
                    fontSize: "11px",
                    color: "#999999",
                    fontStyle: "italic",
                  }}
                >
                  No control plugins installed.
                </div>
              ) : (
                controlPlugins.map((p) => (
                  <PluginRow
                    key={p.id}
                    name={p.name}
                    version={p.version}
                    description={p.description}
                    kind="control"
                    selected={
                      selected?.kind === "control" && selected.id === p.id
                    }
                    onClick={() => setSelected({ kind: "control", id: p.id })}
                  />
                ))
              )}
            </>
          )}
        </div>
      </div>

      {/* ── Main content ────────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflow: "hidden", display: "flex" }}>
        {selectedDevicePlugin ? (
          <DevicePluginPanel plugin={selectedDevicePlugin} />
        ) : selectedControlPlugin ? (
          <ControlPluginPanel plugin={selectedControlPlugin} />
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
            <Plug size={40} color="#2D2D2D" />
            <span style={{ fontSize: "13px", color: "#999999" }}>
              Select a plugin to view its details and configuration
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
