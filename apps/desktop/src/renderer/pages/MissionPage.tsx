import { useState, useRef, useCallback } from "react";
import maplibregl from "maplibre-gl";
import {
  Plus,
  Trash2,
  ArrowUp,
  ArrowDown,
  Play,
  SkipForward,
  X,
  Blocks,
  Settings2,
  Search,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import MissionMap, {
  type MapBase,
  type MapTheme,
} from "../components/map/MissionMap";
import MapStylePicker from "../components/map/MapStylePicker";
import HubMarker from "../components/map/HubMarker";
import NodeMarkers from "../components/map/NodeMarkers";
import { useHubLocation } from "../hooks/useHubLocation";
import { useControlPlugins } from "../hooks/usePlugins";
import type { ControlPluginInfo, PluginConfigField } from "../types";

// ── Layout constants ───────────────────────────────────────────────────────────

const BOTTOM_H = 300;
const RIGHT_W = 260;

// ── Data model ─────────────────────────────────────────────────────────────────

interface MissionBlock {
  instanceId: string;
  pluginId: string;
  displayName: string;
  configSchema: Record<string, PluginConfigField>;
  params: Record<string, unknown>;
}

function defaultParams(
  schema: Record<string, PluginConfigField>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const [key, field] of Object.entries(schema)) {
    out[key] =
      field.default ??
      (field.type === "boolean" ? false : field.type === "number" ? 0 : "");
  }
  return out;
}

// ── Shared icon button ─────────────────────────────────────────────────────────

function IconBtn({
  children,
  onClick,
  title,
  disabled,
  danger,
  size = 22,
}: {
  children: React.ReactNode;
  onClick: (e: React.MouseEvent) => void;
  title?: string;
  disabled?: boolean;
  danger?: boolean;
  size?: number;
}) {
  return (
    <button
      title={title}
      disabled={disabled}
      onClick={onClick}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        borderRadius: "4px",
        border: "none",
        backgroundColor: "transparent",
        color: disabled ? "#3A3F48" : danger ? "#F05252" : "#8B95A3",
        cursor: disabled ? "default" : "pointer",
        transition: "background-color 100ms, color 100ms",
        flexShrink: 0,
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = danger
            ? "#F0525218"
            : "#1C1F24";
          if (!danger)
            (e.currentTarget as HTMLButtonElement).style.color = "#E8EAED";
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "transparent";
          (e.currentTarget as HTMLButtonElement).style.color = danger
            ? "#F05252"
            : "#8B95A3";
        }
      }}
    >
      {children}
    </button>
  );
}

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
  onChange: (key: string, val: unknown) => void;
}) {
  const inputBase: React.CSSProperties = {
    width: "100%",
    backgroundColor: "#0D0F12",
    border: "1px solid #2A2F38",
    borderRadius: "5px",
    color: "#E8EAED",
    fontSize: "11px",
    padding: "5px 8px",
    outline: "none",
    boxSizing: "border-box",
  };

  if (field.type === "boolean") {
    return (
      <label
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          cursor: "pointer",
          fontSize: "11px",
          color: "#8B95A3",
        }}
      >
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(fieldKey, e.target.checked)}
          style={{ accentColor: "#A78BFA", width: "13px", height: "13px" }}
        />
        {field.label}
      </label>
    );
  }

  if (field.type === "select" && field.options) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
        <span style={{ fontSize: "10px", color: "#555F6E" }}>
          {field.label}
        </span>
        <select
          value={String(value ?? "")}
          onChange={(e) => onChange(fieldKey, e.target.value)}
          style={{ ...inputBase, cursor: "pointer" }}
        >
          {field.options.map((opt) => (
            <option key={String(opt.value)} value={String(opt.value)}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
      <span style={{ fontSize: "10px", color: "#555F6E" }}>{field.label}</span>
      <input
        type={field.type === "number" ? "number" : "text"}
        value={String(value ?? "")}
        placeholder={field.placeholder ?? ""}
        min={field.min}
        max={field.max}
        onChange={(e) =>
          onChange(
            fieldKey,
            field.type === "number" ? Number(e.target.value) : e.target.value,
          )
        }
        style={inputBase}
      />
      {field.description && (
        <span style={{ fontSize: "10px", color: "#555F6E", lineHeight: 1.3 }}>
          {field.description}
        </span>
      )}
    </div>
  );
}

// ── Right panel — ordered step list ───────────────────────────────────────────

function StepListPanel({
  blocks,
  selectedId,
  onSelect,
  onDelete,
  onMoveUp,
  onMoveDown,
  plugins,
}: {
  blocks: MissionBlock[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  plugins: ControlPluginInfo[];
}) {
  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        right: 0,
        width: `${RIGHT_W}px`,
        height: `calc(100% - ${BOTTOM_H}px)`,
        backgroundColor: "#0D0F12CC",
        backdropFilter: "blur(6px)",
        borderLeft: "1px solid #2A2F38",
        borderBottom: "1px solid #2A2F38",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "12px 12px 10px",
          borderBottom: "1px solid #2A2F38",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "1.2px",
            color: "#555F6E",
          }}
        >
          MISSION PLAN
        </span>
      </div>

      {/* Step list */}
      <div
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "8px",
          display: "flex",
          flexDirection: "column",
          gap: "6px",
        }}
      >
        {blocks.length === 0 ? (
          <div
            style={{
              flex: 1,
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "10px",
              color: "#3A3F48",
            }}
          >
            <Blocks size={28} strokeWidth={1.2} />
            <span
              style={{
                fontSize: "11px",
                textAlign: "center",
                maxWidth: "150px",
                lineHeight: 1.4,
              }}
            >
              {plugins.length === 0
                ? "Install a control plugin to get started"
                : "Add steps from the panel below"}
            </span>
          </div>
        ) : (
          blocks.map((block, i) => {
            const selected = block.instanceId === selectedId;
            return (
              <div
                key={block.instanceId}
                onClick={() => onSelect(block.instanceId)}
                style={{
                  display: "flex",
                  backgroundColor: selected ? "#A78BFA0D" : "#141619",
                  border: `1px solid ${selected ? "#A78BFA55" : "#2A2F38"}`,
                  borderRadius: "7px",
                  overflow: "hidden",
                  cursor: "pointer",
                  flexShrink: 0,
                  transition: "all 120ms",
                }}
              >
                {/* Left accent */}
                <div
                  style={{
                    width: "3px",
                    backgroundColor: selected ? "#A78BFA" : "#3A3F48",
                    flexShrink: 0,
                    transition: "background-color 120ms",
                  }}
                />
                <div
                  style={{
                    flex: 1,
                    padding: "8px 8px",
                    display: "flex",
                    alignItems: "center",
                    gap: "7px",
                    minWidth: 0,
                  }}
                >
                  {/* Step number */}
                  <div
                    style={{
                      width: "18px",
                      height: "18px",
                      borderRadius: "50%",
                      backgroundColor: selected ? "#A78BFA22" : "#1C1F24",
                      border: `1px solid ${selected ? "#A78BFA" : "#3A3F48"}`,
                      color: selected ? "#A78BFA" : "#555F6E",
                      fontSize: "9px",
                      fontWeight: 700,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      flexShrink: 0,
                    }}
                  >
                    {i + 1}
                  </div>
                  {/* Name */}
                  <span
                    style={{
                      flex: 1,
                      fontSize: "11px",
                      fontWeight: 600,
                      color: selected ? "#E8EAED" : "#8B95A3",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {block.displayName}
                  </span>
                  {/* Reorder + delete */}
                  <div style={{ display: "flex", gap: "1px", flexShrink: 0 }}>
                    <IconBtn
                      title="Move up"
                      disabled={i === 0}
                      size={20}
                      onClick={(e) => {
                        e.stopPropagation();
                        onMoveUp(block.instanceId);
                      }}
                    >
                      <ArrowUp size={10} />
                    </IconBtn>
                    <IconBtn
                      title="Move down"
                      disabled={i === blocks.length - 1}
                      size={20}
                      onClick={(e) => {
                        e.stopPropagation();
                        onMoveDown(block.instanceId);
                      }}
                    >
                      <ArrowDown size={10} />
                    </IconBtn>
                    <IconBtn
                      title="Delete step"
                      danger
                      size={20}
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(block.instanceId);
                      }}
                    >
                      <Trash2 size={10} />
                    </IconBtn>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── Step types browser ─────────────────────────────────────────────────────────

function StepTypesSection({
  plugins,
  onAdd,
}: {
  plugins: ControlPluginInfo[];
  onAdd: (plugin: ControlPluginInfo) => void;
}) {
  const [search, setSearch] = useState("");
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const query = search.toLowerCase();

  // Filter: show a plugin group if the plugin name, step display name, or
  // description contains the query. With the current model (one step per
  // plugin) this effectively filters the whole group at once.
  const visible = query
    ? plugins.filter(
        (p) =>
          p.name.toLowerCase().includes(query) ||
          p.ui.display_name.toLowerCase().includes(query) ||
          p.ui.description?.toLowerCase().includes(query),
      )
    : plugins;

  function toggleCollapse(id: string) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  return (
    <div
      style={{
        width: "230px",
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "8px 12px 6px",
          borderBottom: "1px solid #2A2F38",
          flexShrink: 0,
        }}
      >
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "0.9px",
            color: "#555F6E",
          }}
        >
          STEP TYPES
        </span>
      </div>

      {/* Search bar */}
      <div
        style={{
          padding: "6px 8px",
          borderBottom: "1px solid #2A2F38",
          flexShrink: 0,
        }}
      >
        <div style={{ position: "relative" }}>
          <Search
            size={11}
            style={{
              position: "absolute",
              left: "7px",
              top: "50%",
              transform: "translateY(-50%)",
              color: "#555F6E",
              pointerEvents: "none",
            }}
          />
          <input
            type="text"
            placeholder="Search steps…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              width: "100%",
              backgroundColor: "#0D0F12",
              border: "1px solid #2A2F38",
              borderRadius: "5px",
              color: "#E8EAED",
              fontSize: "11px",
              padding: "5px 24px 5px 24px",
              outline: "none",
              boxSizing: "border-box",
            }}
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              style={{
                position: "absolute",
                right: "6px",
                top: "50%",
                transform: "translateY(-50%)",
                background: "none",
                border: "none",
                color: "#555F6E",
                cursor: "pointer",
                padding: 0,
                display: "flex",
                alignItems: "center",
              }}
            >
              <X size={10} />
            </button>
          )}
        </div>
      </div>

      {/* Plugin groups */}
      <div style={{ flex: 1, overflowY: "auto" }}>
        {plugins.length === 0 ? (
          <div
            style={{
              padding: "16px 12px",
              fontSize: "11px",
              color: "#3A3F48",
              lineHeight: 1.4,
            }}
          >
            No control plugins installed
          </div>
        ) : visible.length === 0 ? (
          <div
            style={{
              padding: "16px 12px",
              fontSize: "11px",
              color: "#3A3F48",
              textAlign: "center",
            }}
          >
            No matching steps
          </div>
        ) : (
          visible.map((p) => {
            const isCollapsed = collapsed.has(p.id);
            return (
              <div key={p.id}>
                {/* Plugin group header */}
                <button
                  onClick={() => toggleCollapse(p.id)}
                  style={{
                    width: "100%",
                    display: "flex",
                    alignItems: "center",
                    gap: "5px",
                    padding: "5px 10px",
                    backgroundColor: "#141619",
                    border: "none",
                    borderBottom: "1px solid #2A2F38",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "background-color 100ms",
                  }}
                  onMouseEnter={(e) => {
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "#1C1F24";
                  }}
                  onMouseLeave={(e) => {
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "#141619";
                  }}
                >
                  {isCollapsed ? (
                    <ChevronRight size={10} color="#555F6E" />
                  ) : (
                    <ChevronDown size={10} color="#555F6E" />
                  )}
                  <span
                    style={{
                      flex: 1,
                      fontSize: "10px",
                      fontWeight: 700,
                      letterSpacing: "0.4px",
                      color: "#8B95A3",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {p.name}
                  </span>
                </button>

                {/* Step type rows — one per plugin for now, but structured for
                    future multi-step-per-plugin support */}
                {!isCollapsed && (
                  <button
                    onClick={() => onAdd(p)}
                    style={{
                      width: "100%",
                      display: "flex",
                      alignItems: "center",
                      gap: "8px",
                      padding: "7px 10px 7px 20px",
                      backgroundColor: "transparent",
                      border: "none",
                      borderBottom: "1px solid #1C1F24",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "background-color 100ms",
                    }}
                    onMouseEnter={(e) => {
                      (
                        e.currentTarget as HTMLButtonElement
                      ).style.backgroundColor = "#1A1D22";
                    }}
                    onMouseLeave={(e) => {
                      (
                        e.currentTarget as HTMLButtonElement
                      ).style.backgroundColor = "transparent";
                    }}
                  >
                    {/* Add icon */}
                    <div
                      style={{
                        width: "18px",
                        height: "18px",
                        borderRadius: "4px",
                        backgroundColor: "#A78BFA18",
                        border: "1px solid #A78BFA44",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                      }}
                    >
                      <Plus size={10} color="#A78BFA" />
                    </div>
                    {/* Step name + description */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: "11px",
                          fontWeight: 600,
                          color: "#E8EAED",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {p.ui.display_name}
                      </div>
                      {p.ui.description && (
                        <div
                          style={{
                            fontSize: "10px",
                            color: "#555F6E",
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                          }}
                        >
                          {p.ui.description}
                        </div>
                      )}
                    </div>
                  </button>
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}

// ── Bottom panel ───────────────────────────────────────────────────────────────

function BottomPanel({
  plugins,
  blocks,
  selectedId,
  onAddBlock,
  onUpdateBlock,
  onClear,
}: {
  plugins: ControlPluginInfo[];
  blocks: MissionBlock[];
  selectedId: string | null;
  onAddBlock: (plugin: ControlPluginInfo) => void;
  onUpdateBlock: (instanceId: string, params: Record<string, unknown>) => void;
  onClear: () => void;
}) {
  const selectedBlock = blocks.find((b) => b.instanceId === selectedId) ?? null;
  const hasFields = selectedBlock
    ? Object.keys(selectedBlock.configSchema).length > 0
    : false;

  function setParam(key: string, val: unknown) {
    if (!selectedBlock) return;
    onUpdateBlock(selectedBlock.instanceId, {
      ...selectedBlock.params,
      [key]: val,
    });
  }

  const divider = (
    <div
      style={{
        width: "1px",
        backgroundColor: "#2A2F38",
        flexShrink: 0,
        alignSelf: "stretch",
      }}
    />
  );

  return (
    <div
      style={{
        position: "absolute",
        bottom: 0,
        left: 0,
        right: 0,
        height: `${BOTTOM_H}px`,
        backgroundColor: "#0D0F12E6",
        backdropFilter: "blur(8px)",
        borderTop: "1px solid #2A2F38",
        display: "flex",
        zIndex: 10,
      }}
    >
      {/* ── Section 1: Available step types ─────────────────────────── */}
      <StepTypesSection plugins={plugins} onAdd={onAddBlock} />

      {divider}

      {/* ── Section 2: Configure selected step ──────────────────────── */}
      <div
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          minWidth: 0,
        }}
      >
        <div
          style={{
            padding: "8px 14px 6px",
            borderBottom: "1px solid #2A2F38",
            display: "flex",
            alignItems: "center",
            gap: "6px",
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.9px",
              color: "#555F6E",
            }}
          >
            CONFIGURE
          </span>
          {selectedBlock && (
            <span
              style={{
                fontSize: "10px",
                color: "#A78BFA",
                fontWeight: 500,
              }}
            >
              — {selectedBlock.displayName}
            </span>
          )}
        </div>

        <div
          style={{
            flex: 1,
            overflowY: "auto",
            padding: "10px 14px",
          }}
        >
          {!selectedBlock ? (
            <div
              style={{
                height: "100%",
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                gap: "8px",
                color: "#3A3F48",
              }}
            >
              <Settings2 size={22} strokeWidth={1.2} />
              <span style={{ fontSize: "11px" }}>
                Select a step to configure
              </span>
            </div>
          ) : !hasFields ? (
            <div
              style={{
                height: "100%",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: "11px",
                color: "#3A3F48",
              }}
            >
              No configuration required
            </div>
          ) : (
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
                gap: "12px",
              }}
            >
              {Object.entries(selectedBlock.configSchema).map(
                ([key, field]) => (
                  <ConfigField
                    key={key}
                    fieldKey={key}
                    field={field}
                    value={selectedBlock.params[key]}
                    onChange={setParam}
                  />
                ),
              )}
            </div>
          )}
        </div>
      </div>

      {divider}

      {/* ── Section 3: Playback controls ────────────────────────────── */}
      <div
        style={{
          width: "140px",
          flexShrink: 0,
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div
          style={{
            padding: "8px 12px 6px",
            borderBottom: "1px solid #2A2F38",
            flexShrink: 0,
          }}
        >
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "0.9px",
              color: "#555F6E",
            }}
          >
            CONTROLS
          </span>
        </div>

        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            alignItems: "stretch",
            justifyContent: "center",
            gap: "8px",
            padding: "12px",
          }}
        >
          {/* Play */}
          <button
            disabled={blocks.length === 0}
            title="Run mission"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "8px",
              borderRadius: "7px",
              border: `1px solid ${blocks.length > 0 ? "#3DD68C55" : "#2A2F38"}`,
              backgroundColor: blocks.length > 0 ? "#3DD68C18" : "#141619",
              color: blocks.length > 0 ? "#3DD68C" : "#3A3F48",
              cursor: blocks.length > 0 ? "pointer" : "default",
              fontSize: "11px",
              fontWeight: 600,
              transition: "all 120ms",
            }}
          >
            <Play size={12} />
            Run Mission
          </button>

          {/* Step forward */}
          <button
            disabled={blocks.length === 0}
            title="Step forward"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "7px",
              borderRadius: "7px",
              border: "1px solid #2A2F38",
              backgroundColor: "#141619",
              color: blocks.length > 0 ? "#8B95A3" : "#3A3F48",
              cursor: blocks.length > 0 ? "pointer" : "default",
              fontSize: "11px",
              fontWeight: 500,
              transition: "all 120ms",
            }}
            onMouseEnter={(e) => {
              if (blocks.length > 0) {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#1C1F24";
                (e.currentTarget as HTMLButtonElement).style.color = "#E8EAED";
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "#141619";
              (e.currentTarget as HTMLButtonElement).style.color =
                blocks.length > 0 ? "#8B95A3" : "#3A3F48";
            }}
          >
            <SkipForward size={12} />
            Step
          </button>

          {/* Clear */}
          <button
            disabled={blocks.length === 0}
            title="Clear all steps"
            onClick={onClear}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "7px",
              borderRadius: "7px",
              border: "1px solid #2A2F38",
              backgroundColor: "transparent",
              color: blocks.length > 0 ? "#F05252" : "#3A3F48",
              cursor: blocks.length > 0 ? "pointer" : "default",
              fontSize: "11px",
              fontWeight: 500,
              transition: "all 120ms",
            }}
            onMouseEnter={(e) => {
              if (blocks.length > 0)
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#F0525210";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "transparent";
            }}
          >
            <X size={12} />
            Clear All
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MissionPage() {
  const hubLocation = useHubLocation();
  const { data: controlPlugins = [] } = useControlPlugins();

  // Map state
  const [map, setMap] = useState<maplibregl.Map | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const [mapBase, setMapBase] = useState<MapBase>("standard");
  const [mapTheme, setMapTheme] = useState<MapTheme>("dark");
  const [savedView, setSavedView] = useState<{
    center: [number, number];
    zoom: number;
  } | null>(null);

  // Mission state
  const [blocks, setBlocks] = useState<MissionBlock[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const handleMapReady = useCallback((m: maplibregl.Map) => {
    mapRef.current = m;
    setMap(m);
  }, []);

  function saveAndSwitch(base: MapBase, theme: MapTheme) {
    if (mapRef.current) {
      const c = mapRef.current.getCenter();
      setSavedView({ center: [c.lng, c.lat], zoom: mapRef.current.getZoom() });
    }
    setMap(null);
    setMapBase(base);
    setMapTheme(theme);
  }

  function addBlock(plugin: ControlPluginInfo) {
    const id = `${plugin.id}-${Date.now()}`;
    setBlocks((prev) => [
      ...prev,
      {
        instanceId: id,
        pluginId: plugin.id,
        displayName: plugin.ui.display_name,
        configSchema: plugin.ui.config_schema ?? {},
        params: defaultParams(plugin.ui.config_schema ?? {}),
      },
    ]);
    setSelectedId(id);
  }

  function updateBlock(instanceId: string, params: Record<string, unknown>) {
    setBlocks((prev) =>
      prev.map((b) => (b.instanceId === instanceId ? { ...b, params } : b)),
    );
  }

  function deleteBlock(instanceId: string) {
    setBlocks((prev) => {
      const next = prev.filter((b) => b.instanceId !== instanceId);
      return next;
    });
    setSelectedId((prev) => (prev === instanceId ? null : prev));
  }

  function moveUp(instanceId: string) {
    setBlocks((prev) => {
      const i = prev.findIndex((b) => b.instanceId === instanceId);
      if (i <= 0) return prev;
      const next = [...prev];
      [next[i - 1], next[i]] = [next[i], next[i - 1]];
      return next;
    });
  }

  function moveDown(instanceId: string) {
    setBlocks((prev) => {
      const i = prev.findIndex((b) => b.instanceId === instanceId);
      if (i < 0 || i >= prev.length - 1) return prev;
      const next = [...prev];
      [next[i], next[i + 1]] = [next[i + 1], next[i]];
      return next;
    });
  }

  function clearAll() {
    setBlocks([]);
    setSelectedId(null);
  }

  const styleKey = `${mapBase}-${mapTheme}`;

  return (
    <div
      style={{
        display: "flex",
        flex: 1,
        overflow: "hidden",
        position: "relative",
      }}
    >
      {/* Map — full background */}
      <div style={{ position: "absolute", inset: 0 }}>
        <MissionMap
          key={styleKey}
          mapBase={mapBase}
          mapTheme={mapTheme}
          initialCenter={savedView?.center}
          initialZoom={savedView?.zoom}
          onMapReady={handleMapReady}
        />
        {map && <NodeMarkers map={map} />}
        {map && <HubMarker map={map} location={hubLocation} />}
      </div>

      {/* Map style picker — top-center of map area */}
      <MapStylePicker
        mapBase={mapBase}
        mapTheme={mapTheme}
        onChangeBase={(base) => saveAndSwitch(base, mapTheme)}
        onChangeTheme={(theme) => saveAndSwitch(mapBase, theme)}
        position="top-center"
      />

      {/* Right panel — ordered step list */}
      <StepListPanel
        blocks={blocks}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onDelete={deleteBlock}
        onMoveUp={moveUp}
        onMoveDown={moveDown}
        plugins={controlPlugins}
      />

      {/* Bottom panel — step types | configure | controls */}
      <BottomPanel
        plugins={controlPlugins}
        blocks={blocks}
        selectedId={selectedId}
        onAddBlock={addBlock}
        onUpdateBlock={updateBlock}
        onClear={clearAll}
      />
    </div>
  );
}
