"""
CPU and memory use of a running Henosync (install / platform results).

Samples the backend (python main.py) and the Electron app processes once a
second and prints mean / max per group:

    python tools/results/resource_monitor.py --duration 60 --label "idle, 0 robots" \
        [--csv runs/resources.csv]

Needs psutil:  python -m pip install psutil
Works on Windows, macOS and Linux. Run once per scenario (idle, 1 robot,
3 robots, mission running) and per OS.
"""

import argparse
import csv
import platform
import time
from pathlib import Path

import psutil


def _group(proc: psutil.Process) -> str | None:
    try:
        name = proc.name().lower()
        cmd = " ".join(proc.cmdline()).lower()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    if "python" in name and "main.py" in cmd and "backend" in cmd.replace("\\", "/"):
        return "backend"
    if "python" in name and "main.py" in cmd:
        try:
            if Path(proc.cwd()).name == "backend":
                return "backend"
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return None
    if "electron" in name or "henosync" in name:
        return "desktop"
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--label", default="", help="scenario label stored in the CSV")
    parser.add_argument("--csv", help="append a summary row to this CSV file")
    args = parser.parse_args()

    procs = {p.pid: (p, g) for p in psutil.process_iter() if (g := _group(p))}
    if not any(g == "backend" for _, g in procs.values()):
        raise SystemExit("Henosync backend (python main.py) not found - is the app running?")
    for p, _ in procs.values():
        p.cpu_percent(None)  # prime per-process CPU counters

    samples: dict[str, list[tuple[float, float]]] = {"backend": [], "desktop": []}
    end = time.time() + args.duration
    print(f"Sampling {len(procs)} process(es) for {args.duration:.0f} s...")
    while time.time() < end:
        time.sleep(1.0)
        totals = {"backend": [0.0, 0.0], "desktop": [0.0, 0.0]}
        for p, g in list(procs.values()):
            try:
                totals[g][0] += p.cpu_percent(None)
                totals[g][1] += p.memory_info().rss / 2**20
            except psutil.NoSuchProcess:
                procs.pop(p.pid, None)
        for g, (cpu, mem) in totals.items():
            samples[g].append((cpu, mem))

    cores = psutil.cpu_count() or 1
    row = {
        "label": args.label,
        "os": f"{platform.system()} {platform.release()}",
        "cpu_cores": cores,
        "ram_total_gb": round(psutil.virtual_memory().total / 2**30, 1),
        "duration_s": args.duration,
    }
    for g, s in samples.items():
        cpu = [c for c, _ in s]
        mem = [m for _, m in s]
        # psutil reports per-core %; divide by cores for share of the whole machine.
        row[f"{g}_cpu_mean_pct"] = round(sum(cpu) / len(cpu) / cores, 2) if cpu else None
        row[f"{g}_cpu_max_pct"] = round(max(cpu) / cores, 2) if cpu else None
        row[f"{g}_rss_mean_mb"] = round(sum(mem) / len(mem), 1) if mem else None
        row[f"{g}_rss_max_mb"] = round(max(mem), 1) if mem else None

    for k, v in row.items():
        print(f"{k:>22}: {v}")

    if args.csv:
        path = Path(args.csv)
        new = not path.exists()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(row))
            if new:
                writer.writeheader()
            writer.writerow(row)
        print(f"\nappended to {path}")


if __name__ == "__main__":
    main()
