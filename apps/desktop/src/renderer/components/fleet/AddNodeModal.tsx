import { useState, useEffect } from "react";
import { X, Lock } from "lucide-react";
import { useAddNode } from "../../hooks/useNodes";
import { useDevicePlugins } from "../../hooks/usePlugins";
import type { PluginConfigField, DeviceCapability } from "../../types";

interface AddNodeModalProps {
  onClose: () => void;
}

// ── Shared styles ──────────────────────────────────────────────────────────────

const fieldStyle: React.CSSProperties = {
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
};

// ── Capability metadata ────────────────────────────────────────────────────────

const CAPABILITY_LABEL: Record<DeviceCapability, string> = {
  move_2d: "2D Motion",
  move_3d: "3D Motion",
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

// ── Config field renderer ──────────────────────────────────────────────────────

function ConfigField({
  fieldKey,
  field,
  value,
  onChange,
}: {
  fieldKey: string;
  field: PluginConfigField;
  value: unknown;
  onChange: (k: string, v: unknown) => void;
}) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
      <label style={{ fontSize: "11px", color: "#999999", fontWeight: 500 }}>
        {field.label}
        {field.required && (
          <span style={{ color: "#F05252", marginLeft: "3px" }}>*</span>
        )}
      </label>

      {field.type === "boolean" && (
        <div style={{ display: "flex", gap: "8px" }}>
          {([true, false] as const).map((val) => {
            const active = value === val;
            return (
              <button
                key={String(val)}
                type="button"
                onClick={() => onChange(fieldKey, val)}
                style={{
                  flex: 1,
                  padding: "6px 0",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: 500,
                  cursor: "pointer",
                  border: `1px solid ${active ? "#4A9EFF" : "#2D2D2D"}`,
                  backgroundColor: active ? "#4A9EFF18" : "transparent",
                  color: active ? "#4A9EFF" : "#999999",
                  transition: "all 150ms",
                }}
              >
                {val ? "Yes" : "No"}
              </button>
            );
          })}
        </div>
      )}

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
          style={fieldStyle}
        />
      )}

      {field.type === "select" && (
        <select
          value={value as string}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={{
            ...fieldStyle,
            cursor: "pointer",
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

      {field.type === "string" && (
        <input
          type="text"
          value={value as string}
          placeholder={field.placeholder}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={fieldStyle}
        />
      )}
    </div>
  );
}

// ── Capability chip ────────────────────────────────────────────────────────────

function CapChip({
  cap,
  selected,
  locked,
  onToggle,
}: {
  cap: DeviceCapability;
  selected: boolean;
  locked: boolean;
  onToggle?: () => void;
}) {
  const label = CAPABILITY_LABEL[cap] ?? cap;
  const color = locked ? "#666666" : selected ? "#4A9EFF" : "#666666";
  const bg = locked ? "#24242488" : selected ? "#4A9EFF18" : "transparent";
  const border = locked ? "#2D2D2D" : selected ? "#4A9EFF55" : "#2D2D2D";

  return (
    <button
      type="button"
      disabled={locked}
      onClick={onToggle}
      title={locked ? `${label} (always included)` : label}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "4px",
        padding: "4px 8px",
        borderRadius: "5px",
        border: `1px solid ${border}`,
        backgroundColor: bg,
        color,
        fontSize: "10px",
        fontWeight: 500,
        cursor: locked ? "default" : "pointer",
        transition: "all 120ms",
        flexShrink: 0,
      }}
    >
      {locked && <Lock size={9} />}
      {label}
    </button>
  );
}

// ── Helpers ────────────────────────────────────────────────────────────────────

function initConfig(
  schema: Record<string, PluginConfigField> | undefined,
): Record<string, unknown> {
  if (!schema) return {};
  return Object.fromEntries(
    Object.entries(schema).map(([k, f]) => [
      k,
      f.default !== undefined ? f.default : f.type === "boolean" ? false : "",
    ]),
  );
}

// ── Modal ──────────────────────────────────────────────────────────────────────

export default function AddNodeModal({ onClose }: AddNodeModalProps) {
  const { data: plugins = [], isLoading } = useDevicePlugins();
  const { mutate: addNode, isPending } = useAddNode();

  const [pluginId, setPluginId] = useState("");
  const [name, setName] = useState("");
  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [selectedCaps, setSelectedCaps] = useState<Set<DeviceCapability>>(
    new Set(),
  );
  const [error, setError] = useState<string | null>(null);

  const selectedPlugin = plugins.find((p) => p.id === pluginId);
  const fixedCaps: DeviceCapability[] =
    selectedPlugin?.fixed_capabilities ?? [];
  const optionalCaps: DeviceCapability[] =
    selectedPlugin?.optional_capabilities ?? [];
  const hasCapabilities = fixedCaps.length > 0 || optionalCaps.length > 0;

  // Default to first plugin
  useEffect(() => {
    if (plugins.length > 0 && !pluginId) {
      const first = plugins[0];
      setPluginId(first.id);
      setConfig(initConfig(first.config_schema));
      setSelectedCaps(new Set(first.fixed_capabilities ?? []));
    }
  }, [plugins, pluginId]);

  function handlePluginChange(id: string) {
    setPluginId(id);
    const plugin = plugins.find((p) => p.id === id);
    setConfig(initConfig(plugin?.config_schema));
    setSelectedCaps(new Set(plugin?.fixed_capabilities ?? []));
    setError(null);
  }

  function toggleCap(cap: DeviceCapability) {
    setSelectedCaps((prev) => {
      const next = new Set(prev);
      if (next.has(cap)) next.delete(cap);
      else next.add(cap);
      return next;
    });
  }

  function handleConfigChange(key: string, value: unknown) {
    setConfig((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Device name is required");
      return;
    }
    if (!pluginId) {
      setError("Select a plugin");
      return;
    }

    const finalConfig = {
      ...config,
      selected_capabilities: Array.from(selectedCaps),
    };

    addNode(
      { name: trimmed, plugin_id: pluginId, config: finalConfig },
      {
        onSuccess: () => onClose(),
        onError: (err) =>
          setError(err instanceof Error ? err.message : "Failed to add device"),
      },
    );
  }

  const schemaEntries = Object.entries(selectedPlugin?.config_schema ?? {});

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "380px",
          maxHeight: "82vh",
          display: "flex",
          flexDirection: "column",
          backgroundColor: "#1C1C1C",
          border: "1px solid #2D2D2D",
          borderRadius: "8px",
          overflow: "hidden",
        }}
      >
        {/* Header */}
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            padding: "12px 16px",
            borderBottom: "1px solid #2D2D2D",
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: "13px", fontWeight: 600, color: "#EFEFEF" }}>
            Add Device
          </span>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#999999",
              display: "flex",
              padding: "2px",
            }}
          >
            <X size={14} />
          </button>
        </div>

        {/* Body */}
        <form
          onSubmit={handleSubmit}
          style={{
            padding: "16px",
            display: "flex",
            flexDirection: "column",
            gap: "14px",
            overflowY: "auto",
          }}
        >
          {/* Plugin selector */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{ fontSize: "11px", color: "#999999", fontWeight: 500 }}
            >
              Plugin
            </label>
            {isLoading ? (
              <div
                style={{ ...fieldStyle, color: "#999999", fontStyle: "italic" }}
              >
                Loading plugins…
              </div>
            ) : plugins.length === 0 ? (
              <div style={{ ...fieldStyle, color: "#999999" }}>
                No device plugins installed
              </div>
            ) : (
              <select
                value={pluginId}
                onChange={(e) => handlePluginChange(e.target.value)}
                style={{
                  ...fieldStyle,
                  cursor: "pointer",
                  appearance: "none",
                  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%238B95A3' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'%3E%3C/polyline%3E%3C/svg%3E")`,
                  backgroundRepeat: "no-repeat",
                  backgroundPosition: "right 10px center",
                  paddingRight: "28px",
                }}
              >
                {plugins.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            )}
            {selectedPlugin && (
              <span
                style={{ fontSize: "10px", color: "#999999", lineHeight: 1.5 }}
              >
                {selectedPlugin.description}
              </span>
            )}
          </div>

          {/* Device name */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{ fontSize: "11px", color: "#999999", fontWeight: 500 }}
            >
              Device Name <span style={{ color: "#F05252" }}>*</span>
            </label>
            <input
              autoFocus
              type="text"
              placeholder={
                selectedPlugin?.node_types[0]
                  ? `e.g. ${selectedPlugin.node_types[0]} 1`
                  : "e.g. Robot 1"
              }
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError(null);
              }}
              style={{
                ...fieldStyle,
                borderColor: error ? "#F05252" : "#2D2D2D",
                userSelect: "text",
              }}
            />
          </div>

          {/* Dynamic config fields */}
          {schemaEntries.map(([key, field]) => (
            <ConfigField
              key={key}
              fieldKey={key}
              field={field}
              value={config[key]}
              onChange={handleConfigChange}
            />
          ))}

          {/* Capabilities */}
          {hasCapabilities && (
            <div
              style={{ display: "flex", flexDirection: "column", gap: "8px" }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}
              >
                <label
                  style={{
                    fontSize: "11px",
                    color: "#999999",
                    fontWeight: 500,
                  }}
                >
                  Device Capabilities
                </label>
                {optionalCaps.length > 0 && (
                  <span style={{ fontSize: "10px", color: "#666666" }}>
                    {selectedCaps.size - fixedCaps.length}/{optionalCaps.length}{" "}
                    optional selected
                  </span>
                )}
              </div>

              {/* Fixed capabilities */}
              {fixedCaps.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "4px",
                  }}
                >
                  <span
                    style={{
                      fontSize: "10px",
                      color: "#666666",
                      fontWeight: 500,
                    }}
                  >
                    Always included
                  </span>
                  <div
                    style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}
                  >
                    {fixedCaps.map((cap) => (
                      <CapChip key={cap} cap={cap} selected locked />
                    ))}
                  </div>
                </div>
              )}

              {/* Optional capabilities */}
              {optionalCaps.length > 0 && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: "4px",
                  }}
                >
                  {fixedCaps.length > 0 && (
                    <span
                      style={{
                        fontSize: "10px",
                        color: "#666666",
                        fontWeight: 500,
                      }}
                    >
                      Optional attachments
                    </span>
                  )}
                  <div
                    style={{ display: "flex", flexWrap: "wrap", gap: "6px" }}
                  >
                    {optionalCaps.map((cap) => (
                      <CapChip
                        key={cap}
                        cap={cap}
                        selected={selectedCaps.has(cap)}
                        locked={false}
                        onToggle={() => toggleCap(cap)}
                      />
                    ))}
                  </div>
                  <span
                    style={{
                      fontSize: "10px",
                      color: "#666666",
                      marginTop: "2px",
                    }}
                  >
                    Click to toggle. Selected capabilities appear on the device
                    card.
                  </span>
                </div>
              )}
            </div>
          )}

          {error && (
            <span style={{ fontSize: "11px", color: "#F05252" }}>{error}</span>
          )}

          {/* Actions */}
          <div
            style={{
              display: "flex",
              gap: "8px",
              justifyContent: "flex-end",
              paddingTop: "4px",
            }}
          >
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: "7px 14px",
                borderRadius: "6px",
                background: "none",
                border: "1px solid #2D2D2D",
                color: "#999999",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending || !pluginId}
              style={{
                padding: "7px 14px",
                borderRadius: "6px",
                backgroundColor: isPending || !pluginId ? "#2D2D2D" : "#4A9EFF",
                border: "none",
                color: isPending || !pluginId ? "#999999" : "white",
                fontSize: "12px",
                fontWeight: 500,
                cursor: isPending || !pluginId ? "not-allowed" : "pointer",
                transition: "background-color 150ms",
              }}
            >
              {isPending ? "Adding…" : "Add Device"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
