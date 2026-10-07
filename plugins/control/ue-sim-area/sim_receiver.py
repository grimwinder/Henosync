"""
UE Sim Area — sim-side packet decoder.

Runs on the Unreal Engine sim machine, NOT inside Henosync. Place this file
next to coverage_fns.py.

Henosync's "UE Sim Area" mission step sends one newline-terminated JSON line
per robot over TCP (ue-sim device config "area_port", default 7000):

    {"angle_1": 0.0, "angle_2": 6.2814, "radius": 50.0,
     "ag_id": 1, "nag": 1, "envi_type": "Circular"}

Angles are radians in [0, 2π), counter-clockwise from angle_1 to angle_2
(angle_2 < angle_1 means the sector wraps through 0). This script decodes the
packet into a coverage_fns.Agents object:

    angle_1, angle_2  -> ang_bounds
    radius            -> R
    ag_id, nag, envi_type -> passed through unchanged

Use from your own sim code:

    from sim_receiver import decode_packet
    agent = decode_packet(line)

Or run standalone to receive packets and print the decoded agent:

    python sim_receiver.py              # listens on 0.0.0.0:7000
    python sim_receiver.py --port 7001

Requires only the Python standard library plus coverage_fns.py (and its own
dependencies: numpy, shapely, matplotlib).
"""

import argparse
import json
import math
import socketserver

REQUIRED_KEYS = ("angle_1", "angle_2", "radius", "ag_id", "nag", "envi_type")
SUPPORTED_ENVS = ("Circular",)  # RegularPolygons crashes coverage_fns after 10 interactions


class PacketError(ValueError):
    """Raised when a packet is malformed or has invalid values."""


def parse_packet(line):
    """Validate one packet and return the keyword arguments for coverage_fns.Agents."""
    if isinstance(line, bytes):
        line = line.decode("utf-8")
    try:
        data = json.loads(line)
    except json.JSONDecodeError as e:
        raise PacketError(f"not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise PacketError("packet must be a JSON object")

    missing = [k for k in REQUIRED_KEYS if k not in data]
    if missing:
        raise PacketError(f"missing keys: {', '.join(missing)}")

    try:
        angle_1 = float(data["angle_1"]) % (2 * math.pi)
        angle_2 = float(data["angle_2"]) % (2 * math.pi)
        radius = float(data["radius"])
        ag_id = int(data["ag_id"])
        nag = int(data["nag"])
    except (TypeError, ValueError) as e:
        raise PacketError(f"wrong value type: {e}") from e
    envi_type = data["envi_type"]

    if radius <= 0:
        raise PacketError(f"radius must be > 0 (got {radius})")
    if nag < 1 or not 1 <= ag_id <= nag:
        raise PacketError(f"ag_id must be between 1 and nag (got ag_id={ag_id}, nag={nag})")
    if envi_type not in SUPPORTED_ENVS:
        raise PacketError(f"envi_type must be one of {SUPPORTED_ENVS} (got {envi_type!r})")

    return {
        "ag_id": ag_id,
        "envi_type": envi_type,
        "nag": nag,
        "ang_bounds": [angle_1, angle_2],
        "R": radius,
    }


def decode_packet(line):
    """Decode one packet from Henosync into a coverage_fns.Agents object."""
    from coverage_fns import Agents  # imported here so parse_packet works without coverage_fns

    return Agents(**parse_packet(line))


class _Handler(socketserver.StreamRequestHandler):
    # Henosync opens one connection per packet, sends one line, then closes.
    def handle(self):
        for line in self.rfile:
            if not line.strip():
                continue
            try:
                agent = decode_packet(line)
            except PacketError as e:
                print(f"[{self.client_address[0]}] rejected packet: {e}", flush=True)
                continue
            print(
                f"[{self.client_address[0]}] agent {agent.id}/{agent.nag} ({agent.env}) "
                f"ang_bounds=[{agent.ang_bounds[0]:.4f}, {agent.ang_bounds[1]:.4f}] rad "
                f"({math.degrees(agent.ang_bounds[0]):.1f} to {math.degrees(agent.ang_bounds[1]):.1f} deg), "
                f"R={agent.R}",
                flush=True,
            )


def main():
    parser = argparse.ArgumentParser(description="Receive and decode UE Sim Area packets from Henosync.")
    parser.add_argument("--host", default="0.0.0.0", help="interface to listen on (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7000, help="TCP port (must match ue-sim area_port, default 7000)")
    args = parser.parse_args()

    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer((args.host, args.port), _Handler) as server:
        print(f"Listening for Henosync area packets on {args.host}:{args.port} (Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
