"""
UE Sim Area — sim-side packet decoder.

Runs on the Unreal Engine sim machine, NOT inside Henosync. Place this file
next to coverage_fns.py.

Henosync's "UE Sim Area" mission step sends one newline-terminated JSON line
per robot over TCP (one port per vehicle: base_port, base_port+1, base_port+2):

    {"angle_1": 0.0, "angle_2": 6.2814, "radius": 50.0,
     "ag_id": 1, "nag": 1, "envi_type": "Circular"}

Angles are radians in [0, 2π), counter-clockwise from angle_1 to angle_2
(angle_2 < angle_1 means the sector wraps through 0). This script decodes the
packet into a coverage_fns.Agents object:

    angle_1, angle_2  -> ang_bounds
    radius            -> R
    ag_id, nag, envi_type -> passed through unchanged

After decoding, each vehicle runs a continuous coverage loop:
  1. Generate a random waypoint within its current angular sector.
  2. Drive there using the proportional velocity controller.
  3. On arrival, check if any other vehicle is within INTERACTION_RADIUS_M.
  4. If so (and cooldown has elapsed), call BilateralInteraction on both —
     which redistributes their angular sectors equally — then generate a new
     waypoint and repeat.

Use from your own sim code:

    from sim_receiver import decode_packet, random_waypoint
    agent = decode_packet(line)
    x_m, y_m = random_waypoint(agent)

Or run standalone:

    python sim_receiver.py              # listens on 0.0.0.0:7000/7001/7002
    python sim_receiver.py --port 7000

Requires: cosysairsim, coverage_fns.py (numpy, shapely, matplotlib).
"""

import argparse
import json
import math
import random
import time
import socketserver
import threading

import cosysairsim as airsim

REQUIRED_KEYS = ("angle_1", "angle_2", "radius", "ag_id", "nag", "envi_type")
SUPPORTED_ENVS = ("Circular",)  # RegularPolygons crashes coverage_fns after 10 interactions

# ── Sim connection settings ───────────────────────────────────────────────────
AIRSIM_HOST = "192.168.0.136"        # IP of the machine running the Unreal Engine sim
VEHICLE_NAMES = ["Car1", "Car2", "Car3"]  # AirSim vehicle names indexed by ag_id - 1

# ── Velocity controller constants ─────────────────────────────────────────────
CTRL_HZ = 10.0          # control loop rate (Hz)
ARRIVAL_RADIUS_M = 1.0  # stop when within this distance of the goal (metres)
MAX_THROTTLE = 0.5      # caps throttle (0–1)
MIN_THROTTLE = 0.15     # minimum throttle while driving — keeps car moving while turning
STEERING_GAIN = 0.8     # heading_error (rad) → steering (−1..1)
THROTTLE_GAIN = 0.3     # distance (m) → throttle, scaled by cos(heading_error)

# ── Bilateral interaction constants ───────────────────────────────────────────
# When two vehicles come within this distance, BilateralInteraction is triggered.
INTERACTION_RADIUS_M = 5.0
# Minimum seconds between interactions for the same pair of vehicles — prevents
# repeated firing while two vehicles remain close together.
INTERACTION_COOLDOWN_S = 15.0

# ── Shared vehicle state (thread-safe via _registry_lock) ─────────────────────
_agent_registry: dict = {}      # vehicle_name -> Agents object
_position_registry: dict = {}   # vehicle_name -> (x, y) in AirSim NED metres
_last_interaction: dict = {}    # frozenset({v1, v2}) -> monotonic time of last interaction
_registry_lock = threading.Lock()

# Tracks which vehicles have an active coverage loop so we ignore duplicate packets.
_active_loops: set = set()
_active_loops_lock = threading.Lock()


# ── Packet parsing ────────────────────────────────────────────────────────────

class PacketError(ValueError):
    """Raised when a packet is malformed or has invalid values."""


def parse_packet(line):
    """Validate one packet and return keyword arguments for coverage_fns.Agents."""
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


# ── Waypoint generation ───────────────────────────────────────────────────────

def random_waypoint(agent):
    """
    Return a uniformly random (x_m, y_m) within the agent's current sector.

    Uses sqrt(uniform) for the radius so the distribution is uniform over area
    (not biased toward the centre).  The returned coordinates are in the same
    frame as the AirSim NED world (x=North, y=East, metres from origin).

    Caller must hold _registry_lock if agent.ang_bounds may be concurrently
    modified by BilateralInteraction.
    """
    th1 = agent.ang_bounds[0]
    th2 = agent.ang_bounds[1]
    if th2 <= th1:          # sector wraps through 0
        th2 += 2 * math.pi
    theta = random.uniform(th1, th2)
    r = agent.R * math.sqrt(random.random())
    return r * math.cos(theta), r * math.sin(theta)


# ── Velocity controller ───────────────────────────────────────────────────────

def car_controls(goal_x, goal_y, pos_x, pos_y, yaw_rad):
    """
    Compute AirSim CarControls to steer toward (goal_x, goal_y).

    All coordinates must be in the same flat frame (AirSim NED metres:
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
    # Always apply at least MIN_THROTTLE so the car moves while turning.
    forward = max(0.0, math.cos(heading_error))
    controls.throttle = min(MAX_THROTTLE, max(MIN_THROTTLE, THROTTLE_GAIN * distance * forward))
    controls.brake = 0.0
    return controls, False


def run_to_waypoint(vehicle_name, goal_x, goal_y, timeout_s=60.0):
    """
    Standalone: connect to AirSim, drive vehicle_name to (goal_x, goal_y), then stop.

    Blocks until within ARRIVAL_RADIUS_M or timeout_s elapses.
    Does NOT update the shared position registry — use the coverage loop instead.
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


# ── Coverage loop ─────────────────────────────────────────────────────────────

def _drive_to(client, vehicle: str, goal_x: float, goal_y: float, timeout_s: float = 60.0) -> None:
    """
    Drive vehicle to (goal_x, goal_y) using an existing AirSim client.

    Updates _position_registry on every tick so the interaction monitor has
    fresh positions. Blocks until arrival or timeout.
    """
    print(f"[{vehicle}] heading to ({goal_x:.2f}, {goal_y:.2f})", flush=True)
    dt = 1.0 / CTRL_HZ
    deadline = time.monotonic() + timeout_s
    tick = 0

    while time.monotonic() < deadline:
        state = client.getCarState(vehicle)
        pos = state.kinematics_estimated.position
        q = state.kinematics_estimated.orientation
        yaw = math.atan2(
            2.0 * (q.w_val * q.z_val + q.x_val * q.y_val),
            1.0 - 2.0 * (q.y_val * q.y_val + q.z_val * q.z_val),
        )

        with _registry_lock:
            _position_registry[vehicle] = (pos.x_val, pos.y_val)

        controls, arrived = car_controls(goal_x, goal_y, pos.x_val, pos.y_val, yaw)
        if tick % 10 == 0:
            dx = goal_x - pos.x_val
            dy = goal_y - pos.y_val
            dist = math.sqrt(dx * dx + dy * dy)
            print(
                f"[{vehicle}] tick={tick} pos=({pos.x_val:.2f},{pos.y_val:.2f}) "
                f"yaw={math.degrees(yaw):.1f}° dist={dist:.2f}m "
                f"throttle={controls.throttle:.2f} steering={controls.steering:.2f}",
                flush=True,
            )
        client.setCarControls(controls, vehicle)
        tick += 1

        if arrived:
            print(f"[{vehicle}] arrived at ({goal_x:.2f}, {goal_y:.2f})", flush=True)
            return

        time.sleep(dt)

    print(f"[{vehicle}] timeout reaching ({goal_x:.2f}, {goal_y:.2f})", flush=True)
    stop = airsim.CarControls()
    stop.brake = 1.0
    client.setCarControls(stop, vehicle)


def _check_and_interact(vehicle: str) -> None:
    """
    After arrival, check if any other vehicle is within INTERACTION_RADIUS_M.

    If so (and the cooldown for that pair has elapsed), call BilateralInteraction
    on both agents — which redistributes their angular sectors equally — then log
    the updated bounds.

    Both agents' ang_bounds are captured BEFORE either is updated so the exchange
    is symmetric (agent_i sees agent_j's old sector, and vice versa).

    All mutation of agent state and the interaction timestamp happens under
    _registry_lock so concurrent threads can't double-interact.
    """
    now = time.monotonic()

    with _registry_lock:
        my_pos = _position_registry.get(vehicle)
        my_agent = _agent_registry.get(vehicle)
        if my_pos is None or my_agent is None:
            return

        for other_vehicle in VEHICLE_NAMES:
            if other_vehicle == vehicle:
                continue
            other_pos = _position_registry.get(other_vehicle)
            other_agent = _agent_registry.get(other_vehicle)
            if other_pos is None or other_agent is None:
                continue

            dx = my_pos[0] - other_pos[0]
            dy = my_pos[1] - other_pos[1]
            dist = math.sqrt(dx * dx + dy * dy)

            if dist > INTERACTION_RADIUS_M:
                continue

            pair = frozenset({vehicle, other_vehicle})
            last = _last_interaction.get(pair, 0.0)
            if now - last < INTERACTION_COOLDOWN_S:
                print(
                    f"[interaction] {vehicle} ↔ {other_vehicle} within {dist:.2f}m "
                    f"but cooldown ({INTERACTION_COOLDOWN_S:.0f}s) not elapsed — skipping",
                    flush=True,
                )
                continue

            # Snapshot both sectors BEFORE updating either (symmetric exchange).
            bounds_mine = list(my_agent.ang_bounds)
            bounds_other = list(other_agent.ang_bounds)

            print(
                f"[interaction] {vehicle} ↔ {other_vehicle} at {dist:.2f}m "
                f"— calling BilateralInteraction",
                flush=True,
            )
            print(
                f"  {vehicle}       before: [{math.degrees(bounds_mine[0]):.1f}°, "
                f"{math.degrees(bounds_mine[1]):.1f}°]",
                flush=True,
            )
            print(
                f"  {other_vehicle} before: [{math.degrees(bounds_other[0]):.1f}°, "
                f"{math.degrees(bounds_other[1]):.1f}°]",
                flush=True,
            )

            my_agent.BilateralInteraction(other_agent.id, bounds_other)
            other_agent.BilateralInteraction(my_agent.id, bounds_mine)
            _last_interaction[pair] = now

            print(
                f"  {vehicle}       after:  [{math.degrees(my_agent.ang_bounds[0]):.1f}°, "
                f"{math.degrees(my_agent.ang_bounds[1]):.1f}°]",
                flush=True,
            )
            print(
                f"  {other_vehicle} after:  [{math.degrees(other_agent.ang_bounds[0]):.1f}°, "
                f"{math.degrees(other_agent.ang_bounds[1]):.1f}°]",
                flush=True,
            )


def _run_vehicle_loop(vehicle: str, agent) -> None:
    """
    Continuous coverage loop for one vehicle.

    Registers the agent in the shared registry, opens one persistent AirSim
    connection, then repeats:
        1. Sample a random waypoint from the current angular sector.
        2. Drive there (ticking the shared position registry on every control step).
        3. Check proximity to all other vehicles and trigger BilateralInteraction
           when within INTERACTION_RADIUS_M (with cooldown).
    """
    with _active_loops_lock:
        if vehicle in _active_loops:
            print(f"[{vehicle}] coverage loop already running — ignoring duplicate packet", flush=True)
            return
        _active_loops.add(vehicle)

    with _registry_lock:
        _agent_registry[vehicle] = agent

    print(
        f"[{vehicle}] starting coverage loop  "
        f"bounds=[{math.degrees(agent.ang_bounds[0]):.1f}°, "
        f"{math.degrees(agent.ang_bounds[1]):.1f}°]  R={agent.R}",
        flush=True,
    )

    client = airsim.CarClient(ip=AIRSIM_HOST)
    try:
        client.confirmConnection()
        client.enableApiControl(True, vehicle)
        print(f"[{vehicle}] connected to AirSim, API control enabled", flush=True)

        while True:
            # Sample waypoint under lock so BilateralInteraction can't race with us.
            with _registry_lock:
                x_m, y_m = random_waypoint(agent)

            print(
                f"[{vehicle}] new waypoint ({x_m:.2f}, {y_m:.2f})  "
                f"bounds=[{math.degrees(agent.ang_bounds[0]):.1f}°, "
                f"{math.degrees(agent.ang_bounds[1]):.1f}°]",
                flush=True,
            )

            _drive_to(client, vehicle, x_m, y_m)
            _check_and_interact(vehicle)

    except Exception as e:
        import traceback
        print(f"[{vehicle}] coverage loop error: {e}", flush=True)
        traceback.print_exc()
    finally:
        try:
            stop = airsim.CarControls()
            stop.brake = 1.0
            client.setCarControls(stop, vehicle)
            client.enableApiControl(False, vehicle)
        except Exception:
            pass
        with _registry_lock:
            _agent_registry.pop(vehicle, None)
            _position_registry.pop(vehicle, None)
        with _active_loops_lock:
            _active_loops.discard(vehicle)
        print(f"[{vehicle}] coverage loop ended", flush=True)


# ── TCP packet handler ────────────────────────────────────────────────────────

class _Handler(socketserver.StreamRequestHandler):
    """
    One handler per incoming TCP connection (one per vehicle port per mission start).

    Reads one JSON packet, decodes it into an Agents object, and starts the
    continuous coverage loop for that vehicle in a daemon thread. Does NOT join
    the thread — the loop runs until the process exits (Ctrl+C).
    """
    def handle(self):
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

            vehicle = VEHICLE_NAMES[agent.id - 1]
            print(
                f"[{self.client_address[0]}] agent {agent.id}/{agent.nag} ({agent.env}) "
                f"ang_bounds=[{math.degrees(agent.ang_bounds[0]):.1f}°, "
                f"{math.degrees(agent.ang_bounds[1]):.1f}°]  R={agent.R}  →  {vehicle}",
                flush=True,
            )

            t = threading.Thread(target=_run_vehicle_loop, args=(vehicle, agent), daemon=True)
            t.start()


def main():
    parser = argparse.ArgumentParser(description="Receive and decode UE Sim Area packets from Henosync.")
    parser.add_argument("--host", default="0.0.0.0", help="interface to listen on (default 0.0.0.0)")
    parser.add_argument(
        "--port", type=int, default=7000,
        help="Base TCP port; Car1=port, Car2=port+1, Car3=port+2 (default 7000)",
    )
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

    print(
        f"All listeners started — BilateralInteraction triggers when any two cars "
        f"come within {INTERACTION_RADIUS_M:.1f}m (cooldown {INTERACTION_COOLDOWN_S:.0f}s). "
        f"Ctrl+C to stop.",
        flush=True,
    )
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        for server in servers:
            server.shutdown()


if __name__ == "__main__":
    main()
