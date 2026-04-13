import { useState } from "react";
import { useCreateZone } from "../../hooks/useZones";
import type { ZoneType } from "../../types";

const ZONE_TYPES: {
  value: ZoneType;
  label: string;
  color: string;
  desc: string;
}[] = [
  {
    value: "perimeter",
    label: "Perimeter",
    color: "#4A9EFF",
    desc: "Operational boundary",
  },
  { value: "no_go", label: "No-Go", color: "#F05252", desc: "Exclusion zone" },
  {
    value: "safe_return",
    label: "Safe Return",
    color: "#3DD68C",
    desc: "Home base zone",
  },
  {
    value: "coverage",
    label: "Coverage",
    color: "#A78BFA",
    desc: "Area to be covered",
  },
  {
    value: "alert",
    label: "Alert",
    color: "#F5A623",
    desc: "Alert on entry/exit",
  },
  {
    value: "custom",
    label: "Custom",
    color: "#999999",
    desc: "Plugin-defined",
  },
];

interface PendingPolygon {
  type: "polygon";
  points: [number, number][];
}
interface PendingCircle {
  type: "circle";
  center: [number, number];
  radiusM: number;
}

interface CreateZoneModalProps {
  shape: PendingPolygon | PendingCircle;
  onClose: () => void;
}

export default function CreateZoneModal({
  shape,
  onClose,
}: CreateZoneModalProps) {
  const [name, setName] = useState("");
  const [zoneType, setZoneType] = useState<ZoneType>("perimeter");
  const [error, setError] = useState<string | null>(null);
  const { mutate: createZone, isPending } = useCreateZone();

  const selectedType = ZONE_TYPES.find((t) => t.value === zoneType)!;

  function handleSubmit() {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Name is required");
      return;
    }

    const body =
      shape.type === "polygon"
        ? {
            name: trimmed,
            zone_type: zoneType,
            color: selectedType.color,
            points: shape.points.map(([lon, lat]) => ({ lat, lon })),
          }
        : {
            name: trimmed,
            zone_type: zoneType,
            color: selectedType.color,
            center: { lat: shape.center[1], lon: shape.center[0] },
            radius_m: shape.radiusM,
          };

    createZone(body, {
      onSuccess: onClose,
      onError: (err) => setError((err as Error).message),
    });
  }

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          zIndex: 20,
          backgroundColor: "rgba(0,0,0,0.5)",
        }}
      />

      {/* Modal */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          zIndex: 21,
          width: "340px",
          backgroundColor: "#1C1C1C",
          border: "1px solid #2D2D2D",
          borderRadius: "10px",
          padding: "20px",
          display: "flex",
          flexDirection: "column",
          gap: "16px",
        }}
      >
        <div style={{ fontSize: "13px", fontWeight: 600, color: "#EFEFEF" }}>
          New Zone
          <span
            style={{ fontWeight: 400, color: "#999999", marginLeft: "8px" }}
          >
            {shape.type === "circle"
              ? `Circle · ${Math.round(shape.radiusM)}m radius`
              : `Polygon · ${shape.points.length} points`}
          </span>
        </div>

        {/* Name */}
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <label style={{ fontSize: "11px", color: "#999999" }}>Name</label>
          <input
            autoFocus
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
            }}
            placeholder="e.g. Search Area Alpha"
            style={{
              background: "#0D0D0D",
              border: "1px solid #2D2D2D",
              borderRadius: "6px",
              color: "#EFEFEF",
              fontSize: "13px",
              padding: "8px 10px",
              outline: "none",
            }}
          />
        </div>

        {/* Zone type */}
        <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
          <label style={{ fontSize: "11px", color: "#999999" }}>Type</label>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: "6px",
            }}
          >
            {ZONE_TYPES.map((t) => (
              <button
                key={t.value}
                onClick={() => setZoneType(t.value)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "7px",
                  padding: "7px 10px",
                  borderRadius: "6px",
                  border: `1px solid ${zoneType === t.value ? t.color : "#2D2D2D"}`,
                  backgroundColor:
                    zoneType === t.value ? `${t.color}18` : "transparent",
                  cursor: "pointer",
                  textAlign: "left",
                }}
              >
                <div
                  style={{
                    width: "8px",
                    height: "8px",
                    borderRadius: "2px",
                    backgroundColor: t.color,
                    flexShrink: 0,
                  }}
                />
                <div>
                  <div
                    style={{
                      fontSize: "11px",
                      fontWeight: 500,
                      color: "#EFEFEF",
                    }}
                  >
                    {t.label}
                  </div>
                  <div style={{ fontSize: "9px", color: "#999999" }}>
                    {t.desc}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {error && (
          <div style={{ fontSize: "11px", color: "#F05252" }}>{error}</div>
        )}

        {/* Actions */}
        <div style={{ display: "flex", gap: "8px" }}>
          <button
            onClick={onClose}
            style={{
              flex: 1,
              padding: "8px 0",
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
            onClick={handleSubmit}
            disabled={isPending}
            style={{
              flex: 1,
              padding: "8px 0",
              borderRadius: "6px",
              backgroundColor: isPending ? "#2D2D2D" : selectedType.color,
              border: "none",
              color: isPending ? "#999999" : "#fff",
              fontSize: "12px",
              fontWeight: 500,
              cursor: isPending ? "not-allowed" : "pointer",
            }}
          >
            {isPending ? "Saving…" : "Create Zone"}
          </button>
        </div>
      </div>
    </>
  );
}
