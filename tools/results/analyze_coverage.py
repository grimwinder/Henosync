"""
Area coverage (lawnmower) and multi-robot results from a ws_logger run
(Results use cases 2 and 3).

For one area-navigate AREA_COVERAGE run in a VICON zone:
  - coverage %: share of the zone within swath/2 of any robot's VICON trail
  - path deviation: distance from each trail sample to the planned sweep path
    (regenerated with area-navigate's own _generate_coverage_paths)
  - completion time
  - with 2+ robots: per-robot coverage and the minimum distance between robots

    python tools/results/analyze_coverage.py runs/jackal_lawnmower \
        --zone "Arena A" --spacing 0.5 --nodes Jackal [TurtleBot3] \
        [--angle 0] [--swath 0.5] [--run-index -1]

--spacing and --angle must match the step's Coverage Spacing and Sweep Angle.
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
    vicon_track,
)

GRID_M = 0.05
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


def _covered_cells(track, radius, x0, y0) -> set[tuple[int, int]]:
    """Grid cells within `radius` of the trail, densifying long segments."""
    cells: set[tuple[int, int]] = set()
    r_cells = int(math.ceil(radius / GRID_M))
    points = []
    for (_, ax, ay), (_, bx, by) in zip(track, track[1:]):
        steps = max(1, int(math.hypot(bx - ax, by - ay) / (GRID_M / 2)))
        points.extend((ax + (bx - ax) * k / steps, ay + (by - ay) * k / steps) for k in range(steps))
    if track:
        points.append((track[-1][1], track[-1][2]))
    for px, py in points:
        ci, cj = int((px - x0) / GRID_M), int((py - y0) / GRID_M)
        for i in range(ci - r_cells, ci + r_cells + 1):
            for j in range(cj - r_cells, cj + r_cells + 1):
                cx, cy = x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M
                if math.hypot(cx - px, cy - py) <= radius:
                    cells.add((i, j))
    return cells


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("--zone", required=True)
    parser.add_argument("--spacing", type=float, required=True)
    parser.add_argument("--angle", type=float, default=0.0)
    parser.add_argument("--swath", type=float, help="covered width per pass (default: spacing)")
    parser.add_argument("--nodes", nargs="+", required=True, help="robot names, in any order")
    parser.add_argument("--plugin", default="area-navigate")
    parser.add_argument("--run-index", type=int, default=-1,
                        help="which run of the plugin in the log (default: last)")
    args = parser.parse_args()

    area_nav = _load_area_navigate()
    run = load_run(args.run)
    zone_dict = find_named(run["meta"]["zones"], args.zone, "zone")
    if zone_dict.get("map_mode") != "vicon":
        raise SystemExit("Only VICON-mode zones are supported.")
    zone = _zone_namespace(zone_dict)
    nodes = [node_by_name(run["meta"], n) for n in args.nodes]

    runs = [r for r in operation_runs(run["operations"]) if r["plugin_id"] == args.plugin]
    if not runs:
        raise SystemExit(f"No {args.plugin} runs in this log.")
    op = runs[args.run_index]
    end = op["end"] if op["end"] is not None else math.inf

    polygon = area_nav._vicon_zone_polygon(zone)
    _, planned = area_nav._generate_coverage_paths(zone, len(nodes), args.spacing, args.angle)
    planned_segments = [
        (a, b) for path in planned for a, b in zip(path, path[1:])
    ]

    xs, ys = [p[0] for p in polygon], [p[1] for p in polygon]
    x0, y0 = min(xs), min(ys)
    zone_cells = {
        (i, j)
        for i in range(int((max(xs) - x0) / GRID_M) + 1)
        for j in range(int((max(ys) - y0) / GRID_M) + 1)
        if area_nav._point_in_polygon_xy(x0 + (i + 0.5) * GRID_M, y0 + (j + 0.5) * GRID_M, polygon)
    }
    radius = (args.swath or args.spacing) / 2

    tracks = {n["name"]: vicon_track(run["telemetry"], n["id"], op["start"], end) for n in nodes}
    all_covered: set[tuple[int, int]] = set()
    print(f"{op['operation_name']} - state {op['final_state'] or 'running'}, "
          f"time {((op['end'] or op['start']) - op['start']):.1f} s")
    print(f"Zone {zone.name}: {len(zone_cells) * GRID_M ** 2:.2f} m^2, spacing {args.spacing} m, "
          f"swath {2 * radius} m, {len(planned)} planned strip(s)\n")

    for name, track in tracks.items():
        if not track:
            print(f"{name}: no VICON samples during the run")
            continue
        covered = _covered_cells(track, radius, x0, y0) & zone_cells
        all_covered |= covered
        devs = [
            min(_seg_dist(x, y, *a, *b) for a, b in planned_segments)
            for _, x, y in track
        ] if planned_segments else []
        print(f"{name}: {len(track)} samples, covers {100 * len(covered) / len(zone_cells):.1f}% of zone, "
              f"path deviation mean {mean(devs):.3f} m / p95 {percentile(devs, 95):.3f} m / "
              f"max {max(devs, default=float('nan')):.3f} m")

    print(f"\nTotal coverage: {100 * len(all_covered) / len(zone_cells):.1f}%")
    if len(tracks) > 1:
        dist, pair = _min_separation(tracks)
        print(f"Minimum robot separation: {dist:.3f} m ({pair})")


if __name__ == "__main__":
    main()
