"""
Telemetry pipeline performance from a ws_logger run (Results use case 1).

Per node and per source (the robot's own plugin vs. VICON):
  - frames received and mean update rate (Hz)
  - inter-arrival jitter (std, p95, max gap)
  - dropped frames (gaps in the sequence numbers)
  - backend -> client delay: logger receive time minus the frame's backend
    timestamp. Valid only when the logger runs on the same machine as the
    backend (same clock). It does NOT include robot -> backend delay.

    python tools/results/analyze_telemetry.py runs/jackal_waypoints [--csv out.csv]
"""

import argparse
import csv
from collections import defaultdict

from _common import frame_source, load_run, mean, parse_ts, percentile, print_table, std


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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("--csv", help="also write the table to this CSV file")
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


if __name__ == "__main__":
    main()
