"""
Record everything Henosync streams during an experiment.

Connects to the running backend (no code changes needed) and writes a run
directory that every analyze_*.py script reads:

    python tools/results/ws_logger.py --out runs/jackal_waypoints

Stop with Ctrl+C (or pass --duration seconds). Run it with the backend's
virtualenv Python, which already has the `websockets` package.
"""

import argparse
import asyncio
import json
import time
from pathlib import Path

import websockets

from _common import DEFAULT_HOST, api_get

NODE_POLL_S = 0.2
OPERATION_POLL_S = 0.5


def _snapshot(host: str) -> dict:
    meta = {"started": time.time(), "host": host}
    meta["nodes"] = api_get(host, "/api/nodes")["nodes"]
    meta["zones"] = [
        z for mode in ("gps", "vicon") for z in api_get(host, f"/api/zones?mode={mode}")["zones"]
    ]
    meta["markers"] = [
        m for mode in ("gps", "vicon")
        for m in api_get(host, f"/api/markers?mode={mode}")["markers"]
    ]
    return meta


async def _stream(url: str, out, counter: dict, key: str) -> None:
    """Append every non-ping message with its receive time; reconnect on drop."""
    while True:
        try:
            async with websockets.connect(url, max_size=None) as ws:
                async for raw in ws:
                    recv = time.time()
                    msg = json.loads(raw)
                    if msg.get("type") == "ping":
                        continue
                    msg["recv"] = recv
                    out.write(json.dumps(msg) + "\n")
                    counter[key] += 1
        except (OSError, websockets.ConnectionClosed) as e:
            print(f"[logger] {url} dropped ({e}); retrying in 1 s")
            await asyncio.sleep(1.0)


async def _poll_nodes(host: str, out) -> None:
    """Log a line whenever a node's status changes."""
    last: dict[str, str] = {}
    while True:
        try:
            nodes = (await asyncio.to_thread(api_get, host, "/api/nodes"))["nodes"]
            recv = time.time()
            for n in nodes:
                if last.get(n["id"]) != n["status"]:
                    out.write(json.dumps({
                        "recv": recv,
                        "node_id": n["id"],
                        "name": n["name"],
                        "status": n["status"],
                        "last_seen": n.get("last_seen"),
                    }) + "\n")
                    print(f"[logger] {n['name']}: {last.get(n['id'], '-')} -> {n['status']}")
                    last[n["id"]] = n["status"]
        except OSError:
            pass
        await asyncio.sleep(NODE_POLL_S)


async def _poll_operations(host: str, out) -> None:
    """Log a line whenever an operation's state or status text changes."""
    last: dict[tuple, tuple] = {}
    while True:
        try:
            ops = (await asyncio.to_thread(api_get, host, "/api/operations"))["operations"]
            recv = time.time()
            for op in ops:
                key = (op["plugin_id"], op["started_at"])
                sig = (op["status"].get("state"), op["status"].get("status_text"))
                if last.get(key) != sig:
                    out.write(json.dumps({"recv": recv, **op}) + "\n")
                    print(f"[logger] {op['operation_name']}: {sig[0]} - {sig[1]}")
                    last[key] = sig
        except OSError:
            pass
        await asyncio.sleep(OPERATION_POLL_S)


async def _report(counter: dict) -> None:
    while True:
        await asyncio.sleep(10)
        print(f"[logger] {counter['telemetry']} telemetry frames, {counter['events']} events")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True, help="run directory to create")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--duration", type=float, help="stop after this many seconds")
    args = parser.parse_args()

    run = Path(args.out)
    run.mkdir(parents=True, exist_ok=False)
    (run / "meta.json").write_text(json.dumps(_snapshot(args.host), indent=2), encoding="utf-8")

    files = {
        name: (run / f"{name}.jsonl").open("a", encoding="utf-8", buffering=1)
        for name in ("telemetry", "events", "status", "operations")
    }
    counter = {"telemetry": 0, "events": 0}
    tasks = [
        _stream(f"ws://{args.host}/ws/telemetry", files["telemetry"], counter, "telemetry"),
        _stream(f"ws://{args.host}/ws/events", files["events"], counter, "events"),
        _poll_nodes(args.host, files["status"]),
        _poll_operations(args.host, files["operations"]),
        _report(counter),
    ]
    print(f"[logger] recording to {run} - Ctrl+C to stop")
    try:
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=args.duration)
    except asyncio.TimeoutError:
        pass
    finally:
        for f in files.values():
            f.close()
        print(f"[logger] saved {counter['telemetry']} frames, {counter['events']} events to {run}")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
