import { useEffect, useState } from "react";
import { X, FileSpreadsheet, FolderOpen, Trash2 } from "lucide-react";
import { getRuns, deleteRun } from "../../lib/api";
import type { MissionRun, RunOutcome } from "../../types";

const POLL_MS = 2000;

const OUTCOME_COLOR: Record<RunOutcome, string> = {
  running: "#4A9EFF",
  completed: "#3DD68C",
  stopped: "#F5A623",
  failed: "#F05252",
  interrupted: "#F5A623",
  incomplete: "#8B95A3",
};

function fmtDate(epoch: number) {
  const d = new Date(epoch * 1000);
  return (
    d.toLocaleDateString(undefined, {
      day: "numeric",
      month: "short",
      year: "numeric",
    }) +
    " · " +
    d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })
  );
}

/** Opens the run's CSV file directly. */
export async function openRunCsv(csvPath: string) {
  const err = await window.henosync?.shell.openPath(csvPath);
  if (err) throw new Error(err);
}

const btn: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: "5px",
  padding: "4px 8px",
  borderRadius: "5px",
  border: "1px solid #2D2D2D",
  backgroundColor: "#141414",
  color: "#CCCCCC",
  fontSize: "11px",
  cursor: "pointer",
};

/** Lists recorded mission runs with CSV open, open folder and delete. */
export default function RunsDialog({ onClose }: { onClose: () => void }) {
  const [runs, setRuns] = useState<MissionRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      getRuns()
        .then((r) => {
          if (alive) {
            setRuns(r);
            setError(null);
          }
        })
        .catch((e: Error) => alive && setError(e.message));
    load();
    const t = setInterval(load, POLL_MS);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  async function handleOpenCsv(run: MissionRun) {
    try {
      await openRunCsv(run.csv_path);
    } catch (e) {
      setNotice(`Could not open CSV: ${(e as Error).message}`);
    }
  }

  async function handleDelete(run: MissionRun) {
    if (confirmDelete !== run.id) {
      setConfirmDelete(run.id);
      return;
    }
    setConfirmDelete(null);
    try {
      await deleteRun(run.id);
      setRuns((prev) => prev.filter((r) => r.id !== run.id));
    } catch (e) {
      setNotice(`Delete failed: ${(e as Error).message}`);
    }
  }

  return (
    <div
      onMouseDown={onClose}
      style={{
        position: "absolute",
        inset: 0,
        zIndex: 60,
        backgroundColor: "rgba(0,0,0,0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        onMouseDown={(e) => e.stopPropagation()}
        style={{
          width: "min(860px, 92%)",
          maxHeight: "80%",
          display: "flex",
          flexDirection: "column",
          backgroundColor: "#141414",
          border: "1px solid #2D2D2D",
          borderRadius: "8px",
          boxShadow: "0 12px 32px rgba(0,0,0,0.6)",
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
            gap: "10px",
            padding: "0 12px",
            backgroundColor: "#0D0D0D",
            borderBottom: "1px solid #2D2D2D",
          }}
        >
          <span
            style={{
              fontSize: "10px",
              fontWeight: 700,
              letterSpacing: "1px",
              color: "#666666",
            }}
          >
            MISSION RUNS
          </span>
          <span style={{ flex: 1, fontSize: "10px", color: "#555555" }}>
            CSV logs saved to ~/Downloads
          </span>
          <button
            onClick={onClose}
            title="Close"
            style={{
              background: "none",
              border: "none",
              color: "#666666",
              cursor: "pointer",
              display: "flex",
              padding: 0,
            }}
          >
            <X size={13} />
          </button>
        </div>

        {(notice || error) && (
          <div
            style={{
              padding: "6px 12px",
              fontSize: "11px",
              color: error ? "#F05252" : "#8B95A3",
              borderBottom: "1px solid #2D2D2D",
              overflowWrap: "anywhere",
            }}
          >
            {error ? `Could not load runs: ${error}` : notice}
          </div>
        )}

        {/* List */}
        <div style={{ overflowY: "auto", flex: 1 }}>
          {runs.length === 0 && !error ? (
            <div
              style={{
                padding: "28px 16px",
                textAlign: "center",
                fontSize: "11px",
                color: "#555555",
              }}
            >
              No runs yet. Press Run Mission and the run appears here.
            </div>
          ) : (
            runs.map((run) => {
              const running = run.outcome === "running";
              return (
                <div
                  key={run.id}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    padding: "9px 12px",
                    borderBottom: "1px solid #1F1F1F",
                  }}
                >
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span
                      style={{
                        display: "block",
                        fontSize: "12px",
                        fontWeight: 600,
                        color: "#EFEFEF",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {run.mission}
                    </span>
                    <span
                      style={{
                        display: "block",
                        fontSize: "10px",
                        color: "#777777",
                        fontVariantNumeric: "tabular-nums",
                      }}
                    >
                      {fmtDate(run.started)}
                      {run.duration_s != null &&
                        ` · ${run.duration_s.toFixed(0)} s`}
                      {` · ${run.step_count} step${run.step_count !== 1 ? "s" : ""}`}
                      {run.robots.length > 0 && ` · ${run.robots.join(", ")}`}
                    </span>
                  </span>

                  <span
                    style={{
                      fontSize: "10px",
                      fontWeight: 600,
                      padding: "2px 8px",
                      borderRadius: "999px",
                      color: OUTCOME_COLOR[run.outcome],
                      backgroundColor: `${OUTCOME_COLOR[run.outcome]}1A`,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {run.outcome}
                  </span>

                  <button
                    onClick={() => handleOpenCsv(run)}
                    disabled={!run.csv_path}
                    title={run.csv_path || "No CSV path available"}
                    style={{
                      ...btn,
                      opacity: run.csv_path ? 1 : 0.4,
                      cursor: run.csv_path ? "pointer" : "default",
                    }}
                  >
                    <FileSpreadsheet size={11} />
                    Open CSV
                  </button>
                  <button
                    onClick={() => window.henosync?.shell.openPath(run.path)}
                    title={run.path}
                    style={btn}
                  >
                    <FolderOpen size={11} />
                    Open folder
                  </button>
                  <button
                    onClick={() => handleDelete(run)}
                    onMouseLeave={() =>
                      confirmDelete === run.id && setConfirmDelete(null)
                    }
                    disabled={running}
                    title="Delete this run's recording"
                    style={{
                      ...btn,
                      color: "#F05252",
                      borderColor:
                        confirmDelete === run.id ? "#F05252" : "#2D2D2D",
                      opacity: running ? 0.4 : 1,
                      cursor: running ? "default" : "pointer",
                    }}
                  >
                    <Trash2 size={11} />
                    {confirmDelete === run.id ? "Confirm" : "Delete"}
                  </button>
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}
