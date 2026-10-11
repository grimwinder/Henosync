"""
Waypoint accuracy trials from a ws_logger run (Results use case 1 / Table II).

Every completed run of a move-to-marker operation in the log is one trial.
For each trial the robot's final VICON position (last sample at or before the
operation finished) is compared with the target marker:

    python tools/results/analyze_waypoints.py runs/jackal_waypoints \
        --node Jackal --marker "Target A" [--plugin auto-navigate] [--tolerance 0.3]

VICON arena only: markers drawn on the VICON map store lon = x_m, lat = y_m.
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
    std,
    vicon_track,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("--node", required=True, help="robot name (as shown in Henosync)")
    parser.add_argument("--marker", required=True, help="target marker name")
    parser.add_argument("--plugin", default="auto-navigate",
                        help="control plugin id the trials used (default: auto-navigate)")
    parser.add_argument("--tolerance", type=float, default=0.3,
                        help="max final error (m) that counts as a success (default 0.3)")
    parser.add_argument("--csv", help="also write per-trial rows to this CSV file")
    args = parser.parse_args()

    run = load_run(args.run)
    node = node_by_name(run["meta"], args.node)
    marker = find_named(
        [m for m in run["meta"]["markers"] if m.get("map_mode") == "vicon"],
        args.marker, "VICON marker",
    )
    target_x, target_y = marker["lon"], marker["lat"]

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
        _, fx, fy = track[-1]
        _, sx, sy = track[0]
        error = math.hypot(fx - target_x, fy - target_y)
        path_len = sum(
            math.hypot(b[1] - a[1], b[2] - a[2]) for a, b in zip(track, track[1:])
        )
        straight = math.hypot(target_x - sx, target_y - sy)
        rows.append({
            "trial": i,
            "state": trial["final_state"],
            "time_s": trial["end"] - trial["start"],
            "start_dist_m": straight,
            "path_len_m": path_len,
            "path_efficiency": straight / path_len if path_len > 0 else float("nan"),
            "final_error_m": error,
            "success": trial["final_state"] == "completed" and error <= args.tolerance,
            "status_text": trial["status_text"],
        })

    if not rows:
        raise SystemExit("No analysable trials.")

    print(f"Target {marker['name']} at x={target_x:.3f} m, y={target_y:.3f} m - robot {node['name']}\n")
    print_table(rows, ["trial", "state", "time_s", "start_dist_m", "path_len_m",
                       "path_efficiency", "final_error_m", "success"])

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
