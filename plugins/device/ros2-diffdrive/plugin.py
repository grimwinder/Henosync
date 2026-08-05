"""
ROS2 Diff-Drive — generic ground robot via rosbridge (roslibpy).

For any real ROS2 robot running rosbridge_server. Topic names are per-device
config (set in the Add Device form) — find yours with `ros2 topic list` on
the robot before adding it here.

Milestone 1: connect, drive via cmd_vel (arrow-key teleop), speed telemetry.
No GPS/map position yet — add once you know whether your robot publishes GPS.
"""

import logging

from henosync_sdk import (
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    Node,
    TelemetryFrame,
)
from henosync_sdk.protocols.ros2 import ROS2NodeState, ROS2Plugin

logger = logging.getLogger(__name__)


class _NodeState(ROS2NodeState):
    def __init__(self):
        super().__init__()
        self.speed: float = 0.0
        self.odom_received: bool = False
        self.cmd_vel_pub = None


class ROS2DiffDrivePlugin(ROS2Plugin):
    PLUGIN_ID = "ros2-diffdrive"
    PLUGIN_NAME = "ROS2 Diff-Drive Robot"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Generic ROS2 differential-drive ground robot via rosbridge"

    TELEMETRY_RATE_HZ: float = 2.0

    def __init__(self):
        super().__init__()

    def create_state(self) -> _NodeState:
        return _NodeState()

    async def setup_node(self, node: Node, state: _NodeState, config: dict) -> None:
        node.specs = DeviceSpecs(
            category=DeviceCategory.AGV,
            capabilities=[CapabilitySpec(capability=DeviceCapability.MOVE_2D)],
        )
        cmd_vel_topic = config.get("cmd_vel_topic", "/cmd_vel")
        state.cmd_vel_pub = self.advertise(state, cmd_vel_topic, "geometry_msgs/Twist")

        odom_topic = config.get("odom_topic", "/odom")
        if odom_topic:
            self.subscribe(state, odom_topic, "nav_msgs/Odometry",
                           lambda msg: self._on_odom(node.id, msg))

        logger.info("ROS2 DiffDrive [%s]: cmd_vel=%s odom=%s",
                    node.name, cmd_vel_topic, odom_topic or "(disabled)")

    # ── Topic callbacks ────────────────────────────────────────────────────────

    def _on_odom(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            linear = msg.get("twist", {}).get("twist", {}).get("linear", {})
            state.speed = (linear.get("x", 0.0) ** 2 + linear.get("y", 0.0) ** 2) ** 0.5
            state.odom_received = True

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def build_telemetry(self, node: Node, state: _NodeState, seq: int) -> TelemetryFrame:
        return TelemetryFrame(
            node_id=node.id,
            sequence_number=seq,
            speed=state.speed,
            status_text=(
                f"speed {state.speed:.2f} m/s"
                if state.odom_received else "Connected — no odometry data yet"
            ),
        )

    # ── Custom commands ────────────────────────────────────────────────────────

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        if envelope.command_type != "cmd_vel":
            return CommandResult(success=False, message=f"Unknown command: {envelope.command_type}")
        state = self._nodes.get(node.id)
        if not state or not state.cmd_vel_pub:
            return CommandResult(success=False, message="Not connected")
        max_linear  = float(node.config.get("max_linear_speed", 0.5))
        max_angular = float(node.config.get("max_angular_speed", 1.0))
        linear  = max(-1.0, min(1.0,  envelope.params.get("linear",  0.0))) * max_linear
        # Negate: teleop right=+1, ROS angular.z positive=CCW=left
        angular = max(-1.0, min(1.0, -envelope.params.get("angular", 0.0))) * max_angular
        self.publish(state.cmd_vel_pub, {
            "linear":  {"x": linear,  "y": 0.0, "z": 0.0},
            "angular": {"x": 0.0,     "y": 0.0, "z": angular},
        })
        return CommandResult(success=True, message="cmd_vel sent")

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state and state.cmd_vel_pub:
            self.publish(state.cmd_vel_pub, {
                "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
            })
        return CommandResult(success=True, message="ROS2 DiffDrive — zero velocity sent")
