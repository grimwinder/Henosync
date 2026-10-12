"""
Area coverage (lawnmower) and multi-robot results (Results use cases 2 and 3).

For one AREA_COVERAGE step in a VICON zone:
  - coverage %: share of the zone within swath/2 of any robot's VICON trail
    (same calculation as the coverage_pct column of the app's CSV export)
  - path deviation: distance from each trail sample to the planned sweep path
    (regenerated with area-navigate's own _generate_coverage_paths)
  - completion time
  - with 2+ robots: per-robot coverage and the minimum distance between robots

Recorded mission run — zone, spacing, angle and robots come from the step:

    python tools/results/analyze_coverage.py "<run id or folder>" [--step 2] [--swath 0.5]

ws_logger run — pass them yourself:

    python tools/results/analyze_coverage.py runs/jackal_lawnmower \
        --zone "Arena A" --spacing 0.5 --nodes Jackal [TurtleBot3] \
        [--angle 0] [--swath 0.5] [--run-index -1]

--swath is the width one pass actually covers (default: the spacing).
"""

import argparse
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace

from _common import (
    find_named,
    load_run,
    mean,
    node_by_name,
    operation_runs,
    percentile,
    read_jsonl,
    resolve_run_dir,
    vicon_track,
)
from henosync.core import run_metrics

_PLUGIN = Path(__file__).resolve().parents[2] / "plugins" / "control" / "area-navigate" / "plugin.py"


def _load_area_navigate():
    spec = importlib.util.spec_from_file_location("area_navigate_plugin", _PLUGIN)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _zone_namespace(zone: dict) -> SimpleNamespace:
    pt = lambda p: SimpleNamespace(lat=p["lat"], lon=p["lon"])  # noqa: E731
    return SimpleNamespace(
        name=zone["name"],
        map_mode=zone.get("map_mode", "gps"),
        points=[pt(p) for p in zone.get("points") or []],
        center=pt(zone["center"]) if zone.get("center") else None,
        radius_m=zone.get("radius_m"),
    )


def _seg_dist(px, py, ax, ay, bx, by) -> float:
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _min_separation(tracks: dict[str, list]) -> tuple[float, str]:
    """Closest approach between any two robots, pairing samples within 0.1 s."""
    best, where = math.inf, ""
    names = list(tracks)
    for a in range(len(names)):
        for b in range(a + 1, len(names)):
            ta, tb = tracks[names[a]], tracks[names[b]]
            j = 0
            for t, x, y in ta:
                while j + 1 < len(tb) and abs(tb[j + 1][0] - t) <= abs(tb[j][0] - t):
                    j += 1
                if tb and abs(tb[j][0] - t) <= 0.1:
                    d = math.hypot(x - tb[j][1], y - tb[j][2])
                    if d < best:
                        best, where = d, f"{names[a]} / {names[b]}"
    return best, where


def _from_mission(run: dict, args) -> dict:
    """Coverage step settings and time window from a recorded mission run."""
    meta = run["meta"]
    events = read_jsonl(resolve_run_dir(args.run) / "steps.jsonl")
    coverage_steps = [
        s for s in meta["steps"] if (s.get("params") or {}).get("step_type") == "area_coverage"
    ]
    if not coverage_steps:
        raise SystemExit("This run has no Area Coverage step.")
    if args.step:
        step = next((s for s in coverage_steps if s["index"] == args.step - 1), None)
        if step is None:
            raise SystemExit(f"Step {args.step} is not an Area Coverage step.")
    else:
        step = coverage_steps[-1]
    params = step["params"]
    start = next((e for e in events if e["index"] == step["index"] and e["event"] == "start"), None)
    end = next((e for e in events if e["index"] == step["index"] and e["event"] == "end"), None)
    if start is None:
        raise SystemExit(f"Step {step['index'] + 1} never started.")
    zone = next((z for z in meta["zones"] if z["id"] == params.get("zone_id")), None)
    if zone is None:
        raise SystemExit("The step's zone is not in the run snapshot.")
    robot_ids = list(params.get("node_ids") or [])
    if not robot_ids:
        raise SystemExit("The step had no robots selected - pass --nodes.")
    return {
        "label": f"Step {step['index'] + 1} ({step.get('name', '')})",
        "zone": zone,
        "spacing": float(params.get("coverage_spacing_m") or 0) or 1.0,
        "angle": float(params.get("coverage_angle_deg") or 0),
        "nodes": [node_by_name(meta, rid) for rid in robot_ids],
        "start": start["recv"],
        "end": end["recv"] if end else math.inf,
        "state": (end or {}).get("outcome") or "unfinished",
    }


def _from_logger(run: dict, args) -> dict:
    if not (args.zone and args.spacing and args.nodes):
        raise SystemExit("This is a ws_logger run: pass --zone, --spacing and --nodes.")
    runs = [r for r in operation_runs(run["operations"]) if r["plugin_id"] == args.plugin]
    if not runs:
        raise SystemExit(f"No {args.plugin} runs in this log.")
    op = runs[args.run_index]
    return {
        "label": op["operation_name"],
        "zone": find_named(run["meta"]["zones"], args.zone, "zone"),
        "spacing": args.spacing,
        "angle": args.angle or 0.0,
        "nodes": [node_by_name(run["meta"], n) for n in args.nodes],
        "start": op["start"],
        "end": op["end"] if op["end"] is not None else math.inf,
        "state": op["final_state"] or "running",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", help="run folder, or a run id from the app's Runs list")
    parser.add_argument("--step", type=int, help="mission runs: coverage step number (default: last)")
    parser.add_argument("--zone", help="ws_logger runs: zone name")
    parser.add_argument("--spacing", type=float, help="ws_logger runs: Coverage Spacing (m)")
    parser.add_argument("--angle", type=float, help="ws_logger runs: Sweep Angle (deg)")
    parser.add_argument("--nodes", nargs="+", help="ws_logger runs: robot names")
    parser.add_argument("--swath", type=float, help="covered width per pass (default: spacing)")
    parser.add_argument("--plugin", default="area-navigate")
    parser.add_argument("--run-index", type=int, default=-1,
                        help="ws_logger runs: which run of the plugin (default: last)")
    args = parser.parse_args()

    run = load_run(args.run)
    cfg = _from_mission(run, args) if run["meta"].get("steps") is not None else _from_logger(run, args)
    if cfg["zone"].get("map_mode") != "vicon":
        raise SystemExit("Only VICON-mode zones are supported.")

    area_nav = _load_area_navigate()
    polygon = run_metrics.zone_polygon_xy(cfg["zone"])
    _, planned = area_nav._generate_coverage_paths(
        _zone_namespace(cfg["zone"]), len(cfg["nodes"]), cfg["spacing"], cfg["angle"]
    )
    planned_segments = [(a, b) for path in planned for a, b in zip(path, path[1:])]

    inside = run_metrics.zone_cells(polygon)
    origin = run_metrics.grid_origin(polygon)
    swath = args.swath or cfg["spacing"]

    tracks = {
        n["name"]: vicon_track(run["telemetry"], n["id"], cfg["start"], cfg["end"])
        for n in cfg["nodes"]
    }
    duration = (cfg["end"] - cfg["start"]) if cfg["end"] != math.inf else float("nan")
    print(f"{cfg['label']} - {cfg['state']}, time {duration:.1f} s")
    print(f"Zone {cfg['zone']['name']}: {len(inside) * run_metrics.GRID_M ** 2:.2f} m^2, "
          f"spacing {cfg['spacing']} m, swath {swath} m, {len(planned)} planned strip(s)\n")

    all_covered: set[tuple[int, int]] = set()
    for name, track in tracks.items():
        if not track:
            print(f"{name}: no VICON samples during the step")
            continue
        covered = run_metrics.covered_cells(track, swath / 2, origin) & inside
        all_covered |= covered
        devs = [
            min(_seg_dist(x, y, *a, *b) for a, b in planned_segments)
            for _, x, y in track
        ] if planned_segments else []
        print(f"{name}: {len(track)} samples, covers {100 * len(covered) / len(inside):.1f}% of zone, "
              f"path deviation mean {mean(devs):.3f} m / p95 {percentile(devs, 95):.3f} m / "
              f"max {max(devs, default=float('nan')):.3f} m")

    print(f"\nTotal coverage: {100 * len(all_covered) / len(inside):.1f}%")
    if len(tracks) > 1:
        dist, pair = _min_separation(tracks)
        print(f"Minimum robot separation: {dist:.3f} m ({pair})")


if __name__ == "__main__":
    main()
