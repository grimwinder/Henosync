import { useState, useEffect } from "react";
import { Plug, Cpu, Zap, Plus, Settings, CheckCircle } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useDevicePlugins, useControlPlugins } from "../hooks/usePlugins";
import { NODE_KEYS } from "../hooks/useNodes";
import * as api from "../lib/api";
import type {
  PluginManifest,
  ControlPluginInfo,
  PluginConfigField,
} from "../types";

// ── Helpers ────────────────────────────────────────────────────────────────────

function initConfigValues(
  schema: Record<string, PluginConfigField> | undefined,
): Record<string, unknown> {
  if (!schema) return {};
  return Object.fromEntries(
    Object.entries(schema).map(([key, field]) => [
      key,
      field.default !== undefined
        ? field.default
        : field.type === "boolean"
          ? false
          : "",
    ]),
  );
}

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

const baseInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "7px 10px",
  backgroundColor: "#0D0F12",
  border: "1px solid #2A2F38",
  borderRadius: "6px",
  fontSize: "12px",
  color: "#E8EAED",
  outline: "none",
  fontFamily: "Inter, sans-serif",
  boxSizing: "border-box",
};

// ── ConfigField ────────────────────────────────────────────────────────────────

interface ConfigFieldProps {
  fieldKey: string;
  field: PluginConfigField;
  value: unknown;
  onChange: (key: string, value: unknown) => void;
}

function ConfigField({ fieldKey, field, value, onChange }: ConfigFieldProps) {
  return (
    <div style={{ marginBottom: "18px" }}>
      {/* Label row */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "4px",
          marginBottom: "5px",
        }}
      >
        <label style={{ fontSize: "11px", fontWeight: 500, color: "#8B95A3" }}>
          {field.label}
        </label>
        {field.required && (
          <span style={{ fontSize: "10px", color: "#F05252" }}>*</span>
        )}
      </div>

      {/* Optional description */}
      {field.description && (
        <p
          style={{
            fontSize: "10px",
            color: "#8B95A3",
            margin: "0 0 7px",
            lineHeight: 1.6,
          }}
        >
          {field.description}
        </p>
      )}

      {/* Boolean → Yes / No pill buttons */}
      {field.type === "boolean" && (
        <div style={{ display: "flex", gap: "8px" }}>
          {(
            [
              { label: "Yes", val: true },
              { label: "No", val: false },
            ] as const
          ).map(({ label, val }) => {
            const active = value === val;
            return (
              <button
                key={label}
                type="button"
                onClick={() => onChange(fieldKey, val)}
                style={{
                  padding: "5px 20px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: 500,
                  cursor: "pointer",
                  border: `1px solid ${active ? "#4A9EFF" : "#2A2F38"}`,
                  backgroundColor: active ? "#4A9EFF18" : "transparent",
                  color: active ? "#4A9EFF" : "#8B95A3",
                  transition: "all 150ms",
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      )}

      {/* Number → numeric input */}
      {field.type === "number" && (
        <input
          type="number"
          value={value as number | ""}
          min={field.min}
          max={field.max}
          placeholder={field.placeholder}
          onChange={(e) =>
            onChange(
              fieldKey,
              e.target.value === "" ? "" : Number(e.target.value),
            )
          }
          style={baseInputStyle}
        />
      )}

      {/* Select → styled dropdown */}
      {field.type === "select" && (
        <select
          value={value as string}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={{
            ...baseInputStyle,
            cursor: "pointer",
            // Custom caret via SVG background
            appearance: "none",
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238B95A3' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
            backgroundRepeat: "no-repeat",
            backgroundPosition: "right 10px center",
            paddingRight: "28px",
          }}
        >
          <option value="" disabled>
            Select…
          </option>
          {field.options?.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {opt.label}
            </option>
          ))}
        </select>
      )}

      {/* String → text input */}
      {field.type === "string" && (
        <input
          type="text"
          value={value as string}
          placeholder={field.placeholder}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={baseInputStyle}
        />
      )}
    </div>
  );
}

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
          color: "#8B95A3",
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
        fontFamily: "JetBrains Mono, monospace",
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
        borderBottom: "1px solid #2A2F38",
        backgroundColor: "#0D0F1280",
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
            color: "#8B95A3",
            textTransform: "uppercase",
          }}
        >
          {label}
        </span>
      </div>
      <span
        style={{
          fontSize: "10px",
          color: "#8B95A3",
          backgroundColor: "#252A31",
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
        backgroundColor: selected ? "#1C1F24" : "transparent",
        border: "none",
        borderBottom: "1px solid #2A2F38",
        cursor: "pointer",
        display: "flex",
        alignItems: "flex-start",
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
      {/* Kind accent bar */}
      <div
        style={{
          width: "3px",
          alignSelf: "stretch",
          borderRadius: "2px",
          backgroundColor: selected ? accentColor : "#252A31",
          flexShrink: 0,
          transition: "background-color 150ms",
        }}
      />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div
          style={{
            fontSize: "12px",
            fontWeight: 500,
            color: selected ? "#E8EAED" : "#C8CAD0",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            marginBottom: "2px",
          }}
        >
          {name}
        </div>
        <div
          style={{ fontSize: "10px", color: "#8B95A3", marginBottom: "3px" }}
        >
          v{version}
        </div>
        <div
          style={{
            fontSize: "10px",
            color: "#8B95A3",
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
        borderBottom: "1px solid #2A2F38",
        backgroundColor: "#0D0F12",
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
          <span style={{ fontSize: "18px", fontWeight: 600, color: "#E8EAED" }}>
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
        <div style={{ fontSize: "12px", color: "#8B95A3", lineHeight: 1.6 }}>
          {description}
        </div>
      </div>
    </div>
  );
}

// ── Device Plugin Panel ────────────────────────────────────────────────────────

function DevicePluginPanel({ plugin }: { plugin: PluginManifest }) {
  const qc = useQueryClient();
  const schema = plugin.config_schema ?? {};
  const hasSchema = Object.keys(schema).length > 0;

  const [configValues, setConfigValues] = useState<Record<string, unknown>>(
    () => initConfigValues(plugin.config_schema),
  );
  const [deviceName, setDeviceName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [addedName, setAddedName] = useState<string | null>(null);

  useEffect(() => {
    setConfigValues(initConfigValues(plugin.config_schema));
    setDeviceName("");
    setNameError(null);
    setAddedName(null);
  }, [plugin.id]);

  const {
    mutate: addNode,
    isPending: isAdding,
    error: addError,
  } = useMutation({
    mutationFn: () =>
      api.addNode({
        name: deviceName.trim(),
        plugin_id: plugin.id,
        config: configValues,
      }),
    onSuccess: (node) => {
      setAddedName(node.name);
      setDeviceName("");
      qc.invalidateQueries({ queryKey: NODE_KEYS.all });
      setTimeout(() => setAddedName(null), 4000);
    },
  });

  function handleChangeConfig(key: string, value: unknown) {
    setConfigValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleAddDevice() {
    if (!deviceName.trim()) {
      setNameError("Device name is required");
      return;
    }
    setNameError(null);
    addNode();
  }

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

        {/* Connection parameters */}
        <Section title={hasSchema ? "Connection Parameters" : "Configuration"}>
          {hasSchema ? (
            Object.entries(schema).map(([key, field]) => (
              <ConfigField
                key={key}
                fieldKey={key}
                field={field}
                value={configValues[key]}
                onChange={handleChangeConfig}
              />
            ))
          ) : (
            <p
              style={{
                fontSize: "11px",
                color: "#8B95A3",
                fontStyle: "italic",
                margin: 0,
              }}
            >
              No configuration parameters required for this plugin.
            </p>
          )}
        </Section>

        {/* Add Device */}
        <Section title="Add Device">
          <p
            style={{
              fontSize: "11px",
              color: "#8B95A3",
              lineHeight: 1.6,
              marginBottom: "16px",
            }}
          >
            Register a new device that connects using this plugin. The
            connection parameters above will be applied when Henosync
            establishes the link.
          </p>

          {/* Device name input */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "6px",
              marginBottom: "14px",
            }}
          >
            <label
              style={{ fontSize: "11px", fontWeight: 500, color: "#8B95A3" }}
            >
              Device Name <span style={{ color: "#F05252" }}>*</span>
            </label>
            <input
              type="text"
              placeholder={`e.g. ${plugin.node_types[0] ?? plugin.name} 1`}
              value={deviceName}
              onChange={(e) => {
                setDeviceName(e.target.value);
                setNameError(null);
              }}
              style={{
                ...baseInputStyle,
                borderColor: nameError ? "#F05252" : "#2A2F38",
              }}
            />
            {nameError && (
              <span style={{ fontSize: "11px", color: "#F05252" }}>
                {nameError}
              </span>
            )}
          </div>

          {/* Success / error feedback */}
          {addedName && (
            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: "8px",
                padding: "8px 12px",
                borderRadius: "6px",
                backgroundColor: "#3DD68C18",
                border: "1px solid #3DD68C30",
                color: "#3DD68C",
                fontSize: "12px",
                marginBottom: "10px",
              }}
            >
              <CheckCircle size={14} />
              <span>"{addedName}" added successfully</span>
            </div>
          )}
          {addError && (
            <p
              style={{
                fontSize: "11px",
                color: "#F05252",
                marginBottom: "10px",
              }}
            >
              {addError instanceof Error
                ? addError.message
                : "Failed to add device"}
            </p>
          )}

          <button
            onClick={handleAddDevice}
            disabled={isAdding}
            style={{
              display: "flex",
              alignItems: "center",
              gap: "6px",
              padding: "8px 16px",
              borderRadius: "6px",
              backgroundColor: isAdding ? "#2A2F38" : "#4A9EFF",
              border: "none",
              color: isAdding ? "#8B95A3" : "white",
              fontSize: "12px",
              fontWeight: 500,
              cursor: isAdding ? "not-allowed" : "pointer",
              transition: "background-color 150ms",
            }}
          >
            <Plus size={13} />
            {isAdding ? "Adding…" : "Add Device"}
          </button>
        </Section>
      </div>
    </div>
  );
}

// ── Control Plugin Panel ───────────────────────────────────────────────────────

function ControlPluginPanel({ plugin }: { plugin: ControlPluginInfo }) {
  const schema = plugin.ui.config_schema ?? {};
  const hasSchema = Object.keys(schema).length > 0;

  const [configValues, setConfigValues] = useState<Record<string, unknown>>(
    () => initConfigValues(schema),
  );
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setConfigValues(initConfigValues(schema));
    setSaved(false);
  }, [plugin.id]);

  function handleChangeConfig(key: string, value: unknown) {
    setConfigValues((prev) => ({ ...prev, [key]: value }));
    setSaved(false);
  }

  function handleSave() {
    // Config held in session state; persisted to backend once a config endpoint exists
    setSaved(true);
    setTimeout(() => setSaved(false), 3000);
  }

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
                color: "#8B95A3",
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

        {/* Operation parameters */}
        <Section title={hasSchema ? "Operation Parameters" : "Configuration"}>
          {hasSchema ? (
            <>
              <p
                style={{
                  fontSize: "11px",
                  color: "#8B95A3",
                  lineHeight: 1.6,
                  marginBottom: "16px",
                }}
              >
                These parameters are passed to the plugin when an operation
                starts.
              </p>

              {Object.entries(schema).map(([key, field]) => (
                <ConfigField
                  key={key}
                  fieldKey={key}
                  field={field}
                  value={configValues[key]}
                  onChange={handleChangeConfig}
                />
              ))}

              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "12px",
                  marginTop: "8px",
                }}
              >
                <button
                  onClick={handleSave}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "6px",
                    padding: "8px 16px",
                    borderRadius: "6px",
                    backgroundColor: saved ? "#3DD68C18" : "#252A31",
                    border: `1px solid ${saved ? "#3DD68C40" : "#2A2F38"}`,
                    color: saved ? "#3DD68C" : "#E8EAED",
                    fontSize: "12px",
                    fontWeight: 500,
                    cursor: "pointer",
                    transition: "all 150ms",
                  }}
                >
                  {saved ? <CheckCircle size={13} /> : <Settings size={13} />}
                  {saved ? "Saved" : "Save Configuration"}
                </button>
                {!saved && (
                  <span style={{ fontSize: "10px", color: "#8B95A3" }}>
                    Applied when this operation is started
                  </span>
                )}
              </div>
            </>
          ) : (
            <p
              style={{
                fontSize: "11px",
                color: "#8B95A3",
                fontStyle: "italic",
                margin: 0,
              }}
            >
              No configuration parameters required for this plugin.
            </p>
          )}
        </Section>
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
        backgroundColor: "#0D0F12",
      }}
    >
      {/* ── Left sidebar ────────────────────────────────────────────────── */}
      <div
        style={{
          width: "280px",
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
            padding: "0 14px",
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
                color: "#8B95A3",
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
                    color: "#8B95A3",
                    fontStyle: "italic",
                    borderBottom: "1px solid #2A2F38",
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
                    color: "#8B95A3",
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
            <Plug size={40} color="#2A2F38" />
            <span style={{ fontSize: "13px", color: "#8B95A3" }}>
              Select a plugin to view its details and configuration
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
