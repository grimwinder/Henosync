"""
UE Sim plugin — Unreal Engine AirSim (SUV1) via rosbridge.

Milestone 1 ✓: Connect to rosbridge, heartbeat telemetry, device goes Online.
Milestone 2 ✓: Subscribe to global_gps + car_state — position on map, speed in panel.
Milestone 2b ✓: Camera feed via web_video_server.
Milestone 3 (next): IMU heading.
"""

import logging
import time
from typing import Any

from henosync_sdk import (
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    EventSeverity,
    Node,
    Position,
    TelemetryFrame,
)
from henosync_sdk.protocols.ros2 import ROS2NodeState, ROS2Plugin

logger = logging.getLogger(__name__)

GPS_TOPIC     = "/airsim_node/SUV1/global_gps"   # sensor_msgs/NavSatFix
STATE_TOPIC   = "/airsim_node/SUV1/car_state"    # airsim_ros_pkgs/CarState
CAR_CMD_TOPIC = "/airsim_node/SUV1/car_cmd"      # airsim_ros_pkgs/CarControls


class _NodeState(ROS2NodeState):
    def __init__(self):
        super().__init__()
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.speed: float = 0.0
        self.gps_received: bool = False
        self.last_message_time: float = 0.0
        self.connect_time: float = time.monotonic()
        self._no_fix_warned: bool = False
        self.car_cmd_pub: Any = None


class UESimPlugin(ROS2Plugin):
    PLUGIN_ID = "ue-sim"
    PLUGIN_NAME = "UE Sim (ROS2)"
    PLUGIN_VERSION = "0.2.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Plugin for Unreal Engine AirSim SUV via rosbridge"

    TELEMETRY_RATE_HZ: float = 2.0
    MESSAGE_TIMEOUT: float = 10.0
    POSITION_FIX_TIMEOUT: float = 10.0

    def __init__(self):
        super().__init__()

    def create_state(self) -> _NodeState:
        return _NodeState()

    async def setup_node(self, node: Node, state: _NodeState, config: dict) -> None:
        node.specs = DeviceSpecs(
            category=DeviceCategory.AGV,
            capabilities=[
                CapabilitySpec(capability=DeviceCapability.GPS),
                CapabilitySpec(capability=DeviceCapability.CAMERA),
                CapabilitySpec(capability=DeviceCapability.MOVE_2D),
            ],
        )
        self.subscribe(state, GPS_TOPIC, "sensor_msgs/NavSatFix",
                       lambda msg: self._on_gps(node.id, msg))
        self.subscribe(state, STATE_TOPIC, "airsim_ros_pkgs/CarState",
                       lambda msg: self._on_car_state(node.id, msg))
        state.car_cmd_pub = self.advertise(state, CAR_CMD_TOPIC, "airsim_ros_pkgs/CarControls")

    # ── Topic callbacks ────────────────────────────────────────────────────────

    def _on_gps(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.lat = msg.get("latitude", 0.0)
            state.lon = msg.get("longitude", 0.0)
            state.alt = msg.get("altitude", 0.0)
            state.gps_received = True
            state.last_message_time = time.monotonic()

    def _on_car_state(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.speed = msg.get("speed", 0.0)
            state.last_message_time = time.monotonic()

    # ── Telemetry ──────────────────────────────────────────────────────────────

    def build_telemetry(self, node: Node, state: _NodeState, seq: int) -> TelemetryFrame:
        return TelemetryFrame(
            node_id=node.id,
            sequence_number=seq,
            speed=state.speed,
            position=Position(lat=state.lat, lon=state.lon, alt=state.alt)
            if state.gps_received else None,
            status_text=(
                f"GPS {state.lat:.5f}, {state.lon:.5f}  "
                f"alt {state.alt:.1f} m  speed {state.speed:.1f} m/s"
                if state.gps_received else "Connected — waiting for GPS"
            ),
        )

    async def on_telemetry_tick(self, node: Node, state: _NodeState) -> None:
        if (
            not state.gps_received
            and not state._no_fix_warned
            and time.monotonic() - state.connect_time > self.POSITION_FIX_TIMEOUT
        ):
            state._no_fix_warned = True
            if self._context:
                await self._context.emit_event(
                    "No GPS data",
                    f"Connected but no GPS received after {self.POSITION_FIX_TIMEOUT:.0f}s. "
                    f"Check that {GPS_TOPIC} is publishing.",
                    EventSeverity.WARNING,
                )

    async def is_connected(self, node: Node) -> bool:
        if not await super().is_connected(node):
            return False
        state = self._nodes.get(node.id)
        if (
            state.gps_received
            and time.monotonic() - state.last_message_time > self.MESSAGE_TIMEOUT
        ):
            return False
        return True

    # ── Camera feed ────────────────────────────────────────────────────────────

    async def get_video_stream_url(self, node: Node) -> str | None:
        host = node.config.get("host", "localhost")
        return (
            f"http://{host}:8080/stream"
            f"?topic=/airsim_node/SUV1/StereoCamera0_Scene/image"
        )

    # ── Custom commands ────────────────────────────────────────────────────────

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        if envelope.command_type != "cmd_vel":
            return CommandResult(success=False, message=f"Unknown command: {envelope.command_type}")
        state = self._nodes.get(node.id)
        if not state or not state.car_cmd_pub:
            return CommandResult(success=False, message="Not connected")
        linear  = max(-1.0, min(1.0, envelope.params.get("linear", 0.0)))
        angular = max(-1.0, min(1.0, envelope.params.get("angular", 0.0)))
        self.publish(state.car_cmd_pub, {
            "throttle": abs(linear),
            "steering": angular,
            "brake": 1.0 if linear == 0.0 and angular == 0.0 else 0.0,
            "handbrake": False,
            "is_manual_gear": linear < 0.0,
            "manual_gear": -1 if linear < 0.0 else 0,
            "gear_immediate": True,
        })
        return CommandResult(success=True, message="cmd_vel sent")

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state and state.car_cmd_pub:
            self.publish(state.car_cmd_pub, {
                "throttle": 0.0, "steering": 0.0, "brake": 1.0,
                "handbrake": True, "is_manual_gear": False,
                "manual_gear": 0, "gear_immediate": True,
            })
        return CommandResult(success=True, message="UE Sim — brake applied")
