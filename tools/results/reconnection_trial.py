"""
Dropout / reconnection trials (Results use case 6).

Guides you through N trials and appends one CSV row per trial:

    python tools/results/reconnection_trial.py --node Jackal --trials 20 \
        --out runs/reconnect_wifi.csv [--method wifi] [--outage 15]

Each trial:
  1. waits until the robot is ONLINE
  2. cuts the link - runs --cut-cmd if given, otherwise you cut it yourself and
     press Enter AT THE SAME MOMENT (timing error = your reaction time)
  3. records how long until Henosync marks the robot DEGRADED and ERROR
  4. restores the link - runs --restore-cmd after --outage seconds if given,
     otherwise you restore it and press Enter
  5. watches --watch seconds for automatic recovery (Henosync has none by design,
     so this documents that it stays down)
  6. presses Reconnect via the REST API and times how long until ONLINE

Precise, hands-free timing on Windows (no admin needed):
    --cut-cmd "netsh wlan disconnect" \
    --restore-cmd "netsh wlan connect name=<SSID>" --outage 15
Killing rosbridge instead, e.g.:
    --cut-cmd "ssh user@jackal pkill -f rosbridge" \
    --restore-cmd "ssh user@jackal <your rosbridge launch command> &"

The REST API is on 127.0.0.1, so turning the laptop's WiFi off does not stop
this script talking to Henosync.
"""

import argparse
import csv
import subprocess
import threading
import time
from pathlib import Path

from _common import DEFAULT_HOST, api_get, api_post

POLL_S = 0.1


class StatusWatcher(threading.Thread):
    """Polls one node and timestamps every status change (logger clock)."""

    def __init__(self, host: str, node_id: str) -> None:
        super().__init__(daemon=True)
        self.host, self.node_id = host, node_id
        self.status = None
        self.changes: list[tuple[float, str]] = []
        self._lock = threading.Lock()

    def run(self) -> None:
        while True:
            try:
                node = api_get(self.host, f"/api/nodes/{self.node_id}")
                with self._lock:
                    if node["status"] != self.status:
                        self.status = node["status"]
                        self.changes.append((time.time(), node["status"]))
            except OSError:
                pass
            time.sleep(POLL_S)

    def first_change_after(self, t: float, status: str):
        with self._lock:
            return next((ts for ts, s in self.changes if ts >= t and s == status), None)

    def wait_for(self, status: str, timeout: float) -> float | None:
        start = time.time()
        while time.time() - start < timeout:
            if self.status == status:
                return time.time()
            time.sleep(POLL_S)
        return None


def _resolve_node(host: str, name_or_id: str) -> dict:
    for n in api_get(host, "/api/nodes")["nodes"]:
        if name_or_id in (n["id"], n["name"]):
            return n
    raise SystemExit(f"No node named {name_or_id!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--node", required=True)
    parser.add_argument("--trials", type=int, default=10)
    parser.add_argument("--out", required=True, help="CSV file (appended to)")
    parser.add_argument("--method", default="wifi", help="label for how the link was cut")
    parser.add_argument("--cut-cmd", help="shell command that cuts the link")
    parser.add_argument("--restore-cmd", help="shell command that restores the link")
    parser.add_argument("--outage", type=float,
                        help="seconds between cut and restore (used with --restore-cmd)")
    parser.add_argument("--watch", type=float, default=30.0,
                        help="seconds to watch for automatic recovery (default 30)")
    parser.add_argument("--host", default=DEFAULT_HOST)
    args = parser.parse_args()

    node = _resolve_node(args.host, args.node)
    watcher = StatusWatcher(args.host, node["id"])
    watcher.start()

    out = Path(args.out)
    new_file = not out.exists()
    out.parent.mkdir(parents=True, exist_ok=True)
    if args.restore_cmd and args.outage is None:
        raise SystemExit("--restore-cmd needs --outage")
    fields = [
        "trial", "method", "timing", "to_degraded_s", "to_error_s",
        "actual_outage_s", "auto_recovered", "reconnect_to_online_s", "reconnect_result",
    ]
    with out.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        if new_file:
            writer.writeheader()

        for trial in range(1, args.trials + 1):
            print(f"\n-- Trial {trial}/{args.trials} -- waiting for {node['name']} to be ONLINE...")
            while watcher.wait_for("online", timeout=5) is None:
                print("   still not ONLINE - reconnect it from Henosync if needed")

            if args.cut_cmd:
                time.sleep(2.0)  # settle
                t_cut = time.time()
                subprocess.run(args.cut_cmd, shell=True)
                print("   link cut")
            else:
                input("   Press Enter AT THE MOMENT you cut the link... ")
                t_cut = time.time()

            if args.restore_cmd:
                time.sleep(max(0.0, t_cut + args.outage - time.time()))
                subprocess.run(args.restore_cmd, shell=True)
                print("   link restored")
            else:
                input("   Restore the link when ready, then press Enter... ")
            t_restore = time.time()

            t_degraded = watcher.first_change_after(t_cut, "degraded")
            t_error = watcher.first_change_after(t_cut, "error")

            reconnect_s, result = None, "not needed"
            if t_degraded is None and t_error is None:
                print("   Henosync never marked the robot as down during this outage")
                recovered, result = None, "never detected"
            else:
                print(f"   watching {args.watch:.0f} s for automatic recovery...")
                recovered = watcher.wait_for("online", timeout=args.watch) is not None

            if recovered is False:
                t0 = time.time()
                api_post(args.host, f"/api/nodes/{node['id']}/reconnect")
                t_online = watcher.wait_for("online", timeout=30)
                reconnect_s = t_online - t0 if t_online else None
                result = "online" if t_online else f"still {watcher.status}"

            row = {
                "trial": trial,
                "method": args.method,
                "timing": "command" if args.cut_cmd else "manual",
                "to_degraded_s": round(t_degraded - t_cut, 3) if t_degraded else None,
                "to_error_s": round(t_error - t_cut, 3) if t_error else None,
                "actual_outage_s": round(t_restore - t_cut, 1),
                "auto_recovered": recovered,
                "reconnect_to_online_s": round(reconnect_s, 3) if reconnect_s else None,
                "reconnect_result": result,
            }
            writer.writerow(row)
            f.flush()
            print("   " + ", ".join(f"{k}={v}" for k, v in row.items() if k != "trial"))

    print(f"\nSaved to {out}")


if __name__ == "__main__":
    main()
