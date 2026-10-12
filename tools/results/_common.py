"""
Shared helpers for the Results tooling: REST access and run-log loading.

A "run" is a directory with this layout, written either by Henosync itself
for every Run Mission (~/.henosync/runs/<run id>/, plus steps.jsonl and
summary.json) or by ws_logger.py for anything that isn't a mission:
    meta.json          snapshot of nodes, zones and markers at start
    telemetry.jsonl    every telemetry frame + "recv" (epoch s)
    events.jsonl       every system event + "recv"
    status.jsonl       node status changes
    operations.jsonl   operation state changes
"""

import json
import math
import sys
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Make the backend importable so scripts share henosync.core.run_metrics
# with the in-app CSV export (same numbers either way).
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps" / "backend"))

RUNS_DIR = Path.home() / ".henosync" / "runs"

DEFAULT_HOST = "127.0.0.1:8765"
TERMINAL_STATES = {"completed", "failed", "idle"}


# -- REST ----------------------------------------------------------------------

def api_get(host: str, path: str) -> Any:
    with urllib.request.urlopen(f"http://{host}{path}", timeout=5) as r:
        return json.loads(r.read())


def api_post(host: str, path: str, body: Optional[dict] = None) -> Any:
    req = urllib.request.Request(
        f"http://{host}{path}",
        data=json.dumps(body or {}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


# -- Run loading ---------------------------------------------------------------

def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def resolve_run_dir(run_dir: str | Path) -> Path:
    """A path, or just a run id from the app's Runs list (looked up in ~/.henosync/runs)."""
    path = Path(run_dir)
    if not path.exists() and (RUNS_DIR / str(run_dir)).exists():
        path = RUNS_DIR / str(run_dir)
    if not (path / "meta.json").exists():
        raise SystemExit(f"Not a run folder: {run_dir}")
    return path


def load_run(run_dir: str | Path) -> dict[str, Any]:
    run = resolve_run_dir(run_dir)
    summary_path = run / "summary.json"
    return {
        "meta": json.loads((run / "meta.json").read_text(encoding="utf-8")),
        "summary": (
            json.loads(summary_path.read_text(encoding="utf-8"))
            if summary_path.exists() else None
        ),
        "telemetry": read_jsonl(run / "telemetry.jsonl"),
        "events": read_jsonl(run / "events.jsonl"),
        "status": read_jsonl(run / "status.jsonl"),
        "operations": read_jsonl(run / "operations.jsonl"),
    }


def parse_ts(value: str) -> float:
    """Backend ISO timestamp -> epoch seconds."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def frame_source(values: dict) -> str:
    """
    'vicon' for frames published by vicon_manager (position + vicon_x/y only),
    'device' for frames from the robot's own device plugin (always carry
    status_text).
    """
    return "vicon" if "vicon_x" in values and "status_text" not in values else "device"


def node_by_name(meta: dict, name_or_id: str) -> dict:
    for n in meta.get("nodes", []):
        if name_or_id in (n["id"], n["name"]):
            return n
    names = ", ".join(n["name"] for n in meta.get("nodes", []))
    raise SystemExit(f"No node named {name_or_id!r} in this run. Nodes: {names}")


def find_named(items: list[dict], name_or_id: str, kind: str) -> dict:
    for item in items:
        if name_or_id in (item["id"], item["name"]):
            return item
    names = ", ".join(i["name"] for i in items)
    raise SystemExit(f"No {kind} named {name_or_id!r}. Available: {names}")


def vicon_track(
    telemetry: list[dict], node_id: str, t0: float = -math.inf, t1: float = math.inf
) -> list[tuple[float, float, float]]:
    """(recv time, x_m, y_m) VICON samples for one node within [t0, t1]."""
    return [
        (f["recv"], f["values"]["vicon_x"], f["values"]["vicon_y"])
        for f in telemetry
        if f["node_id"] == node_id
        and "vicon_x" in f["values"]
        and t0 <= f["recv"] <= t1
    ]


def operation_runs(operations: list[dict]) -> list[dict]:
    """
    One entry per operation run, in start order:
    {plugin_id, operation_name, start, end, final_state, status_text, devices}
    `end` is None if the run hadn't finished when logging stopped.
    """
    runs: dict[tuple[str, str], dict] = {}
    for rec in operations:
        key = (rec["plugin_id"], rec["started_at"])
        run = runs.setdefault(key, {
            "plugin_id": rec["plugin_id"],
            "operation_name": rec.get("operation_name", rec["plugin_id"]),
            "start": parse_ts(rec["started_at"]),
            "end": None,
            "final_state": None,
            "status_text": "",
            "devices": set(),
        })
        status = rec["status"]
        run["devices"].update(status.get("devices_active") or [])
        if status.get("status_text"):
            run["status_text"] = status["status_text"]
        if run["end"] is None and status.get("state") in TERMINAL_STATES:
            run["end"] = rec["recv"]
            run["final_state"] = status["state"]
    return sorted(runs.values(), key=lambda r: r["start"])


# -- Small stats helpers -------------------------------------------------------

def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else float("nan")


def std(xs: list[float]) -> float:
    if len(xs) < 2:
        return float("nan")
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def percentile(xs: list[float], p: float) -> float:
    if not xs:
        return float("nan")
    s = sorted(xs)
    k = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def print_table(rows: list[dict], columns: list[str]) -> None:
    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return "-" if math.isnan(v) else f"{v:.3f}"
        return str(v)

    cells = [[fmt(r.get(c, "")) for c in columns] for r in rows]
    widths = [max(len(c), *(len(row[i]) for row in cells)) for i, c in enumerate(columns)]
    print("  ".join(c.ljust(w) for c, w in zip(columns, widths)))
    print("  ".join("-" * w for w in widths))
    for row in cells:
        print("  ".join(v.ljust(w) for v, w in zip(row, widths)))
