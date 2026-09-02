"""
Henosync Device Plugin Template
================================
Choose the starter that matches your robot's communication protocol,
then implement the required methods.

  ROS2 / rosbridge  →  subclass ROS2Plugin      (most ground robots, ROS2 sim)
  MAVLink           →  subclass MAVLinkPlugin    (PX4/ArduPilot drones, ArduRover)
  Other protocol    →  subclass NodePlugin       (HTTP, MQTT, custom UDP, …)

Steps:
  1. Delete the starter you are NOT using (keep only one class).
  2. Rename MyRobotPlugin and set PLUGIN_ID to match manifest.json id.
  3. Implement setup_node(), build_telemetry(), get_safe_state().
  4. Add command handlers your manifest declares (cmd_move_to, etc.).
  5. Update manifest.json with your robot's details.

Positioning:
  - VICON: configured automatically by henosync core (vicon_manager).
            In setup_node(), just set node.local_origin from config — done.
  - GPS:   subscribe to the /gps/fix topic in setup_node() and update state.
"""

# ──────────────────────────────────────────────────────────────────────────────
# Common SDK imports — use what you need, delete the rest
# ──────────────────────────────────────────────────────────────────────────────

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

import logging

logger = logging.getLogger(__name__)


# ==============================================================================
# OPTION A — ROS2 / rosbridge
# Use this for: TurtleBot, Jackal, Husky, any robot running rosbridge_server,
#               or ROS2 simulation environments.
# Delete this section if you are using MAVLink or a custom protocol.
# ==============================================================================

from henosync_sdk.protocols.ros2 import ROS2NodeState, ROS2Plugin


class _NodeState(ROS2NodeState):
    """
    Per-node state. Add your robot's data fields here.
    GPS mode: add lat/lon/alt/gps_received to track the subscription.
    VICON mode: no position fields needed — vicon_manager updates node.position.
    """

    def __init__(self):
        super().__init__()
        # GPS mode fields (delete if using VICON only):
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.gps_received: bool = False
        # TODO: add your robot's own data fields:
        self.speed: float = 0.0
        self.battery_percent: float = 100.0
        self.cmd_vel_pub = None  # store publishers here so command handlers can reach them


class MyRobotPlugin(ROS2Plugin):
    """Replace MyRobotPlugin with your robot's name."""

    PLUGIN_ID      = "my-robot"        # must match manifest.json id
    PLUGIN_NAME    = "My Robot"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR  = "Your Name"
    PLUGIN_DESCRIPTION = "Plugin for My Robot"

    TELEMETRY_RATE_HZ: float = 2.0

    def __init__(self):
        super().__init__()

    def create_state(self) -> _NodeState:
        return _NodeState()

    # ── Required: called immediately after rosbridge connects ──────────────────

    async def setup_node(self, node: Node, state: _NodeState, config: dict) -> None:
        """
        Set node.specs, subscribe to topics, create publishers.
        Raise an exception here to abort the connection with a reason message.
        """
        source = config.get("position_source", "gps")
        ns = config.get("namespace", "").strip("/")

        node.specs = DeviceSpecs(
            category=DeviceCategory.AGV,        # TODO: change to your robot's category
            capabilities=[
                CapabilitySpec(capability=DeviceCapability.GPS),
                CapabilitySpec(capability=DeviceCapability.BATTERY),
                # TODO: add capabilities your robot has:
                # CapabilitySpec(capability=DeviceCapability.MOVE_2D),
            ],
            coordinate_frame="local" if source == "vicon" else "gps",
        )

        if source == "vicon":
            # VICON: set local_origin so DeviceProxy can convert GPS targets to
            # local coords for navigation. Position itself is published by
            # henosync core (vicon_manager) — nothing else needed here.
            node.local_origin = LocalOrigin(
                lat=float(config.get("home_lat") or 0),
                lon=float(config.get("home_lon") or 0),
            )
        else:
            # GPS: subscribe to the NavSatFix topic and write to state.
            gps_topic = config.get("gps_topic") or (
                f"{ns}/gps/fix" if ns else "/gps/fix"
            )
            self.subscribe(state, gps_topic, "sensor_msgs/NavSatFix",
                           lambda msg: self._on_gps(node.id, msg))

        # TODO: subscribe to robot-specific topics
        # self.subscribe(state, f"{ns}/odom" if ns else "/odom",
        #                "nav_msgs/Odometry",
        #                lambda msg: self._on_odom(node.id, msg))
        # self.subscribe(state, f"{ns}/battery_state" if ns else "/battery_state",
        #                "sensor_msgs/BatteryState",
        #                lambda msg: self._on_battery(node.id, msg))

        # TODO: create publishers for topics you need to write to
        # state.cmd_vel_pub = self.advertise(
        #     state, f"{ns}/cmd_vel" if ns else "/cmd_vel", "geometry_msgs/Twist"
        # )

    # ── Required: return a TelemetryFrame from current state ──────────────────

    def build_telemetry(self, node: Node, state: _NodeState, seq: int) -> TelemetryFrame:
        """Sync — read state fields and return a TelemetryFrame. No awaits here."""
        source = node.config.get("position_source", "gps")
        return TelemetryFrame(
            node_id=node.id,
            sequence_number=seq,
            speed=state.speed,
            battery=BatteryData(percentage=state.battery_percent),
            # GPS mode: include position from subscription
            # VICON mode: vicon_manager publishes position; omit here to avoid conflict
            position=(
                Position(lat=state.lat, lon=state.lon, alt=state.alt)
                if source == "gps" and state.gps_received
                else None
            ),
        )

    # ── Required: make the robot safe ─────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        """Called on heartbeat loss or emergency stop. Stop the robot here."""
        state = self._nodes.get(node.id)
        if state and state.cmd_vel_pub:
            self.publish(state.cmd_vel_pub, {
                "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
            })
        return CommandResult(success=True, message="Stopped")

    # ── Topic callbacks (run on Twisted thread — no awaits) ───────────────────

    def _on_gps(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        state.lat = msg.get("latitude", 0.0)
        state.lon = msg.get("longitude", 0.0)
        state.alt = msg.get("altitude", 0.0)
        state.gps_received = True

    # TODO: add callbacks for your robot's other topics
    # def _on_odom(self, node_id: str, msg: dict) -> None:
    #     state = self._nodes.get(node_id)
    #     if not state:
    #         return
    #     state.speed = msg.get("twist", {}).get("twist", {}).get("linear", {}).get("x", 0.0)

    # ── Command handlers (add the ones your manifest declares) ────────────────

    async def cmd_move_to(
        self,
        node: Node,
        lat: float = 0.0,
        lon: float = 0.0,
        alt: float = 0.0,
        x: Optional[float] = None,
        y: Optional[float] = None,
        z: Optional[float] = None,
    ) -> CommandResult:
        """
        x/y/z (local metres) are populated instead of lat/lon/alt when this
        device's coordinate_frame is "local" (VICON mode) — DeviceProxy
        converts the WGS84 target before dispatch. Branch on `x is not None`.
        """
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # node.position is set by vicon_manager (VICON) or telemetry pipeline (GPS).
        if node.position is None:
            return CommandResult(success=False, message="No position fix — cannot navigate")
        # TODO: send navigation command to robot
        return CommandResult(success=True, message=f"Moving to {lat:.5f}, {lon:.5f}, alt={alt:.1f}m")

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # TODO: handle custom commands declared in manifest.json
        # Example: cmd_vel for teleop
        # if envelope.command_type == "cmd_vel":
        #     linear  = envelope.params.get("linear",  0.0)
        #     angular = envelope.params.get("angular", 0.0)
        #     self.publish(state.cmd_vel_pub, { ... })
        #     return CommandResult(success=True, message="cmd_vel sent")
        return CommandResult(
            success=False, message=f"Unknown command: {envelope.command_type}"
        )


# ==============================================================================
# OPTION B — MAVLink (PX4 / ArduPilot)
# Use this for: drones, ArduRover ground vehicles, any MAVLink device over WiFi.
# Connect the device to Henosync via UDP (no companion computer required if the
# flight controller has WiFi).
# Delete this section if you are using ROS2.
#
# VICON positioning works with MAVLink devices: vicon_manager is protocol-agnostic.
# GPS positioning in MAVLink mode: register a GLOBAL_POSITION_INT handler and
# write to state.lat/lon/alt directly (shown below).
# ==============================================================================

# from henosync_sdk.protocols.mavlink import MAVLinkNodeState, MAVLinkPlugin
#
# class _State(MAVLinkNodeState):
#     def __init__(self):
#         super().__init__()
#         self.lat: float = 0.0
#         self.lon: float = 0.0
#         self.alt: float = 0.0
#         self.gps_received: bool = False
#         self.battery: float = 100.0
#
#
# class MyDronePlugin(MAVLinkPlugin):
#     PLUGIN_ID      = "my-drone"
#     PLUGIN_NAME    = "My Drone"
#     PLUGIN_VERSION = "0.1.0"
#     PLUGIN_AUTHOR  = "Your Name"
#
#     TELEMETRY_RATE_HZ: float = 2.0
#
#     def __init__(self):
#         super().__init__()
#
#     def create_state(self):
#         return _State()
#
#     async def setup_node(self, node, state, config):
#         source = config.get("position_source", "vicon")
#         node.specs = DeviceSpecs(
#             category=DeviceCategory.DRONE,
#             capabilities=[
#                 CapabilitySpec(capability=DeviceCapability.GPS),
#                 CapabilitySpec(capability=DeviceCapability.BATTERY),
#                 CapabilitySpec(capability=DeviceCapability.MOVE_3D),
#             ],
#             coordinate_frame="local" if source == "vicon" else "gps",
#         )
#         if source == "vicon":
#             node.local_origin = LocalOrigin(
#                 lat=float(config.get("home_lat", 0.0)),
#                 lon=float(config.get("home_lon", 0.0)),
#             )
#         else:
#             self.register_handler(state, "GLOBAL_POSITION_INT", self._on_position)
#             self.request_message_interval(state, 33, 100_000)  # 10 Hz
#         self.register_handler(state, "BATTERY_STATUS", self._on_battery)
#         self.request_message_interval(state, 147, 1_000_000)   # 1 Hz
#
#     def _on_position(self, state, msg):
#         state.lat = msg.lat / 1e7
#         state.lon = msg.lon / 1e7
#         state.alt = msg.relative_alt / 1000.0
#         state.gps_received = True
#
#     def _on_battery(self, state, msg):
#         state.battery = msg.battery_remaining
#
#     def build_telemetry(self, node, state, seq):
#         source = node.config.get("position_source", "vicon")
#         return TelemetryFrame(
#             node_id=node.id,
#             sequence_number=seq,
#             position=(
#                 Position(lat=state.lat, lon=state.lon, alt=state.alt)
#                 if source == "gps" and state.gps_received else None
#             ),
#             battery=BatteryData(percentage=state.battery),
#         )
#
#     async def get_safe_state(self, node):
#         state = self._nodes.get(node.id)
#         if state:
#             self.send_command_long(state, 21)   # MAV_CMD_NAV_LAND
#         return CommandResult(success=True, message="Landing")
#
#     async def cmd_move_to(self, node, lat, lon, alt=0.0):
#         state = self._nodes.get(node.id)
#         if not state or not state.connected:
#             return CommandResult(success=False, message="Not connected")
#         if node.position is None:
#             return CommandResult(success=False, message="No position fix")
#         self.send_set_position_target(state, lat, lon, alt)
#         return CommandResult(success=True, message=f"Moving to {lat:.5f}, {lon:.5f}")
