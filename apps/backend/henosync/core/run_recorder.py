"""
Records every mission run as a single comprehensive CSV file.

Written to ~/Downloads/<run_id>.csv every POLL_S seconds throughout the run.
A lightweight meta.json is kept in ~/.henosync/runs/<run_id>/ for listing.

CSV columns (all columns written every tick, blank when unavailable):
  timestamp, elapsed_s                           wall clock
  mission_name, mission_status                   overall state
  step_index, step_name, step_type, step_event   current step context
  <node>_status                                  ONLINE/DEGRADED/ERROR/OFFLINE
  <node>_battery_pct
  <node>_lat, <node>_lon                         GPS position (WGS84)
  <node>_vicon_x, <node>_vicon_y                 VICON position (metres from origin)
  <node>_speed
  <node>_heading                                 degrees, 0=North
  <node>_signal
  <node>_imu_roll, <node>_imu_pitch, <node>_imu_yaw  radians
  <node>_telemetry_age_s                         seconds since last frame
  <node>_op_plugin                               plugin_id of active operation on this device
  <node>_op_state                                RUNNING/COMPLETED/FAILED/IDLE
  <node>_op_status_text
  <node>_op_progress                             0–1 if the plugin reports it
  vicon_connected                                True/False
  events                                         semicolon-separated events fired this tick

step_event is blank most ticks; on the tick when a step starts it is "started",
on the tick when it ends it is "completed" or "failed".
"""

import asyncio
import csv
import json
import logging
import re
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

RUNS_DIR = Path.home() / ".henosync" / "runs"
DOWNLOADS_DIR = Path.home() / "Downloads"
POLL_S = 0.5

_NODE_COLS = [
    "status", "battery_pct",
    "lat", "lon",
    "vicon_x", "vicon_y",
    "speed", "heading", "signal",
    "imu_roll", "imu_pitch", "imu_yaw",
    "telemetry_age_s",
    "op_plugin", "op_state", "op_status_text", "op_progress",
]

_FIXED_HEAD = [
    "timestamp", "elapsed_s",
    "mission_name", "mission_status",
    "step_index", "step_name", "step_type", "step_event",
]
_FIXED_TAIL = ["vicon_connected", "events"]


def _safe_col(name: str) -> str:
    return re.sub(r"\W+", "_", name).strip("_").lower() or "node"


def _node_prefixes(nodes: list) -> dict:
    """Return {node_id: column_prefix}, deduplicating identical names."""
    seen: dict[str, int] = {}
    result: dict[str, str] = {}
    for node in nodes:
        base = _safe_col(node.name)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result[node.id] = base if count == 0 else f"{base}_{count + 1}"
    return result


class _ActiveRun:
    def __init__(self, run_id: str, path: Path, csv_path: Path, mission: str,
                 steps: list, node_col_map: dict, columns: list):
        self.id = run_id
        self.path = path
        self.csv_path = csv_path
        self.mission = mission
        self.started = time.time()
        self.steps = steps              # from start_run — used for name/type lookup
        self.node_col_map = node_col_map   # node_id -> column prefix
        self.columns = columns

        # Current step context — updated by record_step()
        self.current_step_index: int = -1
        self.current_step_name: str = ""
        self.current_step_type: str = ""
        self.pending_step_event: str = ""  # written once then cleared

        # Events buffered between ticks
        self.pending_events: list[str] = []

        self.csv_file = csv_path.open("w", newline="", encoding="utf-8", buffering=1)
        self.csv_writer = csv.DictWriter(
            self.csv_file, fieldnames=columns, extrasaction="ignore"
        )
        self.csv_writer.writeheader()
        self.csv_file.flush()
        self.poll_task: Optional[asyncio.Task] = None

    def close(self) -> None:
        self.csv_file.flush()
        self.csv_file.close()


class RunRecorder:
    """One active run at a time; started and stopped by the Mission page."""

    def __init__(self) -> None:
        self._active: Optional[_ActiveRun] = None
        self._subscribed = False

    @property
    def active_run_id(self) -> Optional[str]:
        return self._active.id if self._active else None

    # ── Lifecycle ──────────────────────────────────────────────────

    async def start_run(self, mission: str, steps: list[dict]) -> dict:
        from .node_registry import node_registry

        if self._active:
            await self.stop_run(self._active.id, "interrupted")
        self._subscribe_once()

        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe = _safe_col(mission)[:40] or "mission"
        run_id = f"{stamp}_{safe}"
        path = RUNS_DIR / run_id
        suffix = 2
        while path.exists():
            run_id = f"{stamp}_{safe}_{suffix}"
            path = RUNS_DIR / run_id
            suffix += 1
        path.mkdir(parents=True, exist_ok=True)

        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        csv_path = DOWNLOADS_DIR / f"{run_id}.csv"

        nodes = node_registry.get_all_nodes()
        node_col_map = _node_prefixes(nodes)
        node_cols = [
            f"{prefix}_{col}"
            for prefix in node_col_map.values()
            for col in _NODE_COLS
        ]
        columns = _FIXED_HEAD + node_cols + _FIXED_TAIL

        run = _ActiveRun(run_id, path, csv_path, mission, steps, node_col_map, columns)

        meta = {
            "run_id": run_id,
            "mission": mission,
            "started": run.started,
            "steps": steps,
            "csv_path": str(csv_path),
            "nodes": [
                {"id": n.id, "name": n.name, "col": node_col_map[n.id]}
                for n in nodes
            ],
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

        self._active = run
        run.poll_task = asyncio.create_task(self._poll_loop(run))
        logger.info(f"Run recording started: {csv_path}")
        return {"run_id": run_id, "path": str(path), "csv_path": str(csv_path)}

    def record_step(
        self, run_id: str, index: int, event: str,
        outcome: Optional[str] = None, status_text: str = "",
    ) -> None:
        run = self._require_active(run_id)
        if event == "start":
            run.current_step_index = index
            # Look up name and type from the steps list sent at start_run
            step_meta = next((s for s in run.steps if s.get("index") == index), None)
            if step_meta:
                run.current_step_name = step_meta.get("display_name") or step_meta.get("name", "")
                run.current_step_type = (step_meta.get("params") or {}).get("step_type") or step_meta.get("plugin_id", "")
            run.pending_step_event = "started"
        elif event == "end":
            run.pending_step_event = "completed" if (outcome or "completed") == "completed" else "failed"

    async def stop_run(self, run_id: str, outcome: str) -> dict:
        run = self._require_active(run_id)
        self._active = None
        if run.poll_task:
            run.poll_task.cancel()
            try:
                await run.poll_task
            except asyncio.CancelledError:
                pass
        self._write_row(run)  # final row
        run.close()

        meta_path = run.path / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["ended"] = time.time()
        meta["outcome"] = outcome
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

        logger.info(f"Run recording stopped ({outcome}): {run.csv_path}")
        return self._describe(run.path)

    async def shutdown(self) -> None:
        if self._active:
            await self.stop_run(self._active.id, "interrupted")

    # ── Queries ───────────────────────────────────────────────────

    def list_runs(self) -> list[dict]:
        if not RUNS_DIR.exists():
            return []
        runs = [self._describe(p) for p in RUNS_DIR.iterdir() if (p / "meta.json").exists()]
        return sorted(runs, key=lambda r: r["started"], reverse=True)

    def get_run(self, run_id: str) -> dict:
        return self._describe(self._run_path(run_id))

    def delete_run(self, run_id: str) -> None:
        if self._active and self._active.id == run_id:
            raise ValueError("Run is still in progress")
        path = self._run_path(run_id)
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        csv_p = Path(meta.get("csv_path", ""))
        if csv_p.exists():
            csv_p.unlink(missing_ok=True)
        shutil.rmtree(path)

    # ── Event subscription ────────────────────────────────────────

    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        from .telemetry_bus import telemetry_bus
        telemetry_bus.subscribe_events(self._on_event)
        self._subscribed = True

    async def _on_event(self, event) -> None:
        run = self._active
        if run is None:
            return
        severity = getattr(event.severity, "value", str(event.severity))
        run.pending_events.append(f"[{severity}] {event.title}: {event.message}")

    # ── Polling loop ──────────────────────────────────────────────

    async def _poll_loop(self, run: _ActiveRun) -> None:
        while True:
            self._write_row(run)
            run.pending_step_event = ""
            run.pending_events = []
            await asyncio.sleep(POLL_S)

    def _write_row(self, run: _ActiveRun) -> None:
        from .node_registry import node_registry
        from .operation_manager import operation_manager
        from .mission_engine import mission_engine
        from .vicon_manager import vicon_manager

        now = time.time()

        row: dict = {
            "timestamp": datetime.fromtimestamp(now).isoformat(timespec="milliseconds"),
            "elapsed_s": round(now - run.started, 2),
            "mission_name": run.mission,
            "mission_status": mission_engine.get_status().get("status", ""),
            "step_index": run.current_step_index if run.current_step_index >= 0 else "",
            "step_name": run.current_step_name,
            "step_type": run.current_step_type,
            "step_event": run.pending_step_event,
            "vicon_connected": vicon_manager.is_connected,
            "events": "; ".join(run.pending_events),
        }

        for node_id, prefix in run.node_col_map.items():
            node = node_registry.get_node(node_id)
            if not node:
                continue

            row[f"{prefix}_status"] = node.status.value
            row[f"{prefix}_battery_pct"] = node.battery_percent if node.battery_percent is not None else ""

            if node.last_seen:
                row[f"{prefix}_telemetry_age_s"] = round(now - node.last_seen.timestamp(), 1)

            frame = node_registry.get_last_frame(node_id)
            if frame:
                if frame.position:
                    row[f"{prefix}_lat"] = frame.position.lat
                    row[f"{prefix}_lon"] = frame.position.lon
                    if frame.position.heading is not None:
                        row[f"{prefix}_heading"] = round(frame.position.heading, 2)
                if frame.speed is not None:
                    row[f"{prefix}_speed"] = round(frame.speed, 3)
                if frame.signal_strength is not None:
                    row[f"{prefix}_signal"] = frame.signal_strength
                if frame.imu:
                    imu = frame.imu
                    row[f"{prefix}_imu_roll"] = round(imu.roll, 4) if imu.roll is not None else ""
                    row[f"{prefix}_imu_pitch"] = round(imu.pitch, 4) if imu.pitch is not None else ""
                    row[f"{prefix}_imu_yaw"] = round(imu.yaw, 4) if imu.yaw is not None else ""

            # VICON x/y from node.telemetry (written by vicon_manager each frame)
            t = node.telemetry
            if "vicon_x" in t:
                row[f"{prefix}_vicon_x"] = t["vicon_x"]
            if "vicon_y" in t:
                row[f"{prefix}_vicon_y"] = t["vicon_y"]

            # Active operation assigned to this device
            op = operation_manager.get_node_operation(node_id)
            if op:
                s = op["status"]
                row[f"{prefix}_op_plugin"] = op["plugin_id"]
                row[f"{prefix}_op_state"] = s.get("state", "")
                row[f"{prefix}_op_status_text"] = s.get("status_text", "")
                prog = s.get("progress")
                row[f"{prefix}_op_progress"] = prog if prog is not None else ""

        run.csv_writer.writerow(row)
        run.csv_file.flush()

    # ── Helpers ───────────────────────────────────────────────────

    def _require_active(self, run_id: str) -> _ActiveRun:
        if not self._active or self._active.id != run_id:
            raise ValueError(f"Run {run_id} is not the active run")
        return self._active

    @staticmethod
    def _run_path(run_id: str) -> Path:
        path = (RUNS_DIR / run_id).resolve()
        if path.parent != RUNS_DIR.resolve() or not (path / "meta.json").exists():
            raise KeyError(run_id)
        return path

    def _describe(self, path: Path) -> dict:
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        running = self._active is not None and self._active.id == meta["run_id"]
        ended = meta.get("ended")
        return {
            "id": meta["run_id"],
            "mission": meta["mission"],
            "path": str(path),
            "csv_path": meta.get("csv_path", ""),
            "started": meta["started"],
            "ended": ended,
            "duration_s": round(ended - meta["started"], 1) if ended else None,
            "outcome": "running" if running else meta.get("outcome", "incomplete"),
            "robots": [n["name"] for n in meta.get("nodes", [])],
            "step_count": len(meta.get("steps", [])),
            "results": [],
        }


run_recorder = RunRecorder()
