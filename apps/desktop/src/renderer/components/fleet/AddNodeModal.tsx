import { useState } from "react";
import { X } from "lucide-react";
import { useAddNode } from "../../hooks/useNodes";

interface AddNodeModalProps {
  onClose: () => void;
}

export default function AddNodeModal({ onClose }: AddNodeModalProps) {
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { mutate: addNode, isPending } = useAddNode();

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("Name is required");
      return;
    }

    addNode(
      { name: trimmed, plugin_id: "sim-dummy", config: {} },
      {
        onSuccess: () => onClose(),
        onError: (err) =>
          setError(err instanceof Error ? err.message : "Failed to add device"),
      },
    );
  }

  return (
    // Backdrop
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
      {/* Modal */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "320px",
          backgroundColor: "#1C1F24",
          border: "1px solid #2A2F38",
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
            borderBottom: "1px solid #2A2F38",
          }}
        >
          <span style={{ fontSize: "13px", fontWeight: 600, color: "#E8EAED" }}>
            Add Device
          </span>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: "#8B95A3",
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
            gap: "16px",
          }}
        >
          {/* Plugin badge — locked for now */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{ fontSize: "11px", color: "#8B95A3", fontWeight: 500 }}
            >
              Plugin
            </label>
            <div
              style={{
                padding: "7px 10px",
                backgroundColor: "#141619",
                border: "1px solid #2A2F38",
                borderRadius: "6px",
                fontSize: "12px",
                color: "#8B95A3",
              }}
            >
              sim-dummy — Simulation Node
            </div>
          </div>

          {/* Name */}
          <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
            <label
              style={{ fontSize: "11px", color: "#8B95A3", fontWeight: 500 }}
            >
              Device Name
            </label>
            <input
              autoFocus
              type="text"
              placeholder="e.g. Sim Robot 1"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setError(null);
              }}
              style={{
                padding: "7px 10px",
                backgroundColor: "#141619",
                border: `1px solid ${error ? "#F05252" : "#2A2F38"}`,
                borderRadius: "6px",
                fontSize: "12px",
                color: "#E8EAED",
                outline: "none",
                fontFamily: "Inter, sans-serif",
                userSelect: "text",
              }}
            />
            {error && (
              <span style={{ fontSize: "11px", color: "#F05252" }}>
                {error}
              </span>
            )}
          </div>

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
                border: "1px solid #2A2F38",
                color: "#8B95A3",
                fontSize: "12px",
                cursor: "pointer",
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              style={{
                padding: "7px 14px",
                borderRadius: "6px",
                backgroundColor: isPending ? "#2A2F38" : "#4A9EFF",
                border: "none",
                color: isPending ? "#8B95A3" : "white",
                fontSize: "12px",
                fontWeight: 500,
                cursor: isPending ? "not-allowed" : "pointer",
                transition: "background-color 150ms",
              }}
            >
              {isPending ? "Adding..." : "Add Device"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
