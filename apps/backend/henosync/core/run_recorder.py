"""
Records every mission run (one press of Run Mission) to its own folder.

    ~/.henosync/runs/<YYYY-MM-DD_HH-MM-SS>_<mission name>/
        meta.json          mission, steps, nodes, zones, markers at start
        telemetry.jsonl    every telemetry frame (same format as /ws/telemetry) + "recv"
        events.jsonl       every system event + "recv"
        status.jsonl       node status changes
        operations.jsonl   operation state changes
        steps.jsonl        step start / end reported by the Mission page
        summary.json       per-step results, written when the run stops
        report.html        human-readable report built from the above by
                           tools/results/henosync_report.py after the run stops

The folder layout matches tools/results/ws_logger.py, so the analysis
scripts read either. Times are epoch seconds on the backend's clock.
"""

import asyncio
import csv
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from . import run_metrics
from .marker_manager import marker_manager
from .telemetry_bus import telemetry_bus
from .zone_manager import zone_manager

logger = logging.getLogger(__name__)

RUNS_DIR = Path.home() / ".henosync" / "runs"
OPERATION_POLL_S = 0.5
REPORT_SCRIPT = Path(__file__).resolve().parents[4] / "tools" / "results" / "henosync_report.py"
REPORT_NAME = "report.html"
REPORT_TIMEOUT_S = 120

CSV_COLUMNS = [
    "run_id", "mission", "step", "step_name", "step_type", "robot", "target",
    "started_at", "ended_at", "duration_s", "outcome",
    "final_x_m", "final_y_m", "target_x_m", "target_y_m",
    "final_error_m", "coverage_pct", "status_text",
]

# Control plugins whose single step type isn't carried in a step_type param.
_PLUGIN_STEP_TYPES = {"area-navigate": "move_to_marker"}


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^\w\- ]+", "_", name).strip() or "Mission"
    return cleaned[:60]


def _fmt_time(epoch: Optional[float]) -> str:
    if epoch is None:
        return ""
    return datetime.fromtimestamp(epoch).strftime("%Y-%m-%d %H:%M:%S.%f")[:-5]


def _round(value: Optional[float], digits: int = 3) -> Optional[float]:
    return None if value is None else round(value, digits)


class _ActiveRun:
    def __init__(self, run_id: str, path: Path, mission: str, steps: list[dict]):
        self.id = run_id
        self.path = path
        self.mission = mission
        self.steps = steps
        self.started = time.time()
        self.files = {
            name: (path / f"{name}.jsonl").open("a", encoding="utf-8", buffering=1)
            for name in ("telemetry", "events", "status", "operations", "steps")
        }
        self.node_status: dict[str, str] = {}
        self.op_signatures: dict[tuple, tuple] = {}
        self.poll_task: Optional[asyncio.Task] = None

    def write(self, name: str, record: dict) -> None:
        self.files[name].write(json.dumps(record, default=str) + "\n")

    def close(self) -> None:
        for f in self.files.values():
            f.close()


class RunRecorder:
    """One active run at a time; started and stopped by the Mission page."""

    def __init__(self) -> None:
        self._active: Optional[_ActiveRun] = None
        self._subscribed = False
        self._report_tasks: dict[str, asyncio.Task] = {}

    @property
    def active_run_id(self) -> Optional[str]:
        return self._active.id if self._active else None

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start_run(self, mission: str, steps: list[dict]) -> dict:
        from .node_registry import node_registry

        if self._active:
            await self.stop_run(self._active.id, "interrupted")
        self._subscribe_once()

        stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        run_id = f"{stamp}_{_safe_name(mission)}"
        path = RUNS_DIR / run_id
        suffix = 2
        while path.exists():
            run_id = f"{stamp}_{_safe_name(mission)}_{suffix}"
            path = RUNS_DIR / run_id
            suffix += 1
        path.mkdir(parents=True)

        run = _ActiveRun(run_id, path, mission, steps)
        meta = {
            "run_id": run_id,
            "mission": mission,
            "started": run.started,
            "steps": steps,
            "nodes": [n.model_dump(mode="json") for n in node_registry.get_all_nodes()],
            "zones": [z.model_dump(mode="json") for z in zone_manager.get_all_zones()],
            "markers": [m.model_dump(mode="json") for m in marker_manager.get_all_markers()],
        }
        (path / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        for node in node_registry.get_all_nodes():
            self._record_status(run, node)

        self._active = run
        run.poll_task = asyncio.create_task(self._poll_operations(run))
        logger.info(f"Run recording started: {path}")
        return {"run_id": run_id, "path": str(path)}

    def record_step(
        self, run_id: str, index: int, event: str,
        outcome: Optional[str] = None, status_text: str = "",
    ) -> None:
        run = self._require_active(run_id)
        run.write("steps", {
            "recv": time.time(), "index": index, "event": event,
            "outcome": outcome, "status_text": status_text,
        })

    async def stop_run(self, run_id: str, outcome: str) -> dict:
        run = self._require_active(run_id)
        self._active = None
        if run.poll_task:
            run.poll_task.cancel()
            try:
                await run.poll_task
            except asyncio.CancelledError:
                pass
        self._poll_once(run)  # final operation states
        ended = time.time()
        run.close()

        summary = {
            "run_id": run.id,
            "mission": run.mission,
            "started": run.started,
            "ended": ended,
            "outcome": outcome,
            "results": self._step_results(run.path, ended, outcome),
        }
        (run.path / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        logger.info(f"Run recording stopped ({outcome}): {run.path}")
        self._start_report(run.id, run.path)
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

    def export_csv(self, run_id: str, dest: str) -> str:
        run = self.get_run(run_id)
        if run["outcome"] == "running":
            raise ValueError("Run is still in progress")
        with open(dest, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            writer.writeheader()
            for row in run["results"]:
                writer.writerow({"run_id": run["id"], "mission": run["mission"], **row})
        return dest

    async def report(self, run_id: str) -> str:
        """Path to the run's report.html, building it first if needed."""
        path = self._run_path(run_id)
        if self._active and self._active.id == run_id:
            raise ValueError("Run is still in progress")
        task = self._report_tasks.get(run_id)
        if task:
            await asyncio.shield(task)
        report = path / REPORT_NAME
        if not report.exists():
            await _build_report(path)
        return str(report)

    def delete_run(self, run_id: str) -> None:
        if self._active and self._active.id == run_id:
            raise ValueError("Run is still in progress")
        shutil.rmtree(self._run_path(run_id))

    # ── Recording ─────────────────────────────────────────────────

    def _subscribe_once(self) -> None:
        if self._subscribed:
            return
        from .node_registry import node_registry

        telemetry_bus.subscribe_telemetry(self._on_telemetry)
        telemetry_bus.subscribe_events(self._on_event)
        node_registry.add_listener(self._on_node_change)
        self._subscribed = True

    async def _on_telemetry(self, frame) -> None:
        run = self._active
        if run is None:
            return
        run.write("telemetry", {
            "type": "telemetry",
            "node_id": frame.node_id,
            "timestamp": frame.timestamp.isoformat(),
            "sequence": frame.sequence_number,
            "values": frame.to_values_dict(),
            "recv": time.time(),
        })

    async def _on_event(self, event) -> None:
        run = self._active
        if run is None:
            return
        run.write("events", {
            "type": "event",
            "id": event.id,
            "severity": event.severity,
            "title": event.title,
            "message": event.message,
            "node_id": event.node_id,
            "timestamp": event.timestamp.isoformat(),
            "recv": time.time(),
        })

    def _on_node_change(self, node) -> None:
        if self._active is not None:
            self._record_status(self._active, node)

    @staticmethod
    def _record_status(run: _ActiveRun, node) -> None:
        status = getattr(node.status, "value", node.status)
        if run.node_status.get(node.id) == status:
            return
        run.node_status[node.id] = status
        run.write("status", {
            "recv": time.time(),
            "node_id": node.id,
            "name": node.name,
            "status": status,
            "last_seen": node.last_seen.isoformat() if node.last_seen else None,
        })

    async def _poll_operations(self, run: _ActiveRun) -> None:
        while True:
            self._poll_once(run)
            await asyncio.sleep(OPERATION_POLL_S)

    @staticmethod
    def _poll_once(run: _ActiveRun) -> None:
        from .operation_manager import operation_manager

        recv = time.time()
        for op in operation_manager.get_all_operation_statuses():
            key = (op["plugin_id"], op["started_at"])
            status = op["status"]
            signature = (status.get("state"), status.get("status_text"))
            if run.op_signatures.get(key) != signature:
                run.op_signatures[key] = signature
                run.write("operations", {"recv": recv, **json.loads(json.dumps(op, default=str))})

    # ── Results ───────────────────────────────────────────────────

    def _step_results(self, path: Path, ended: float, run_outcome: str) -> list[dict]:
        meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
        step_events = _read_jsonl(path / "steps.jsonl")
        telemetry = _read_jsonl(path / "telemetry.jsonl")
        operations = _read_jsonl(path / "operations.jsonl")

        names = {n["id"]: n["name"] for n in meta["nodes"]}
        markers = {m["id"]: m for m in meta["markers"]}
        zones = {z["id"]: z for z in meta["zones"]}

        rows: list[dict] = []
        for step in meta["steps"]:
            idx = step["index"]
            params = step.get("params") or {}
            started = next((e["recv"] for e in step_events
                            if e["index"] == idx and e["event"] == "start"), None)
            end_event = next((e for e in step_events
                              if e["index"] == idx and e["event"] == "end"), None)
            step_end = end_event["recv"] if end_event else (ended if started else None)
            if started is None:
                outcome = "not run"
            elif end_event:
                outcome = end_event.get("outcome") or "completed"
            else:
                outcome = "stopped" if run_outcome != "completed" else "completed"
            status_text = (end_event or {}).get("status_text") or ""

            step_type = params.get("step_type") or _PLUGIN_STEP_TYPES.get(
                step["plugin_id"], step["plugin_id"]
            )
            robot_ids = _step_robots(step, params, operations, started, step_end)

            marker = markers.get(params.get("marker_id") or "")
            zone = zones.get(params.get("zone_id") or "")
            target_name = (marker or zone or {}).get("name", "")
            target_xy = (
                (marker["lon"], marker["lat"])
                if marker and marker.get("map_mode") == "vicon" else None
            )

            tracks = {
                rid: _vicon_track(telemetry, rid, started, step_end)
                for rid in robot_ids
            } if started else {}

            coverage = None
            if (step_type == "area_coverage" and zone and zone.get("map_mode") == "vicon"
                    and any(tracks.values())):
                swath = float(params.get("coverage_spacing_m") or 0) or 1.0
                coverage = run_metrics.coverage_percent(
                    run_metrics.zone_polygon_xy(zone),
                    [t for t in tracks.values() if t], swath,
                )

            base = {
                "step": idx + 1,
                "step_name": step.get("name", ""),
                "step_type": step_type,
                "target": target_name,
                "started_at": _fmt_time(started),
                "ended_at": _fmt_time(step_end),
                "duration_s": _round(step_end - started, 1) if started and step_end else None,
                "outcome": outcome,
                "target_x_m": _round(target_xy[0]) if target_xy else None,
                "target_y_m": _round(target_xy[1]) if target_xy else None,
                "coverage_pct": _round(coverage, 1),
                "status_text": status_text,
            }
            for rid in robot_ids or [None]:
                track = tracks.get(rid) if rid else None
                final = track[-1] if track else None
                error = (
                    run_metrics.final_error_m(track, *target_xy)
                    if track and target_xy else None
                )
                rows.append({
                    **base,
                    "robot": names.get(rid, rid or ""),
                    "final_x_m": _round(final[1]) if final else None,
                    "final_y_m": _round(final[2]) if final else None,
                    "final_error_m": _round(error),
                })
        return rows

    # ── Report ────────────────────────────────────────────────────

    def _start_report(self, run_id: str, path: Path) -> None:
        task = asyncio.create_task(_build_report(path))
        self._report_tasks[run_id] = task

        def done(t: asyncio.Task) -> None:
            self._report_tasks.pop(run_id, None)
            if not t.cancelled() and t.exception():
                logger.warning(f"Report generation failed for {run_id}: {t.exception()}")

        task.add_done_callback(done)

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
        summary_path = path / "summary.json"
        summary = (
            json.loads(summary_path.read_text(encoding="utf-8"))
            if summary_path.exists() else None
        )
        running = self._active is not None and self._active.id == meta["run_id"]
        names = {n["id"]: n["name"] for n in meta["nodes"]}
        robots: list[str] = []
        for step in meta["steps"]:
            params = step.get("params") or {}
            for rid in _selected_robots(params):
                name = names.get(rid, rid)
                if name not in robots:
                    robots.append(name)
        ended = summary["ended"] if summary else None
        return {
            "id": meta["run_id"],
            "mission": meta["mission"],
            "path": str(path),
            "started": meta["started"],
            "ended": ended,
            "duration_s": _round(ended - meta["started"], 1) if ended else None,
            "outcome": "running" if running else (summary["outcome"] if summary else "incomplete"),
            "robots": robots,
            "step_count": len(meta["steps"]),
            "results": summary["results"] if summary else [],
        }


async def _build_report(path: Path) -> Path:
    """Run tools/results/henosync_report.py on one run folder -> report.html."""
    out = path / REPORT_NAME
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(REPORT_SCRIPT), str(path), "-o", str(out)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=REPORT_TIMEOUT_S,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"Report generation timed out after {REPORT_TIMEOUT_S} s")
    if proc.returncode != 0:
        lines = proc.stderr.strip().splitlines()
        raise RuntimeError(lines[-1] if lines else f"Report script exited {proc.returncode}")
    return out


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _selected_robots(params: dict) -> list[str]:
    ids = [params["node_id"]] if params.get("node_id") else []
    node_ids = params.get("node_ids") or []
    if isinstance(node_ids, str):
        node_ids = [node_ids]
    return ids + [i for i in node_ids if i and i not in ids]


def _step_robots(
    step: dict, params: dict, operations: list[dict],
    started: Optional[float], ended: Optional[float],
) -> list[str]:
    """Robots the step used: the operator's selection, else what the plugin reported."""
    selected = _selected_robots(params)
    if selected or started is None:
        return selected
    seen: list[str] = []
    for op in operations:
        if op["plugin_id"] != step["plugin_id"]:
            continue
        if not (started - 1 <= op["recv"] <= (ended or op["recv"]) + 1):
            continue
        for rid in op["status"].get("devices_active") or []:
            if rid not in seen:
                seen.append(rid)
    return seen


def _vicon_track(
    telemetry: list[dict], node_id: str, t0: float, t1: Optional[float]
) -> run_metrics.Track:
    end = t1 if t1 is not None else float("inf")
    return [
        (f["recv"], f["values"]["vicon_x"], f["values"]["vicon_y"])
        for f in telemetry
        if f["node_id"] == node_id and "vicon_x" in f["values"] and t0 <= f["recv"] <= end
    ]


run_recorder = RunRecorder()
