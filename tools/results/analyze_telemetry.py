"""
Telemetry pipeline performance from a recorded mission run or a ws_logger
run (Results use cases 1 and 5).

Per node and per source (the robot's own plugin vs. VICON):
  - frames received and mean update rate (Hz)
  - inter-arrival jitter (std, p95, max gap)
  - dropped frames (gaps in the sequence numbers)
  - backend -> client delay: receive time minus the frame's backend
    timestamp (same machine, same clock). For runs recorded inside Henosync
    this is only the in-process delay; use a ws_logger run to measure the
    WebSocket path to the UI. Neither includes robot -> backend delay.

Dropout cross-reference (--dropout flag):
  Shows each ONLINE→DEGRADED/ERROR window per node, the number of VICON
  position frames that arrived during it, and how far the robot moved —
  proving the position pipeline kept working while the device plugin was
  disconnected.

    python tools/results/analyze_telemetry.py "<run id or folder>" [--csv out.csv] [--dropout]
"""

import argparse
import csv
import math
from collections import defaultdict

from _common import frame_source, load_run, mean, parse_ts, percentile, print_table, std, vicon_track


def analyze(telemetry: list[dict], names: dict[str, str]) -> list[dict]:
    streams: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for f in telemetry:
        streams[(f["node_id"], frame_source(f["values"]))].append(f)

    rows = []
    for (node_id, source), frames in sorted(streams.items()):
        frames.sort(key=lambda f: f["recv"])
        recv = [f["recv"] for f in frames]
        gaps = [b - a for a, b in zip(recv, recv[1:])]
        delays_ms = [(f["recv"] - parse_ts(f["timestamp"])) * 1000 for f in frames]

        seqs = [f["sequence"] for f in frames]
        dropped = sum(max(0, b - a - 1) for a, b in zip(seqs, seqs[1:]) if b > a)
        restarts = sum(1 for a, b in zip(seqs, seqs[1:]) if b <= a)  # stream restarted (reconnect)
        expected = len(frames) + dropped

        duration = recv[-1] - recv[0] if len(recv) > 1 else 0.0
        rows.append({
            "node": names.get(node_id, node_id[:8]),
            "source": source,
            "frames": len(frames),
            "duration_s": duration,
            "rate_hz": (len(frames) - 1) / duration if duration > 0 else float("nan"),
            "gap_mean_ms": mean(gaps) * 1000,
            "gap_std_ms": std(gaps) * 1000,
            "gap_p95_ms": percentile(gaps, 95) * 1000,
            "gap_max_ms": max(gaps) * 1000 if gaps else float("nan"),
            "dropped": dropped,
            "drop_pct": 100.0 * dropped / expected if expected else float("nan"),
            "stream_restarts": restarts,
            "delay_mean_ms": mean(delays_ms),
            "delay_p95_ms": percentile(delays_ms, 95),
            "delay_max_ms": max(delays_ms),
        })
    return rows


def analyze_dropouts(status: list[dict], telemetry: list[dict], names: dict[str, str]) -> list[dict]:
    """
    Cross-reference status transitions with VICON telemetry.
    Returns one row per ONLINE→DEGRADED/ERROR dropout window per node.
    """
    DEGRADED_STATUSES = {"DEGRADED", "ERROR"}

    # group status records by node
    by_node: dict[str, list[dict]] = defaultdict(list)
    for rec in status:
        by_node[rec["node_id"]].append(rec)
    for recs in by_node.values():
        recs.sort(key=lambda r: r["recv"])

    rows = []
    for node_id, recs in sorted(by_node.items()):
        dropout_start = None
        for rec in recs:
            s = rec["status"]
            if s in DEGRADED_STATUSES and dropout_start is None:
                dropout_start = rec["recv"]
                dropout_status = s
            elif s == "ONLINE" and dropout_start is not None:
                t0, t1 = dropout_start, rec["recv"]
                track = vicon_track(telemetry, node_id, t0, t1)
                dist = sum(
                    math.hypot(b[1] - a[1], b[2] - a[2])
                    for a, b in zip(track, track[1:])
                )
                rows.append({
                    "node": names.get(node_id, node_id[:8]),
                    "dropout_status": dropout_status,
                    "start_s": f"{t0:.1f}",
                    "end_s": f"{t1:.1f}",
                    "duration_s": t1 - t0,
                    "vicon_frames": len(track),
                    "distance_moved_m": dist,
                    "position_live": "YES" if track else "NO",
                })
                dropout_start = None
        # still degraded at end of run
        if dropout_start is not None:
            t0 = dropout_start
            t1 = recs[-1]["recv"]
            track = vicon_track(telemetry, node_id, t0, t1)
            dist = sum(
                math.hypot(b[1] - a[1], b[2] - a[2])
                for a, b in zip(track, track[1:])
            )
            rows.append({
                "node": names.get(node_id, node_id[:8]),
                "dropout_status": dropout_status,
                "start_s": f"{t0:.1f}",
                "end_s": "(end)",
                "duration_s": t1 - t0,
                "vicon_frames": len(track),
                "distance_moved_m": dist,
                "position_live": "YES" if track else "NO",
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("--csv", help="also write the telemetry table to this CSV file")
    parser.add_argument("--dropout", action="store_true",
                        help="print dropout cross-reference table (status vs VICON position)")
    args = parser.parse_args()

    run = load_run(args.run)
    names = {n["id"]: n["name"] for n in run["meta"].get("nodes", [])}
    rows = analyze(run["telemetry"], names)
    if not rows:
        raise SystemExit("No telemetry frames in this run.")

    print_table(rows, [
        "node", "source", "frames", "rate_hz", "gap_std_ms", "gap_p95_ms", "gap_max_ms",
        "dropped", "drop_pct", "stream_restarts", "delay_mean_ms", "delay_p95_ms",
    ])
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nwrote {args.csv}")

    if args.dropout:
        dropout_rows = analyze_dropouts(run["status"], run["telemetry"], names)
        if not dropout_rows:
            print("\nNo dropout windows found in status.jsonl.")
        else:
            print(f"\n--- Dropout cross-reference ({len(dropout_rows)} window(s)) ---")
            print_table(dropout_rows, [
                "node", "dropout_status", "start_s", "end_s",
                "duration_s", "vicon_frames", "distance_moved_m", "position_live",
            ])


if __name__ == "__main__":
    main()
