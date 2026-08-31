import { useState, useRef, useCallback, useEffect } from "react";
import { useNodeStore } from "../stores/nodeStore";
import maplibregl from "maplibre-gl";
import {
  Plus,
  Trash2,
  ArrowUp,
  ArrowDown,
  Play,
  Square,
  SkipForward,
  X,
  Blocks,
  Settings2,
  Search,
  ChevronDown,
  ChevronRight,
  BookmarkPlus,
  FolderOpen,
  Check,
  CheckCircle2,
} from "lucide-react";
import MissionMap, {
  type MapBase,
  type MapTheme,
} from "../components/map/MissionMap";
import MapStylePicker from "../components/map/MapStylePicker";
import HubMarker from "../components/map/HubMarker";
import NodeMarkers from "../components/map/NodeMarkers";
import VICONMap from "../components/map/VICONMap";
import { useHubLocation } from "../hooks/useHubLocation";
import { useViconConnection } from "../hooks/useSystem";
import { useControlPlugins } from "../hooks/usePlugins";
import { useMissionPlans, type MissionPlan } from "../hooks/useMissionPlans";
import { startOperation, stopOperation, getOperations } from "../lib/api";
import { useUIStore } from "../stores/uiStore";
import type { ControlPluginInfo, PluginConfigField } from "../types";

// ── Layout constants ───────────────────────────────────────────────────────────

const BOTTOM_H = 300;
const RIGHT_W = 260;

// ── Data model ─────────────────────────────────────────────────────────────────

export interface MissionBlock {
  instanceId: string;
  pluginId: string;
  label: string; // user-given name (required)
  displayName: string; // step type name from plugin
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

// ── Node selector (live dropdown from connected devices) ───────────────────────

function DeviceSelectField({
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
  const nodes = useNodeStore((s) => Object.values(s.nodes));
  const inputBase: React.CSSProperties = {
    width: "100%",
    backgroundColor: "#0D0D0D",
    border: "1px solid #2D2D2D",
    borderRadius: "5px",
    color: "#EFEFEF",
    fontSize: "11px",
    padding: "5px 8px",
    outline: "none",
    boxSizing: "border-box",
    cursor: "pointer",
  };
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
      <span style={{ fontSize: "10px", color: "#666666" }}>{field.label}</span>
      <select
        value={String(value ?? "")}
        onChange={(e) => onChange(fieldKey, e.target.value)}
        style={inputBase}
      >
        <option value="">Any available robot</option>
        {nodes.map((n) => (
          <option key={n.id} value={n.id}>
            {n.name} ({n.status})
          </option>
        ))}
      </select>
      {field.description && (
        <span style={{ fontSize: "10px", color: "#666666", lineHeight: 1.3 }}>
          {field.description}
        </span>
      )}
    </div>
  );
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
        color: disabled ? "#444444" : danger ? "#F05252" : "#999999",
        cursor: disabled ? "default" : "pointer",
        transition: "background-color 100ms, color 100ms",
        flexShrink: 0,
      }}
      onMouseEnter={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor = danger
            ? "#F0525218"
            : "#1C1C1C";
          if (!danger)
            (e.currentTarget as HTMLButtonElement).style.color = "#EFEFEF";
        }
      }}
      onMouseLeave={(e) => {
        if (!disabled) {
          (e.currentTarget as HTMLButtonElement).style.backgroundColor =
            "transparent";
          (e.currentTarget as HTMLButtonElement).style.color = danger
            ? "#F05252"
            : "#999999";
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
    backgroundColor: "#0D0D0D",
    border: "1px solid #2D2D2D",
    borderRadius: "5px",
    color: "#EFEFEF",
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
          color: "#999999",
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

  if (field.type === "device_select") {
    return (
      <DeviceSelectField
        fieldKey={fieldKey}
        field={field}
        value={value}
        onChange={onChange}
      />
    );
  }

  if (field.type === "select" && field.options) {
    return (
      <div style={{ display: "flex", flexDirection: "column", gap: "3px" }}>
        <span style={{ fontSize: "10px", color: "#666666" }}>
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
      <span style={{ fontSize: "10px", color: "#666666" }}>{field.label}</span>
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
        <span style={{ fontSize: "10px", color: "#666666", lineHeight: 1.3 }}>
          {field.description}
        </span>
      )}
    </div>
  );
}

// ── Plan save popup ────────────────────────────────────────────────────────────

function SavePlanPopup({
  onSave,
  onClose,
}: {
  onSave: (name: string) => void;
  onClose: () => void;
}) {
  const [name, setName] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  function commit() {
    if (!name.trim()) return;
    onSave(name.trim());
    onClose();
  }

  return (
    <div
      style={{
        position: "absolute",
        top: "calc(100% + 6px)",
        right: 0,
        width: "220px",
        backgroundColor: "#141414",
        border: "1px solid #2D2D2D",
        borderRadius: "8px",
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        padding: "10px",
        display: "flex",
        flexDirection: "column",
        gap: "8px",
        zIndex: 50,
      }}
    >
      <span
        style={{
          fontSize: "10px",
          fontWeight: 700,
          letterSpacing: "0.8px",
          color: "#666666",
        }}
      >
        SAVE PLAN AS
      </span>
      <input
        ref={inputRef}
        type="text"
        value={name}
        onChange={(e) => setName(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") commit();
          if (e.key === "Escape") onClose();
        }}
        placeholder="Plan name…"
        style={{
          backgroundColor: "#0D0D0D",
          border: "1px solid #2D2D2D",
          borderRadius: "5px",
          color: "#EFEFEF",
          fontSize: "12px",
          padding: "6px 8px",
          outline: "none",
        }}
      />
      <div style={{ display: "flex", gap: "6px" }}>
        <button
          onClick={onClose}
          style={{
            flex: 1,
            padding: "6px",
            borderRadius: "5px",
            border: "1px solid #2D2D2D",
            backgroundColor: "transparent",
            color: "#999999",
            fontSize: "11px",
            cursor: "pointer",
          }}
        >
          Cancel
        </button>
        <button
          onClick={commit}
          disabled={!name.trim()}
          style={{
            flex: 1,
            padding: "6px",
            borderRadius: "5px",
            border: `1px solid ${name.trim() ? "#A78BFA55" : "#2D2D2D"}`,
            backgroundColor: name.trim() ? "#A78BFA18" : "transparent",
            color: name.trim() ? "#A78BFA" : "#444444",
            fontSize: "11px",
            fontWeight: 600,
            cursor: name.trim() ? "pointer" : "default",
          }}
        >
          Save
        </button>
      </div>
    </div>
  );
}

// ── Plan open popup ────────────────────────────────────────────────────────────

function OpenPlanPopup({
  plans,
  onLoad,
  onDelete,
  onClose,
}: {
  plans: MissionPlan[];
  onLoad: (plan: MissionPlan) => void;
  onDelete: (id: string) => void;
  onClose: () => void;
}) {
  const [confirmId, setConfirmId] = useState<string | null>(null);

  function formatDate(iso: string) {
    const d = new Date(iso);
    return (
      d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      }) +
      " · " +
      d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
    );
  }

  return (
    <div
      style={{
        position: "absolute",
        top: "calc(100% + 6px)",
        right: 0,
        width: "260px",
        backgroundColor: "#141414",
        border: "1px solid #2D2D2D",
        borderRadius: "8px",
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        zIndex: 50,
        overflow: "hidden",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "9px 12px",
          borderBottom: "1px solid #2D2D2D",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "0.8px",
            color: "#666666",
          }}
        >
          SAVED PLANS
        </span>
        <button
          onClick={onClose}
          style={{
            background: "none",
            border: "none",
            color: "#666666",
            cursor: "pointer",
            display: "flex",
            padding: 0,
          }}
        >
          <X size={12} />
        </button>
      </div>

      {/* List */}
      <div style={{ maxHeight: "320px", overflowY: "auto" }}>
        {plans.length === 0 ? (
          <div
            style={{
              padding: "24px 16px",
              textAlign: "center",
              fontSize: "12px",
              color: "#666666",
              lineHeight: 1.5,
            }}
          >
            No saved plans yet.
            <br />
            Use Save As to create one.
          </div>
        ) : (
          plans.map((plan) => {
            const isConfirming = confirmId === plan.id;
            return (
              <div
                key={plan.id}
                style={{
                  padding: "10px 12px",
                  borderBottom: "1px solid #1C1C1C",
                  display: "flex",
                  alignItems: "center",
                  gap: "8px",
                }}
              >
                {isConfirming ? (
                  <div
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      gap: "6px",
                    }}
                  >
                    <span
                      style={{
                        flex: 1,
                        fontSize: "11px",
                        color: "#999999",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      Delete "{plan.name}"?
                    </span>
                    <button
                      onClick={() => setConfirmId(null)}
                      style={{
                        fontSize: "10px",
                        padding: "2px 7px",
                        borderRadius: "4px",
                        border: "1px solid #2D2D2D",
                        backgroundColor: "transparent",
                        color: "#999999",
                        cursor: "pointer",
                        flexShrink: 0,
                      }}
                    >
                      Cancel
                    </button>
                    <button
                      onClick={() => {
                        onDelete(plan.id);
                        setConfirmId(null);
                      }}
                      style={{
                        fontSize: "10px",
                        padding: "2px 7px",
                        borderRadius: "4px",
                        border: "1px solid #F05252",
                        backgroundColor: "#F0525222",
                        color: "#F05252",
                        cursor: "pointer",
                        flexShrink: 0,
                      }}
                    >
                      Delete
                    </button>
                  </div>
                ) : (
                  <>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: "12px",
                          fontWeight: 600,
                          color: "#EFEFEF",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {plan.name}
                      </div>
                      <div
                        style={{
                          fontSize: "10px",
                          color: "#666666",
                          marginTop: "2px",
                        }}
                      >
                        {formatDate(plan.savedAt)}
                      </div>
                      <div
                        style={{
                          fontSize: "10px",
                          color: "#444444",
                          marginTop: "1px",
                        }}
                      >
                        {plan.blocks.length} step
                        {plan.blocks.length !== 1 ? "s" : ""}
                      </div>
                    </div>
                    <div style={{ display: "flex", gap: "2px", flexShrink: 0 }}>
                      <button
                        onClick={() => {
                          onLoad(plan);
                          onClose();
                        }}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          gap: "4px",
                          padding: "4px 8px",
                          borderRadius: "5px",
                          border: "1px solid #2D2D2D",
                          backgroundColor: "transparent",
                          color: "#999999",
                          fontSize: "11px",
                          cursor: "pointer",
                          transition: "all 100ms",
                        }}
                        onMouseEnter={(e) => {
                          (
                            e.currentTarget as HTMLButtonElement
                          ).style.backgroundColor = "#1C1C1C";
                          (e.currentTarget as HTMLButtonElement).style.color =
                            "#EFEFEF";
                        }}
                        onMouseLeave={(e) => {
                          (
                            e.currentTarget as HTMLButtonElement
                          ).style.backgroundColor = "transparent";
                          (e.currentTarget as HTMLButtonElement).style.color =
                            "#999999";
                        }}
                      >
                        <Check size={11} />
                        Load
                      </button>
                      <button
                        onClick={() => setConfirmId(plan.id)}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: "26px",
                          height: "26px",
                          borderRadius: "5px",
                          border: "none",
                          backgroundColor: "transparent",
                          color: "#999999",
                          cursor: "pointer",
                          transition: "all 100ms",
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.color =
                            "#F05252";
                          (
                            e.currentTarget as HTMLButtonElement
                          ).style.backgroundColor = "#F0525210";
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLButtonElement).style.color =
                            "#999999";
                          (
                            e.currentTarget as HTMLButtonElement
                          ).style.backgroundColor = "transparent";
                        }}
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })
        )}
      </div>
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
  plans,
  onSavePlan,
  onLoadPlan,
  onDeletePlan,
  isRunning,
  activeStepIndex,
}: {
  blocks: MissionBlock[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onMoveUp: (id: string) => void;
  onMoveDown: (id: string) => void;
  plugins: ControlPluginInfo[];
  plans: MissionPlan[];
  onSavePlan: (name: string) => void;
  onLoadPlan: (plan: MissionPlan) => void;
  onDeletePlan: (id: string) => void;
  isRunning: boolean;
  activeStepIndex: number;
}) {
  const [activePopup, setActivePopup] = useState<"save" | "open" | null>(null);
  const popupAnchorRef = useRef<HTMLDivElement>(null);

  // Close popup on outside click
  useEffect(() => {
    if (!activePopup) return;
    function onDown(e: MouseEvent) {
      if (
        popupAnchorRef.current &&
        !popupAnchorRef.current.contains(e.target as Node)
      ) {
        setActivePopup(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [activePopup]);

  return (
    <div
      style={{
        position: "absolute",
        top: 0,
        right: 0,
        width: `${RIGHT_W}px`,
        height: "100%",
        backgroundColor: "#141414",
        borderLeft: "1px solid #2D2D2D",
        borderBottom: "1px solid #2D2D2D",
        display: "flex",
        flexDirection: "column",
        zIndex: 10,
      }}
    >
      {/* Header */}
      <div
        style={{
          height: "36px",
          padding: "0 8px 0 12px",
          backgroundColor: "#0D0D0D",
          borderBottom: "1px solid #2D2D2D",
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
          gap: "6px",
        }}
      >
        <span
          style={{
            flex: 1,
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "1.2px",
            color: isRunning ? "#3DD68C" : "#666666",
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}
        >
          {isRunning && (
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "#3DD68C",
                flexShrink: 0,
                animation: "pulse-dot 1.2s ease-in-out infinite",
              }}
            />
          )}
          {isRunning
            ? `STEP ${activeStepIndex + 1} / ${blocks.length}`
            : "MISSION PLAN"}
        </span>

        {/* Save / Open buttons — hidden while running */}
        <div
          ref={popupAnchorRef}
          style={{
            position: "relative",
            display: isRunning ? "none" : "flex",
            gap: "1px",
          }}
        >
          <button
            title="Save plan as…"
            disabled={blocks.length === 0}
            onClick={() =>
              setActivePopup(activePopup === "save" ? null : "save")
            }
            style={{
              width: "26px",
              height: "26px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "5px",
              border: `1px solid ${activePopup === "save" ? "#A78BFA" : "transparent"}`,
              backgroundColor:
                activePopup === "save" ? "#A78BFA18" : "transparent",
              color:
                blocks.length === 0
                  ? "#444444"
                  : activePopup === "save"
                    ? "#A78BFA"
                    : "#999999",
              cursor: blocks.length === 0 ? "default" : "pointer",
              transition: "all 150ms",
            }}
            onMouseEnter={(e) => {
              if (blocks.length > 0 && activePopup !== "save") {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#1C1C1C";
                (e.currentTarget as HTMLButtonElement).style.color = "#EFEFEF";
              }
            }}
            onMouseLeave={(e) => {
              if (activePopup !== "save") {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "transparent";
                (e.currentTarget as HTMLButtonElement).style.color =
                  blocks.length === 0 ? "#444444" : "#999999";
              }
            }}
          >
            <BookmarkPlus size={13} />
          </button>
          <button
            title="Open saved plan"
            onClick={() =>
              setActivePopup(activePopup === "open" ? null : "open")
            }
            style={{
              width: "26px",
              height: "26px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "5px",
              border: `1px solid ${activePopup === "open" ? "#A78BFA" : "transparent"}`,
              backgroundColor:
                activePopup === "open" ? "#A78BFA18" : "transparent",
              color: activePopup === "open" ? "#A78BFA" : "#999999",
              cursor: "pointer",
              transition: "all 150ms",
            }}
            onMouseEnter={(e) => {
              if (activePopup !== "open") {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#1C1C1C";
                (e.currentTarget as HTMLButtonElement).style.color = "#EFEFEF";
              }
            }}
            onMouseLeave={(e) => {
              if (activePopup !== "open") {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "transparent";
                (e.currentTarget as HTMLButtonElement).style.color = "#999999";
              }
            }}
          >
            <FolderOpen size={13} />
          </button>

          {activePopup === "save" && (
            <SavePlanPopup
              onSave={onSavePlan}
              onClose={() => setActivePopup(null)}
            />
          )}
          {activePopup === "open" && (
            <OpenPlanPopup
              plans={plans}
              onLoad={onLoadPlan}
              onDelete={onDeletePlan}
              onClose={() => setActivePopup(null)}
            />
          )}
        </div>
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
              color: "#444444",
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
            const isActive = isRunning && i === activeStepIndex;
            const isDone = isRunning && i < activeStepIndex;
            const isPending = isRunning && i > activeStepIndex;
            const selected = !isRunning && block.instanceId === selectedId;

            const accentColor = isActive
              ? "#3DD68C"
              : isDone
                ? "#3DD68C55"
                : selected
                  ? "#A78BFA"
                  : "#444444";
            const cardBg = isActive
              ? "#3DD68C0A"
              : isDone
                ? "#141414"
                : selected
                  ? "#A78BFA0D"
                  : "#141414";
            const cardBorder = isActive
              ? "#3DD68C55"
              : isDone
                ? "#2D2D2D"
                : selected
                  ? "#A78BFA55"
                  : "#2D2D2D";
            const labelColor = isActive
              ? "#EFEFEF"
              : isDone
                ? "#666666"
                : selected
                  ? "#EFEFEF"
                  : "#CCCCCC";
            const subColor = isActive
              ? "#3DD68C"
              : isDone
                ? "#444444"
                : selected
                  ? "#A78BFA"
                  : "#666666";

            return (
              <div
                key={block.instanceId}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "7px",
                  flexShrink: 0,
                  opacity: isPending ? 0.45 : 1,
                  transition: "opacity 200ms",
                }}
              >
                {/* Step number / done indicator — outside the card */}
                <div
                  style={{
                    width: "20px",
                    height: "20px",
                    borderRadius: "50%",
                    backgroundColor: isActive
                      ? "#3DD68C22"
                      : isDone
                        ? "#3DD68C18"
                        : selected
                          ? "#A78BFA22"
                          : "#1C1C1C",
                    border: `1px solid ${isActive ? "#3DD68C" : isDone ? "#3DD68C55" : selected ? "#A78BFA" : "#444444"}`,
                    color: isActive
                      ? "#3DD68C"
                      : isDone
                        ? "#3DD68C"
                        : selected
                          ? "#A78BFA"
                          : "#666666",
                    fontSize: "9px",
                    fontWeight: 700,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    flexShrink: 0,
                    transition: "all 200ms",
                  }}
                >
                  {isDone ? <CheckCircle2 size={11} /> : i + 1}
                </div>

                {/* Card */}
                <div
                  onClick={() => !isRunning && onSelect(block.instanceId)}
                  style={{
                    flex: 1,
                    display: "flex",
                    alignItems: "center",
                    backgroundColor: cardBg,
                    border: `1px solid ${cardBorder}`,
                    borderRadius: "7px",
                    overflow: "hidden",
                    cursor: isRunning ? "default" : "pointer",
                    transition: "all 200ms",
                    minWidth: 0,
                    boxShadow: isActive ? "0 0 0 1px #3DD68C33" : "none",
                  }}
                >
                  {/* Left accent */}
                  <div
                    style={{
                      width: "3px",
                      alignSelf: "stretch",
                      backgroundColor: accentColor,
                      flexShrink: 0,
                      transition: "background-color 200ms",
                    }}
                  />
                  {/* Text content */}
                  <div
                    style={{
                      flex: 1,
                      padding: "7px 8px",
                      minWidth: 0,
                    }}
                  >
                    <div
                      style={{
                        fontSize: "12px",
                        fontWeight: 600,
                        color: labelColor,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        transition: "color 200ms",
                      }}
                    >
                      {block.label}
                    </div>
                    <div
                      style={{
                        fontSize: "10px",
                        color: subColor,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        marginTop: "1px",
                        transition: "color 200ms",
                      }}
                    >
                      {isActive
                        ? "● Running…"
                        : isDone
                          ? "✓ Complete"
                          : block.displayName}
                    </div>
                  </div>
                  {/* Reorder + delete — hidden while running */}
                  {!isRunning && (
                    <div
                      style={{
                        display: "flex",
                        gap: "1px",
                        flexShrink: 0,
                        paddingRight: "2px",
                      }}
                    >
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
                  )}
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
          height: "36px",
          padding: "0 12px",
          backgroundColor: "#0D0D0D",
          borderBottom: "1px solid #2D2D2D",
          flexShrink: 0,
          display: "flex",
          alignItems: "center",
        }}
      >
        <span
          style={{
            fontSize: "10px",
            fontWeight: 700,
            letterSpacing: "0.9px",
            color: "#666666",
          }}
        >
          STEP TYPES
        </span>
      </div>

      {/* Search bar */}
      <div
        style={{
          padding: "6px 8px",
          borderBottom: "1px solid #2D2D2D",
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
              color: "#666666",
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
              backgroundColor: "#0D0D0D",
              border: "1px solid #2D2D2D",
              borderRadius: "5px",
              color: "#EFEFEF",
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
                color: "#666666",
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
              color: "#444444",
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
              color: "#444444",
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
                    backgroundColor: "#141414",
                    border: "none",
                    borderBottom: "1px solid #2D2D2D",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "background-color 100ms",
                  }}
                  onMouseEnter={(e) => {
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "#1C1C1C";
                  }}
                  onMouseLeave={(e) => {
                    (
                      e.currentTarget as HTMLButtonElement
                    ).style.backgroundColor = "#141414";
                  }}
                >
                  {isCollapsed ? (
                    <ChevronRight size={10} color="#666666" />
                  ) : (
                    <ChevronDown size={10} color="#666666" />
                  )}
                  <span
                    style={{
                      flex: 1,
                      fontSize: "10px",
                      fontWeight: 700,
                      letterSpacing: "0.4px",
                      color: "#999999",
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
                      borderBottom: "1px solid #1C1C1C",
                      cursor: "pointer",
                      textAlign: "left",
                      transition: "background-color 100ms",
                    }}
                    onMouseEnter={(e) => {
                      (
                        e.currentTarget as HTMLButtonElement
                      ).style.backgroundColor = "#191919";
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
                    {/* Step name */}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div
                        style={{
                          fontSize: "11px",
                          fontWeight: 600,
                          color: "#EFEFEF",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                      >
                        {p.ui.display_name}
                      </div>
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
  onRenameBlock,
}: {
  plugins: ControlPluginInfo[];
  blocks: MissionBlock[];
  selectedId: string | null;
  onAddBlock: (plugin: ControlPluginInfo) => void;
  onUpdateBlock: (instanceId: string, params: Record<string, unknown>) => void;
  onRenameBlock: (instanceId: string, label: string) => void;
}) {
  const selectedBlock = blocks.find((b) => b.instanceId === selectedId) ?? null;
  const selectedPlugin = selectedBlock
    ? (plugins.find((p) => p.id === selectedBlock.pluginId) ?? null)
    : null;
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
        backgroundColor: "#2D2D2D",
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
        right: `${RIGHT_W}px`,
        height: `${BOTTOM_H}px`,
        backgroundColor: "#141414",
        borderTop: "1px solid #2D2D2D",
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
            height: "36px",
            padding: "0 14px",
            backgroundColor: "#0D0D0D",
            borderBottom: "1px solid #2D2D2D",
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
              color: "#666666",
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
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              — {selectedBlock.label}
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
                color: "#444444",
              }}
            >
              <Settings2 size={22} strokeWidth={1.2} />
              <span style={{ fontSize: "11px" }}>
                Select a step to configure
              </span>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: "0" }}>
              {/* Step name — distinct section */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "10px",
                  padding: "10px 14px",
                  backgroundColor: "#0D0D0D",
                  borderBottom: "1px solid #2D2D2D",
                  flexShrink: 0,
                }}
              >
                <span
                  style={{ fontSize: "11px", color: "#666666", flexShrink: 0 }}
                >
                  Name
                </span>
                <input
                  value={selectedBlock.label}
                  onChange={(e) =>
                    onRenameBlock(selectedBlock.instanceId, e.target.value)
                  }
                  style={{
                    width: "180px",
                    padding: "5px 9px",
                    backgroundColor: "#141414",
                    border: "1px solid #2D2D2D",
                    borderRadius: "5px",
                    color: "#EFEFEF",
                    fontSize: "12px",
                    fontWeight: 500,
                    outline: "none",
                  }}
                />
              </div>

              {/* Plugin params */}
              {hasFields ? (
                <div
                  style={{
                    padding: "12px 14px",
                    display: "grid",
                    gridTemplateColumns:
                      "repeat(auto-fill, minmax(180px, 1fr))",
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
              ) : (
                <div
                  style={{
                    padding: "16px 14px",
                    fontSize: "11px",
                    color: "#444444",
                  }}
                >
                  No additional configuration required
                </div>
              )}

              {/* Step description */}
              {selectedPlugin?.ui.description && (
                <div
                  style={{
                    padding: "10px 14px",
                    borderTop: "1px solid #2D2D2D",
                    fontSize: "11px",
                    color: "#666666",
                    lineHeight: 1.5,
                    fontStyle: "italic",
                  }}
                >
                  {selectedPlugin.ui.description}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Controls panel — floating top-left ────────────────────────────────────────

function ControlsPanel({
  blocks,
  onClear,
  isRunning,
  onRun,
  onStop,
}: {
  blocks: MissionBlock[];
  onClear: () => void;
  isRunning: boolean;
  onRun: () => void;
  onStop: () => void;
}) {
  const hasBlocks = blocks.length > 0;
  return (
    <div
      style={{
        position: "absolute",
        top: "10px",
        left: "10px",
        zIndex: 20,
        backgroundColor: "#141414",
        border: `1px solid ${isRunning ? "#3DD68C33" : "#2D2D2D"}`,
        borderRadius: "8px",
        display: "flex",
        flexDirection: "column",
        gap: "6px",
        padding: "8px",
        minWidth: "130px",
        transition: "border-color 200ms",
      }}
    >
      {isRunning ? (
        /* ── Running state ── */
        <>
          {/* Running indicator */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "4px 8px",
              fontSize: "10px",
              fontWeight: 700,
              color: "#3DD68C",
              letterSpacing: "0.8px",
            }}
          >
            <span
              style={{
                width: "6px",
                height: "6px",
                borderRadius: "50%",
                backgroundColor: "#3DD68C",
                animation: "pulse-dot 1.2s ease-in-out infinite",
                flexShrink: 0,
              }}
            />
            RUNNING
          </div>

          {/* Stop button */}
          <button
            onClick={onStop}
            title="Stop mission"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "8px",
              borderRadius: "6px",
              border: "1px solid #F0525255",
              backgroundColor: "#F0525218",
              color: "#F05252",
              cursor: "pointer",
              fontSize: "11px",
              fontWeight: 600,
              transition: "all 120ms",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "#F0525230";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "#F0525218";
            }}
          >
            <Square size={11} />
            Stop Mission
          </button>
        </>
      ) : (
        /* ── Edit state ── */
        <>
          {/* Run Mission */}
          <button
            disabled={!hasBlocks}
            title="Run mission"
            onClick={hasBlocks ? onRun : undefined}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "8px",
              borderRadius: "6px",
              border: `1px solid ${hasBlocks ? "#3DD68C55" : "#2D2D2D"}`,
              backgroundColor: hasBlocks ? "#3DD68C18" : "#141414",
              color: hasBlocks ? "#3DD68C" : "#444444",
              cursor: hasBlocks ? "pointer" : "default",
              fontSize: "11px",
              fontWeight: 600,
              transition: "all 120ms",
            }}
            onMouseEnter={(e) => {
              if (hasBlocks)
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#3DD68C28";
            }}
            onMouseLeave={(e) => {
              if (hasBlocks)
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#3DD68C18";
            }}
          >
            <Play size={12} />
            Run Mission
          </button>

          {/* Step forward */}
          <button
            disabled={!hasBlocks}
            title="Step forward"
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "7px",
              borderRadius: "6px",
              border: "1px solid #2D2D2D",
              backgroundColor: "#141414",
              color: hasBlocks ? "#999999" : "#444444",
              cursor: hasBlocks ? "pointer" : "default",
              fontSize: "11px",
              fontWeight: 500,
              transition: "all 120ms",
            }}
            onMouseEnter={(e) => {
              if (hasBlocks) {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#1C1C1C";
                (e.currentTarget as HTMLButtonElement).style.color = "#EFEFEF";
              }
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                "#141414";
              (e.currentTarget as HTMLButtonElement).style.color = hasBlocks
                ? "#999999"
                : "#444444";
            }}
          >
            <SkipForward size={12} />
            Step
          </button>

          {/* Clear all */}
          <button
            disabled={!hasBlocks}
            title="Clear all steps"
            onClick={onClear}
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "6px",
              padding: "7px",
              borderRadius: "6px",
              border: "1px solid #2D2D2D",
              backgroundColor: "transparent",
              color: hasBlocks ? "#F05252" : "#444444",
              cursor: hasBlocks ? "pointer" : "default",
              fontSize: "11px",
              fontWeight: 500,
              transition: "all 120ms",
            }}
            onMouseEnter={(e) => {
              if (hasBlocks)
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
        </>
      )}
    </div>
  );
}

// ── Page ───────────────────────────────────────────────────────────────────────

export default function MissionPage() {
  const hubLocation = useHubLocation();
  const { data: controlPlugins = [] } = useControlPlugins();
  const { data: viconConn } = useViconConnection();
  const { mapMode, setMapMode, viconSpace } = useUIStore((s) => ({
    mapMode: s.mapMode,
    setMapMode: s.setMapMode,
    viconSpace: s.viconSpace,
  }));

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

  // Execution state
  const [isRunning, setIsRunning] = useState(false);
  const [activeStepIndex, setActiveStepIndex] = useState(0);
  const stopRequestedRef = useRef(false);
  const activeBlockRef = useRef<MissionBlock | null>(null);

  async function startMission() {
    if (blocks.length === 0) return;
    stopRequestedRef.current = false;
    setActiveStepIndex(0);
    setIsRunning(true);
    setSelectedId(null);

    for (let i = 0; i < blocks.length; i++) {
      if (stopRequestedRef.current) break;

      const block = blocks[i];
      setActiveStepIndex(i);
      activeBlockRef.current = block;

      try {
        await startOperation(
          block.pluginId,
          block.params as Record<string, unknown>,
        );
      } catch (err) {
        console.error(`[Mission] Failed to start step ${i + 1}:`, err);
        break;
      }

      // Poll until operation reaches a terminal state
      let done = false;
      while (!done && !stopRequestedRef.current) {
        await new Promise<void>((r) => setTimeout(r, 500));
        try {
          const ops = await getOperations();
          const op = ops.find((o) => o.plugin_id === block.pluginId);
          if (!op) {
            done = true;
          } else {
            const s = op.status.state as string;
            if (s === "completed" || s === "failed" || s === "idle") {
              done = true;
            }
          }
        } catch {
          done = true;
        }
      }

      if (stopRequestedRef.current) break;
    }

    activeBlockRef.current = null;
    setIsRunning(false);
    setActiveStepIndex(0);
  }

  function stopMission() {
    stopRequestedRef.current = true;
    const block = activeBlockRef.current;
    if (block) {
      stopOperation(block.pluginId).catch(() => {});
    }
    setIsRunning(false);
    setActiveStepIndex(0);
  }

  // Saved plans
  const { plans, save: savePlan, remove: deletePlan } = useMissionPlans();

  function handleSavePlan(name: string) {
    savePlan(name, blocks);
  }

  function handleLoadPlan(plan: MissionPlan) {
    setBlocks(plan.blocks);
    setSelectedId(null);
  }

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
    setBlocks((prev) => {
      const stepNum = prev.length + 1;
      return [
        ...prev,
        {
          instanceId: id,
          pluginId: plugin.id,
          label: `Step ${stepNum}`,
          displayName: plugin.ui.display_name,
          configSchema: plugin.ui.config_schema ?? {},
          params: defaultParams(plugin.ui.config_schema ?? {}),
        },
      ];
    });
    setSelectedId(id);
  }

  function updateBlock(instanceId: string, params: Record<string, unknown>) {
    setBlocks((prev) =>
      prev.map((b) => (b.instanceId === instanceId ? { ...b, params } : b)),
    );
  }

  function renameBlock(instanceId: string, label: string) {
    setBlocks((prev) =>
      prev.map((b) => (b.instanceId === instanceId ? { ...b, label } : b)),
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
      {/* Map — full background (always mounted to avoid WebGL teardown) */}
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

      {/* VICON overlay — covers GPS map when in VICON mode */}
      <div
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 2,
          backgroundColor: "#0D0D0D",
          display: mapMode === "vicon" ? "flex" : "none",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {viconSpace ? (
          <VICONMap
            space={viconSpace}
            homeLat={viconConn?.home_lat}
            homeLon={viconConn?.home_lon}
          />
        ) : (
          <div style={{ color: "#8B95A3", fontSize: 13 }}>
            VICON space not configured — set it up on the Home page
          </div>
        )}
      </div>

      {/* GPS / VICON mode toggle — top-left */}
      <div
        style={{
          position: "absolute",
          top: 12,
          left: 12,
          zIndex: 20,
          display: "flex",
          background: "#1C1F24",
          border: "1px solid #2A2F38",
          borderRadius: 6,
          overflow: "hidden",
        }}
      >
        {(["gps", "vicon"] as const).map((m) => (
          <button
            key={m}
            onClick={() => setMapMode(m)}
            style={{
              padding: "5px 12px",
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: "0.5px",
              cursor: "pointer",
              border: "none",
              background: mapMode === m ? "#4A9EFF" : "transparent",
              color: mapMode === m ? "#fff" : "#8B95A3",
              textTransform: "uppercase",
              transition: "background 150ms ease, color 150ms ease",
            }}
          >
            {m}
          </button>
        ))}
      </div>

      {/* Map style picker — top-center, with hub button (GPS mode only) */}
      {mapMode === "gps" && (
        <MapStylePicker
          mapBase={mapBase}
          mapTheme={mapTheme}
          onChangeBase={(base) => saveAndSwitch(base, mapTheme)}
          onChangeTheme={(theme) => saveAndSwitch(mapBase, theme)}
          position="top-center"
          onCenterHub={() => {
            if (mapRef.current && hubLocation)
              mapRef.current.flyTo({
                center: hubLocation,
                zoom: 15,
                duration: 1000,
              });
          }}
        />
      )}

      {/* Controls — floating top-left */}
      <ControlsPanel
        blocks={blocks}
        onClear={clearAll}
        isRunning={isRunning}
        onRun={startMission}
        onStop={stopMission}
      />

      {/* Right panel — ordered step list, full height */}
      <StepListPanel
        blocks={blocks}
        selectedId={selectedId}
        onSelect={setSelectedId}
        onDelete={deleteBlock}
        onMoveUp={moveUp}
        onMoveDown={moveDown}
        plugins={controlPlugins}
        plans={plans}
        onSavePlan={handleSavePlan}
        onLoadPlan={handleLoadPlan}
        onDeletePlan={deletePlan}
        isRunning={isRunning}
        activeStepIndex={activeStepIndex}
      />

      {/* Bottom panel — hidden while mission is running */}
      {!isRunning && (
        <BottomPanel
          plugins={controlPlugins}
          blocks={blocks}
          selectedId={selectedId}
          onAddBlock={addBlock}
          onUpdateBlock={updateBlock}
          onRenameBlock={renameBlock}
        />
      )}
    </div>
  );
}
