"""
TurtleBot3 Burger device plugin for Henosync.

Connects via rosbridge (WebSocket to rosbridge_server).
Positioning:
  - VICON mode: handled entirely by henosync core (vicon_manager). No code here.
  - GPS  mode:  subscribes to /gps/fix via rosbridge.
"""

import asyncio
import logging
import math
import time
from typing import Any, Optional

from henosync_sdk import (
    BatteryData,
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    LocalOrigin,
    Node,
    Position,
    TelemetryFrame,
)
from henosync_sdk.protocols.ros2 import ROS2NodeState, ROS2Plugin

logger = logging.getLogger(__name__)


class _NodeState(ROS2NodeState):
    def __init__(self):
        super().__init__()
        # GPS mode: lat/lon/alt updated by _on_gps; VICON mode: vicon_manager sets node.position
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.gps_received: bool = False
        # Heading from odom — used by goto controller in both positioning modes
        self.heading: float = 0.0
        self.speed: float = 0.0
        self.battery_percent: float = 100.0
        self.last_message_time: float = 0.0  # updated by odom; used by is_connected()
        self.stop_requested: bool = False
        self.cmd_vel_pub: Any = None
        self.nav2_goal_pub: Any = None


class TurtleBot3Plugin(ROS2Plugin):
    PLUGIN_ID = "turtlebot3"
    PLUGIN_NAME = "TurtleBot3 Burger"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "TurtleBot3 Burger via rosbridge — VICON or GPS positioning"

    TELEMETRY_RATE_HZ: float = 2.0
    MESSAGE_TIMEOUT: float = 5.0

    ARRIVAL_THRESHOLD_M: float = 0.30
    MAX_LINEAR_VEL: float = 0.20
    MAX_ANGULAR_VEL: float = 1.50
    LINEAR_GAIN: float = 0.50
    ANGULAR_GAIN: float = 1.50

    def __init__(self):
        super().__init__()

    def create_state(self) -> _NodeState:
        return _NodeState()

    # ── setup_node ─────────────────────────────────────────────────────────────

    async def setup_node(self, node: Node, state: _NodeState, config: dict) -> None:
        ns = config.get("namespace", "").strip("/")
        prefix = f"/{ns}" if ns else ""
        source = config.get("position_source", "vicon")

        selected = set(config.get("selected_capabilities", []))

        capabilities = [
            CapabilitySpec(capability=DeviceCapability.GPS),
            CapabilitySpec(capability=DeviceCapability.MOVE_2D),
            CapabilitySpec(capability=DeviceCapability.BATTERY),
        ]
        if "nav2" in selected:
            capabilities.append(CapabilitySpec(capability=DeviceCapability.NAV2))

        node.specs = DeviceSpecs(
            category=DeviceCategory.AGV,
            capabilities=capabilities,
            coordinate_frame="local" if source == "vicon" else "gps",
        )

        if source == "vicon":
            # Set local_origin so DeviceProxy can convert GPS targets to local coords.
            # Position is published automatically by vicon_manager — nothing more needed.
            node.local_origin = LocalOrigin(
                lat=float(config.get("home_lat") or 0),
                lon=float(config.get("home_lon") or 0),
            )
        else:
            gps_topic = config.get("gps_topic") or f"{prefix}/gps/fix"
            self.subscribe(state, gps_topic, "sensor_msgs/NavSatFix",
                           lambda msg: self._on_gps(node.id, msg))
        self.subscribe(
            state,
            f"{prefix}/odom",
            "nav_msgs/Odometry",
            lambda msg: self._on_odom(node.id, msg),
        )
        self.subscribe(
            state,
            f"{prefix}/battery_state",
            "sensor_msgs/BatteryState",
            lambda msg: self._on_battery(node.id, msg),
        )
        state.cmd_vel_pub = self.advertise(
            state,
            f"{prefix}/cmd_vel",
            "geometry_msgs/TwistStamped",
        )
        if "nav2" in selected:
            nav2_topic = config.get("nav2_goal_topic") or f"{prefix}/move_base_simple/goal"
            state.nav2_goal_pub = self.advertise(
                state, nav2_topic, "geometry_msgs/PoseStamped"
            )
        # Start the liveness clock from connect time so a wrong namespace
        # (topics never publish) triggers DEGRADED within MESSAGE_TIMEOUT seconds.
        state.last_message_time = time.monotonic()

    # ── Topic callbacks ────────────────────────────────────────────────────────

    def _on_gps(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        state.lat = msg.get("latitude", 0.0)
        state.lon = msg.get("longitude", 0.0)
        state.alt = msg.get("altitude", 0.0)
        state.gps_received = True

    def _on_odom(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        state.speed = (
            msg.get("twist", {}).get("twist", {}).get("linear", {}).get("x", 0.0)
        )
        q = msg.get("pose", {}).get("pose", {}).get("orientation", {})
        if q:
            state.heading = self._quat_to_yaw(q)
        state.last_message_time = time.monotonic()

    # TurtleBot3 Burger: 3S Li-Po, 12.6V full, 9.0V empty
    _BATTERY_FULL_V = 12.6
    _BATTERY_EMPTY_V = 9.0

    def _on_battery(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        pct = msg.get("percentage", -1.0)
        if pct > 0.0:
            state.battery_percent = pct if pct > 1.0 else pct * 100.0
        else:
            voltage = msg.get("voltage", 0.0)
            if voltage > 0.0:
                state.battery_percent = max(0.0, min(100.0, (
                    (voltage - self._BATTERY_EMPTY_V)
                    / (self._BATTERY_FULL_V - self._BATTERY_EMPTY_V)
                    * 100.0
                )))

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def build_telemetry(self, node: Node, state: _NodeState, seq: int) -> TelemetryFrame:
        source = node.config.get("position_source", "vicon")
        return TelemetryFrame(
            node_id=node.id,
            sequence_number=seq,
            speed=state.speed,
            battery=BatteryData(percentage=state.battery_percent),
            # GPS mode: include position from /gps/fix subscription
            # VICON mode: vicon_manager publishes position separately; omit here
            position=(
                Position(lat=state.lat, lon=state.lon, alt=state.alt)
                if source == "gps" and state.gps_received
                else None
            ),
            status_text=(
                "Online" if (
                    (source == "vicon" and node.position is not None)
                    or (source == "gps" and state.gps_received)
                )
                else f"Connected — waiting for {'VICON' if source == 'vicon' else 'GPS'}"
            ),
        )

    async def is_connected(self, node: Node) -> bool:
        if not await super().is_connected(node):
            return False
        state = self._nodes.get(node.id)
        if (
            state
            and state.last_message_time > 0
            and time.monotonic() - state.last_message_time > self.MESSAGE_TIMEOUT
        ):
            return False
        return True

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def _quat_to_yaw(q: dict) -> float:
        w, x = q.get("w", 1.0), q.get("x", 0.0)
        y, z = q.get("y", 0.0), q.get("z", 0.0)
        return math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))

    def _publish_nav2_goal(self, state: _NodeState, x: float, y: float) -> None:
        if state.nav2_goal_pub:
            self.publish(state.nav2_goal_pub, {
                "header": {"frame_id": "map"},
                "pose": {
                    "position": {"x": float(x), "y": float(y), "z": 0.0},
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
            })

    def _publish_twist(self, state: _NodeState, linear: float, angular: float) -> None:
        if state.cmd_vel_pub:
            self.publish(state.cmd_vel_pub, {
                "header": {"stamp": {"sec": 0, "nanosec": 0}, "frame_id": ""},
                "twist": {
                    "linear":  {"x": float(linear), "y": 0.0, "z": 0.0},
                    "angular": {"x": 0.0, "y": 0.0, "z": float(angular)},
                },
            })

    # ── Command handlers ───────────────────────────────────────────────────────

    async def cmd_move_to(
        self,
        node: Node,
        lat: float = 0.0,
        lon: float = 0.0,
        alt: float = 0.0,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
        arrival_radius_m: Optional[float] = None,
        max_speed: Optional[float] = None,
    ) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        if node.position is None:
            return CommandResult(success=False, message="No position fix — cannot navigate")

        # VICON mode: DeviceProxy dispatches x/y metres; convert back to GPS
        use_vicon = x is not None and y is not None
        if use_vicon:
            if not node.local_origin:
                return CommandResult(success=False, message="No local_origin set — cannot convert local target")
            _R = 6_371_000.0
            lat = node.local_origin.lat + math.degrees(y / _R)
            lon = node.local_origin.lon + math.degrees(x / (_R * math.cos(math.radians(node.local_origin.lat))))

        threshold = arrival_radius_m if arrival_radius_m is not None else self.ARRIVAL_THRESHOLD_M
        has_nav2 = node.specs and any(
            cs.capability == DeviceCapability.NAV2 for cs in node.specs.capabilities
        )

        logger.info(
            "cmd_move_to: target GPS (%.8f, %.8f) | x=%s y=%s | nav2=%s",
            lat, lon, x, y, has_nav2,
        )

        if has_nav2:
            # ── Nav2 path ────────────────────────────────────────────────────
            if use_vicon:
                goal_x, goal_y = float(x), float(y)
            elif node.local_origin:
                R = 6_371_000.0
                goal_y = R * math.radians(lat - node.local_origin.lat)
                goal_x = R * math.radians(lon - node.local_origin.lon) * math.cos(
                    math.radians(node.local_origin.lat)
                )
            else:
                pos = node.position
                R = 6_371_000.0
                goal_y = R * math.radians(lat - pos.lat)
                goal_x = R * math.radians(lon - pos.lon) * math.cos(math.radians(pos.lat))

            self._publish_nav2_goal(state, goal_x, goal_y)
            state.stop_requested = False
            try:
                while node.id in self._nodes and state.connected:
                    if state.stop_requested:
                        state.stop_requested = False
                        return CommandResult(success=False, message="Stopped")
                    pos = node.position
                    if pos is None:
                        await asyncio.sleep(0.1)
                        continue
                    R = 6_371_000.0
                    dy = R * math.radians(lat - pos.lat)
                    dx = R * math.radians(lon - pos.lon) * math.cos(math.radians(pos.lat))
                    if math.sqrt(dx * dx + dy * dy) < threshold:
                        return CommandResult(success=True, message="Arrived")
                    await asyncio.sleep(0.1)
                return CommandResult(success=False, message="Navigation aborted")
            finally:
                pass  # Nav2 keeps navigating until a new goal arrives

        else:
            # ── Proportional velocity controller ─────────────────────────────
            speed_cap = self.MAX_LINEAR_VEL if max_speed is None else min(float(max_speed), self.MAX_LINEAR_VEL)
            state.stop_requested = False
            _tick = 0
            try:
                while node.id in self._nodes and state.connected:
                    if state.stop_requested:
                        state.stop_requested = False
                        return CommandResult(success=False, message="Stopped")

                    pos = node.position
                    if pos is None:
                        await asyncio.sleep(0.1)
                        continue

                    R = 6_371_000.0
                    dy = R * math.radians(lat - pos.lat)
                    dx = R * math.radians(lon - pos.lon) * math.cos(math.radians(pos.lat))
                    distance = math.sqrt(dx * dx + dy * dy)

                    if distance < threshold:
                        return CommandResult(success=True, message="Arrived")

                    bearing = math.atan2(dy, dx)
                    heading = (
                        pos.heading if (use_vicon and pos.heading is not None)
                        else state.heading
                    )
                    heading_error = math.atan2(
                        math.sin(bearing - heading),
                        math.cos(bearing - heading),
                    )
                    linear = min(
                        speed_cap,
                        self.LINEAR_GAIN * distance * max(0.0, math.cos(heading_error)),
                    )
                    angular = max(
                        -self.MAX_ANGULAR_VEL,
                        min(self.MAX_ANGULAR_VEL, self.ANGULAR_GAIN * heading_error),
                    )

                    _tick += 1
                    if _tick % 10 == 1:
                        logger.info(
                            "goto | pos (%.8f, %.8f) heading=%.3f(pos) %.3f(odom) | "
                            "target (%.8f, %.8f) | dist=%.3fm bearing=%.3f | "
                            "err=%.3f lin=%.3f ang=%.3f",
                            pos.lat, pos.lon,
                            pos.heading if pos.heading is not None else float("nan"),
                            state.heading,
                            lat, lon,
                            distance, bearing,
                            heading_error, linear, angular,
                        )

                    self._publish_twist(state, linear, angular)
                    await asyncio.sleep(0.1)

                return CommandResult(success=False, message="Navigation aborted")
            finally:
                self._publish_twist(state, 0.0, 0.0)

    async def cmd_stop(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        state.stop_requested = True
        self._publish_twist(state, 0.0, 0.0)
        return CommandResult(success=True, message="Stopped")

    async def cmd_return_home(self, node: Node) -> CommandResult:
        if node.home_position:
            return await self.cmd_move_to(
                node, node.home_position.lat, node.home_position.lon
            )
        return CommandResult(success=False, message="No home position set")

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        if envelope.command_type != "cmd_vel":
            return CommandResult(
                success=False, message=f"Unknown command: {envelope.command_type}"
            )
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # Negate angular: teleop right=+1, ROS angular.z positive=CCW=left
        linear = max(
            -self.MAX_LINEAR_VEL,
            min(self.MAX_LINEAR_VEL,
                float(envelope.params.get("linear", 0.0)) * self.MAX_LINEAR_VEL),
        )
        angular = max(
            -self.MAX_ANGULAR_VEL,
            min(self.MAX_ANGULAR_VEL,
                -float(envelope.params.get("angular", 0.0)) * self.MAX_ANGULAR_VEL),
        )
        state.stop_requested = True
        self._publish_twist(state, linear, angular)
        return CommandResult(success=True, message="cmd_vel sent")

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state:
            state.stop_requested = True
            self._publish_twist(state, 0.0, 0.0)
        return CommandResult(success=True, message="Stopped")
