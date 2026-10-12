import { useEffect, useState } from "react";
import {
  X,
  Download,
  FolderOpen,
  Trash2,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { getRuns, exportRun, deleteRun } from "../../lib/api";
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

function fmtNum(v: number | null, digits: number) {
  return v == null ? "—" : v.toFixed(digits);
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

/** Lists recorded mission runs with CSV export, open folder and delete. */
export default function RunsDialog({ onClose }: { onClose: () => void }) {
  const [runs, setRuns] = useState<MissionRun[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
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

  async function handleExport(run: MissionRun) {
    const dest = await window.henosync?.dialog.saveFile(
      [{ name: "CSV", extensions: ["csv"] }],
      `${run.id}.csv`,
    );
    if (!dest) return;
    try {
      const { path } = await exportRun(run.id, dest);
      setNotice(`Exported to ${path}`);
    } catch (e) {
      setNotice(`Export failed: ${(e as Error).message}`);
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
            Every Run Mission is recorded to ~/.henosync/runs
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
              const isOpen = expanded === run.id;
              const running = run.outcome === "running";
              return (
                <div key={run.id} style={{ borderBottom: "1px solid #1F1F1F" }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "10px",
                      padding: "9px 12px",
                    }}
                  >
                    <button
                      onClick={() => setExpanded(isOpen ? null : run.id)}
                      title={isOpen ? "Hide steps" : "Show steps"}
                      style={{
                        flex: 1,
                        minWidth: 0,
                        display: "flex",
                        alignItems: "center",
                        gap: "8px",
                        background: "none",
                        border: "none",
                        padding: 0,
                        cursor: "pointer",
                        textAlign: "left",
                        color: "inherit",
                      }}
                    >
                      {isOpen ? (
                        <ChevronDown size={12} color="#666666" />
                      ) : (
                        <ChevronRight size={12} color="#666666" />
                      )}
                      <span style={{ minWidth: 0 }}>
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
                          {run.robots.length > 0 &&
                            ` · ${run.robots.join(", ")}`}
                        </span>
                      </span>
                    </button>

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
                      onClick={() => handleExport(run)}
                      disabled={running}
                      title={
                        running
                          ? "Available when the run finishes"
                          : "Export step results as CSV"
                      }
                      style={{
                        ...btn,
                        opacity: running ? 0.4 : 1,
                        cursor: running ? "default" : "pointer",
                      }}
                    >
                      <Download size={11} />
                      Export CSV
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

                  {isOpen && <StepTable run={run} />}
                </div>
              );
            })
          )}
        </div>
      </div>
    </div>
  );
}

function StepTable({ run }: { run: MissionRun }) {
  if (run.results.length === 0) {
    return (
      <div style={{ padding: "0 12px 12px 32px", fontSize: "11px", color: "#666666" }}>
        {run.outcome === "running"
          ? "Step results appear when the run finishes."
          : "No step results recorded for this run."}
      </div>
    );
  }
  const th: React.CSSProperties = {
    textAlign: "left",
    padding: "4px 8px",
    fontSize: "9px",
    fontWeight: 700,
    letterSpacing: "0.8px",
    color: "#666666",
    whiteSpace: "nowrap",
  };
  const td: React.CSSProperties = {
    padding: "4px 8px",
    fontSize: "11px",
    color: "#CCCCCC",
    borderTop: "1px solid #1F1F1F",
    whiteSpace: "nowrap",
    fontVariantNumeric: "tabular-nums",
  };
  return (
    <div style={{ padding: "0 12px 12px 32px", overflowX: "auto" }}>
      <table style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            {["STEP", "TYPE", "ROBOT", "TARGET", "OUTCOME", "TIME (S)", "ERROR (M)", "COVERAGE (%)"].map(
              (h) => (
                <th key={h} style={th}>
                  {h}
                </th>
              ),
            )}
          </tr>
        </thead>
        <tbody>
          {run.results.map((r, i) => (
            <tr key={i}>
              <td style={td}>
                {r.step} · {r.step_name}
              </td>
              <td style={td}>{r.step_type}</td>
              <td style={td}>{r.robot || "—"}</td>
              <td style={td}>{r.target || "—"}</td>
              <td style={td} title={r.status_text}>
                {r.outcome}
              </td>
              <td style={td}>{fmtNum(r.duration_s, 1)}</td>
              <td style={td}>{fmtNum(r.final_error_m, 3)}</td>
              <td style={td}>{fmtNum(r.coverage_pct, 1)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
