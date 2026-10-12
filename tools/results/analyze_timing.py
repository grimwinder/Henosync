"""
Parallel execution timing analysis (Results use case 3).

Shows per-step timeline from a mission run's steps.jsonl, identifies
steps that ran concurrently (parallel groups), and prints:
  - per-step start/end times and durations
  - which steps overlapped (parallel group)
  - sequential estimate: sum of all step durations (as if run serially)
  - actual total wall time
  - speedup ratio: sequential / actual

    python tools/results/analyze_timing.py "<run id or folder>" [--csv out.csv]
"""

import argparse
import csv
import math

from _common import load_run, print_table, read_jsonl, resolve_run_dir


def analyze(meta: dict, steps_events: list[dict]) -> tuple[list[dict], dict]:
    step_meta = {s["index"]: s for s in (meta.get("steps") or [])}

    # collect start/end per step index
    starts: dict[int, float] = {}
    ends: dict[int, dict] = {}
    for ev in steps_events:
        idx = ev["index"]
        if ev["event"] == "start":
            starts[idx] = ev["recv"]
        elif ev["event"] == "end":
            ends[idx] = ev

    # build step rows
    rows = []
    for idx in sorted(starts):
        sm = step_meta.get(idx, {})
        t0 = starts[idx]
        end_ev = ends.get(idx)
        t1 = end_ev["recv"] if end_ev else None
        duration = (t1 - t0) if t1 is not None else float("nan")
        rows.append({
            "step": idx + 1,
            "name": sm.get("display_name") or sm.get("name") or f"step {idx + 1}",
            "plugin": sm.get("plugin_id", ""),
            "parallel": "YES" if sm.get("parallel") else "no",
            "start_s": t0,
            "end_s": t1 if t1 is not None else float("nan"),
            "duration_s": duration,
            "outcome": (end_ev or {}).get("outcome", ""),
        })

    if not rows:
        return rows, {}

    # identify concurrent groups: steps whose [start, end] intervals overlap
    # use the step's parallelGroupId if present, otherwise detect by time overlap
    groups: list[list[int]] = []
    assigned: set[int] = set()
    for i, r in enumerate(rows):
        if i in assigned:
            continue
        group = [i]
        for j, r2 in enumerate(rows):
            if j <= i or j in assigned:
                continue
            # overlap: r.start < r2.end AND r2.start < r.end
            if (not math.isnan(r["end_s"]) and not math.isnan(r2["end_s"])
                    and r["start_s"] < r2["end_s"] and r2["start_s"] < r["end_s"]):
                group.append(j)
        if len(group) > 1:
            assigned.update(group)
            groups.append(group)

    # label groups
    for g_idx, group in enumerate(groups, 1):
        for row_idx in group:
            rows[row_idx]["group"] = f"G{g_idx}"

    # summary stats
    serial_s = sum(r["duration_s"] for r in rows if not math.isnan(r["duration_s"]))
    t_start = min(r["start_s"] for r in rows)
    t_end_vals = [r["end_s"] for r in rows if not math.isnan(r["end_s"])]
    t_end = max(t_end_vals) if t_end_vals else float("nan")
    actual_s = t_end - t_start if not math.isnan(t_end) else float("nan")
    speedup = serial_s / actual_s if actual_s and not math.isnan(actual_s) else float("nan")

    summary = {
        "steps": len(rows),
        "parallel_groups": len(groups),
        "serial_estimate_s": serial_s,
        "actual_wall_time_s": actual_s,
        "speedup_ratio": speedup,
    }
    return rows, summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("run")
    parser.add_argument("--csv", help="also write per-step rows to this CSV file")
    args = parser.parse_args()

    run = load_run(args.run)
    run_dir = resolve_run_dir(args.run)
    steps_events = read_jsonl(run_dir / "steps.jsonl")

    if not steps_events:
        raise SystemExit("No steps.jsonl in this run (mission runs only).")

    rows, summary = analyze(run["meta"], steps_events)
    if not rows:
        raise SystemExit("No step start events found.")

    # normalise times to seconds from mission start
    t0 = min(r["start_s"] for r in rows)
    for r in rows:
        r["start_s"] = round(r["start_s"] - t0, 3)
        if not math.isnan(r["end_s"]):
            r["end_s"] = round(r["end_s"] - t0, 3)

    print_table(rows, ["step", "name", "plugin", "parallel", "group",
                       "start_s", "end_s", "duration_s", "outcome"])

    print(
        f"\nSteps: {summary['steps']}  |  parallel groups: {summary['parallel_groups']}\n"
        f"Serial estimate:   {summary['serial_estimate_s']:.1f} s\n"
        f"Actual wall time:  {summary['actual_wall_time_s']:.1f} s\n"
        f"Speedup ratio:     {summary['speedup_ratio']:.2f}×"
    )

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        print(f"\nwrote {args.csv}")


if __name__ == "__main__":
    main()
