"""
Waypoint accuracy trials (Results use case 1 / Table II).

Recorded mission run (Henosync records every Run Mission to ~/.henosync/runs):
every move-to-marker step is one trial, with its own target marker and robot.

    python tools/results/analyze_waypoints.py "<run id or folder>" [--node Jackal] [--tolerance 0.3]

ws_logger run: every completed run of the move-to-marker plugin is one trial,
all to the same marker:

    python tools/results/analyze_waypoints.py runs/jackal_waypoints \
        --node Jackal --marker "Target A" [--plugin auto-navigate]

For each trial the robot's final VICON position (last sample before the step
ended) is compared with the marker. VICON arena only: markers drawn on the
VICON map store lon = x_m, lat = y_m.
"""

import argparse
import csv
import math

from _common import (
    find_named,
    load_run,
    mean,
    node_by_name,
    operation_runs,
    print_table,
    read_jsonl,
    resolve_run_dir,
    std,
    vicon_track,
)

MOVE_TO_MARKER_PLUGINS = {"auto-navigate"}


def _trial_row(trial: int, track, target, state, duration, tolerance, status_text="") -> dict:
    tx, ty = target
    _, fx, fy = track[-1]
    _, sx, sy = track[0]
    error = math.hypot(fx - tx, fy - ty)
    path_len = sum(math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(track, track[1:]))
    straight = math.hypot(tx - sx, ty - sy)
    return {
        "trial": trial,
        "state": state,
        "time_s": duration,
        "start_dist_m": straight,
        "path_len_m": path_len,
        "path_efficiency": straight / path_len if path_len > 0 else float("nan"),
        "final_error_m": error,
        "success": state == "completed" and error <= tolerance,
        "status_text": status_text,
    }


def _mission_trials(run: dict, run_dir, node_filter, tolerance) -> list[dict]:
    """One trial per move-to-marker step of a recorded mission run."""
    meta = run["meta"]
    events = read_jsonl(resolve_run_dir(run_dir) / "steps.jsonl")
    markers = {m["id"]: m for m in meta["markers"]}
    names = {n["id"]: n["name"] for n in meta["nodes"]}
    node_id = node_by_name(meta, node_filter)["id"] if node_filter else None

    rows = []
    for step in meta["steps"]:
        params = step.get("params") or {}
        is_marker_step = (
            params.get("step_type") == "move_to_marker"
            or step["plugin_id"] in MOVE_TO_MARKER_PLUGINS
        )
        marker = markers.get(params.get("marker_id") or "")
        if not is_marker_step or not marker or marker.get("map_mode") != "vicon":
            continue
        start = next((e for e in events if e["index"] == step["index"] and e["event"] == "start"), None)
        end = next((e for e in events if e["index"] == step["index"] and e["event"] == "end"), None)
        if not start or not end:
            print(f"step {step['index'] + 1}: did not finish - skipped")
            continue
        robots = [params["node_id"]] if params.get("node_id") else list(params.get("node_ids") or [])
        for rid in robots:
            if node_id and rid != node_id:
                continue
            track = vicon_track(run["telemetry"], rid, start["recv"], end["recv"])
            if not track:
                print(f"step {step['index'] + 1}: no VICON samples for {names.get(rid, rid)} - skipped")
                continue
            row = _trial_row(
                step["index"] + 1, track, (marker["lon"], marker["lat"]),
                end.get("outcome") or "completed", end["recv"] - start["recv"],
                tolerance, end.get("status_text") or "",
            )
            rows.append({"robot": names.get(rid, rid), "target": marker["name"], **row})
    return rows


def _logger_trials(run: dict, args) -> list[dict]:
    """One trial per completed run of the plugin, all to one marker (ws_logger runs)."""
    if not (args.node and args.marker):
        raise SystemExit("This is a ws_logger run: pass --node and --marker.")
    node = node_by_name(run["meta"], args.node)
    marker = find_named(
        [m for m in run["meta"]["markers"] if m.get("map_mode") == "vicon"],
        args.marker, "VICON marker",
    )
    trials = [r for r in operation_runs(run["operations"]) if r["plugin_id"] == args.plugin]
    if not trials:
        raise SystemExit(f"No {args.plugin} runs in this log.")

    rows = []
    for i, trial in enumerate(trials, 1):
        if trial["end"] is None:
            print(f"trial {i}: still running when logging stopped - skipped")
            continue
        track = vicon_track(run["telemetry"], node["id"], trial["start"], trial["end"])
        if not track:
            print(f"trial {i}: no VICON samples for {node['name']} - skipped")
            continue
        row = _trial_row(
            i, track, (marker["lon"], marker["lat"]), trial["final_state"],
            trial["end"] - trial["start"], args.tolerance, trial["status_text"],
        )
        rows.append({"robot": node["name"], "target": marker["name"], **row})
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run", help="run folder, or a run id from the app's Runs list")
    parser.add_argument("--node", help="robot name (required for ws_logger runs)")
    parser.add_argument("--marker", help="target marker (ws_logger runs only)")
    parser.add_argument("--plugin", default="auto-navigate",
                        help="control plugin id the trials used (ws_logger runs only)")
    parser.add_argument("--tolerance", type=float, default=0.3,
                        help="max final error (m) that counts as a success (default 0.3)")
    parser.add_argument("--csv", help="also write per-trial rows to this CSV file")
    args = parser.parse_args()

    run = load_run(args.run)
    if run["meta"].get("steps") is not None:
        rows = _mission_trials(run, args.run, args.node, args.tolerance)
    else:
        rows = _logger_trials(run, args)
    if not rows:
        raise SystemExit("No analysable trials.")

    print_table(rows, ["trial", "robot", "target", "state", "time_s", "start_dist_m",
                       "path_len_m", "path_efficiency", "final_error_m", "success"])

    errors = [r["final_error_m"] for r in rows]
    times = [r["time_s"] for r in rows]
    successes = sum(r["success"] for r in rows)
    print(
        f"\nTrials: {len(rows)}  |  success (<={args.tolerance} m): {successes}/{len(rows)} "
        f"({100 * successes / len(rows):.0f}%)\n"
        f"Final error: mean {mean(errors):.3f} m, std {std(errors):.3f} m, "
        f"max {max(errors):.3f} m\n"
        f"Completion time: mean {mean(times):.1f} s, std {std(times):.1f} s"
    )

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
