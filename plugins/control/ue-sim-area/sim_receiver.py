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
import random
import time
import socketserver
import cosysairsim as airsim

REQUIRED_KEYS = ("angle_1", "angle_2", "radius", "ag_id", "nag", "envi_type")
SUPPORTED_ENVS = ("Circular",)  # RegularPolygons crashes coverage_fns after 10 interactions

# ── Sim connection settings ───────────────────────────────────────────────────
AIRSIM_HOST = "192.168.0.136"       # IP of the machine running the Unreal Engine sim
VEHICLE_NAMES = ["Car1", "Car2", "Car3"]  # AirSim vehicle names indexed by ag_id - 1


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


def random_waypoint(agent):
    """
    Return a uniformly random (x_m, y_m) within the agent's sector.

    Uses sqrt(uniform) for the radius so the distribution is uniform over area
    (not biased toward the centre).  The returned coordinates are in the same
    frame as the VICON arena: origin at the arena centre, units in metres.

    Usage after decode_packet():
        agent = decode_packet(line)
        x_m, y_m = random_waypoint(agent)
        # pass (x_m, y_m) to the sim velocity controller
    """
    th1 = agent.ang_bounds[0]
    th2 = agent.ang_bounds[1]
    if th2 <= th1:          # sector wraps through 0
        th2 += 2 * math.pi
    theta = random.uniform(th1, th2)
    r = agent.R * math.sqrt(random.random())
    return r * math.cos(theta), r * math.sin(theta)


# ── Velocity controller ──────────────────────────────────────────────────────

CTRL_HZ = 10.0          # control loop rate (Hz)
ARRIVAL_RADIUS_M = 1.0  # stop when within this distance of the goal (metres)
MAX_THROTTLE = 0.5      # caps throttle (0–1)
MIN_THROTTLE = 0.15     # minimum throttle while driving — keeps car moving while turning
STEERING_GAIN = 0.8     # heading_error (rad) → steering (−1..1)
THROTTLE_GAIN = 0.3     # distance (m) → throttle, scaled by cos(heading_error)


def car_controls(goal_x, goal_y, pos_x, pos_y, yaw_rad):
    """
    Compute AirSim CarControls to steer toward (goal_x, goal_y).

    All coordinates must be in the same flat frame (e.g. AirSim NED metres:
    x=North, y=East).  yaw_rad is the vehicle heading in that frame
    (0 = +X/North, counter-clockwise positive).

    Returns
    -------
    controls : airsim.CarControls
    arrived  : bool — True when within ARRIVAL_RADIUS_M
    """
    dx = goal_x - pos_x
    dy = goal_y - pos_y
    distance = math.sqrt(dx * dx + dy * dy)

    controls = airsim.CarControls()
    if distance < ARRIVAL_RADIUS_M:
        controls.throttle = 0.0
        controls.brake = 1.0
        return controls, True

    bearing = math.atan2(dy, dx)
    heading_error = math.atan2(
        math.sin(bearing - yaw_rad),
        math.cos(bearing - yaw_rad),
    )

    controls.steering = max(-1.0, min(1.0, STEERING_GAIN * heading_error))
    # Always apply at least MIN_THROTTLE so the car moves while turning to correct heading.
    forward = max(0.0, math.cos(heading_error))
    controls.throttle = min(MAX_THROTTLE, max(MIN_THROTTLE, THROTTLE_GAIN * distance * forward))
    controls.brake = 0.0
    return controls, False


def run_to_waypoint(vehicle_name, goal_x, goal_y, timeout_s=60.0):
    """
    Connect to AirSim, drive vehicle_name to (goal_x, goal_y), then stop.

    Blocks until within ARRIVAL_RADIUS_M or timeout_s elapses.
    goal_x/goal_y must be in AirSim NED metres (x=North, y=East).

    If your goal comes from random_waypoint() (VICON arena frame), apply any
    rotational offset between the arena origin and the AirSim world origin
    before passing the coordinates here — the scale is the same (1 m = 1 m)
    but the axis alignment depends on how the sim was set up.
    """
    client = airsim.CarClient(ip=AIRSIM_HOST)
    print(f"[{vehicle_name}] CarClient created, confirming connection...", flush=True)
    client.confirmConnection()
    print(f"[{vehicle_name}] connected, enabling API control...", flush=True)
    client.enableApiControl(True, vehicle_name)
    print(f"[{vehicle_name}] API control enabled, starting control loop toward ({goal_x:.2f}, {goal_y:.2f})", flush=True)

    dt = 1.0 / CTRL_HZ
    deadline = time.monotonic() + timeout_s
    tick = 0

    while time.monotonic() < deadline:
        state = client.getCarState(vehicle_name)
        pos = state.kinematics_estimated.position
        q = state.kinematics_estimated.orientation
        yaw = math.atan2(
            2.0 * (q.w_val * q.z_val + q.x_val * q.y_val),
            1.0 - 2.0 * (q.y_val * q.y_val + q.z_val * q.z_val),
        )

        controls, arrived = car_controls(goal_x, goal_y, pos.x_val, pos.y_val, yaw)
        if tick % 10 == 0:
            dx = goal_x - pos.x_val
            dy = goal_y - pos.y_val
            dist = math.sqrt(dx * dx + dy * dy)
            print(
                f"[{vehicle_name}] tick={tick} pos=({pos.x_val:.2f},{pos.y_val:.2f}) "
                f"yaw={math.degrees(yaw):.1f}° dist={dist:.2f}m "
                f"throttle={controls.throttle:.2f} steering={controls.steering:.2f}",
                flush=True,
            )
        client.setCarControls(controls, vehicle_name)
        tick += 1

        if arrived:
            print(f"[{vehicle_name}] arrived at ({goal_x:.2f}, {goal_y:.2f})", flush=True)
            break

        time.sleep(dt)
    else:
        print(f"[{vehicle_name}] timeout reaching ({goal_x:.2f}, {goal_y:.2f})", flush=True)
        stop = airsim.CarControls()
        stop.brake = 1.0
        client.setCarControls(stop, vehicle_name)

    client.enableApiControl(False, vehicle_name)


# ── TCP packet handler ────────────────────────────────────────────────────────

import threading


def _drive_vehicle(vehicle, x_m, y_m):
    """Drive one vehicle to its waypoint — runs in its own thread."""
    print(f"[{vehicle}] connecting to AirSim at {AIRSIM_HOST}...", flush=True)
    try:
        run_to_waypoint(vehicle, x_m, y_m)
    except Exception as e:
        import traceback
        print(f"[{vehicle}] controller error: {e}", flush=True)
        traceback.print_exc()


class _Handler(socketserver.StreamRequestHandler):
    # Henosync sends all agent lines on one TCP connection — spawn a thread per
    # car so they drive concurrently instead of sequentially.
    def handle(self):
        threads = []
        packet_count = 0
        for line in self.rfile:
            if not line.strip():
                continue
            packet_count += 1
            print(f"[receiver] packet {packet_count} raw: {line.strip()[:120]}", flush=True)
            try:
                agent = decode_packet(line)
            except PacketError as e:
                print(f"[{self.client_address[0]}] rejected packet: {e}", flush=True)
                continue
            x_m, y_m = random_waypoint(agent)
            vehicle = VEHICLE_NAMES[agent.id - 1]
            print(
                f"[{self.client_address[0]}] agent {agent.id}/{agent.nag} ({agent.env}) "
                f"ang_bounds=[{agent.ang_bounds[0]:.4f}, {agent.ang_bounds[1]:.4f}] rad "
                f"({math.degrees(agent.ang_bounds[0]):.1f}° to {math.degrees(agent.ang_bounds[1]):.1f}°), "
                f"R={agent.R}  →  waypoint ({x_m:.3f}, {y_m:.3f}) m  →  spawning thread for {vehicle}",
                flush=True,
            )
            t = threading.Thread(target=_drive_vehicle, args=(vehicle, x_m, y_m), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join()


def main():
    parser = argparse.ArgumentParser(description="Receive and decode UE Sim Area packets from Henosync.")
    parser.add_argument("--host", default="0.0.0.0", help="interface to listen on (default 0.0.0.0)")
    parser.add_argument("--port", type=int, default=7000, help="Base TCP port; Car1=port, Car2=port+1, Car3=port+2 (default 7000)")
    args = parser.parse_args()

    socketserver.TCPServer.allow_reuse_address = True
    servers = []
    for i, vehicle in enumerate(VEHICLE_NAMES):
        port = args.port + i
        server = socketserver.TCPServer((args.host, port), _Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        servers.append(server)
        print(f"Listening for {vehicle} on {args.host}:{port}", flush=True)

    print("All listeners started (Ctrl+C to stop)", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        for server in servers:
            server.shutdown()


if __name__ == "__main__":
    main()
