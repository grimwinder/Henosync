import { useNodeStore } from "../../stores/nodeStore";
import type { PluginConfigField } from "../../types";

export const fieldStyle: React.CSSProperties = {
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

export function initConfig(
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

function DeviceSelectField({
  fieldKey,
  value,
  onChange,
}: {
  fieldKey: string;
  value: unknown;
  onChange: (k: string, v: unknown) => void;
}) {
  const nodes = useNodeStore((s) => Object.values(s.nodes));
  return (
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
      <option value="">Any available robot</option>
      {nodes.map((n) => (
        <option key={n.id} value={n.id}>
          {n.name} ({n.status})
        </option>
      ))}
    </select>
  );
}

export function ConfigField({
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

      {field.type === "device_select" && (
        <DeviceSelectField fieldKey={fieldKey} value={value} onChange={onChange} />
      )}

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
