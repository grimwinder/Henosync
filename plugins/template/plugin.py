"""
Henosync Device Plugin Template
================================
Copy this folder, rename it, and implement the methods below.

Steps:
1. Update manifest.json with your robot's details
2. Rename MyRobotPlugin and set PLUGIN_ID to match manifest id
3. Implement connect() — establish connection and set node.specs
4. Implement disconnect() — clean up all resources
5. Override cmd_move_to / cmd_stop / cmd_return_home for the capabilities you declare
6. Implement telemetry_stream() — yield live sensor data using typed TelemetryFrame fields
7. Implement get_safe_state() — stop the robot safely
8. Override is_connected() if your transport can detect a dead connection
   (e.g. check ros.is_connected for rosbridge, serial port open, etc.)

Standard commands flow through the base class send_command dispatcher automatically:
    DeviceProxy.move_to()    → cmd_move_to()
    DeviceProxy.stop()       → cmd_stop()
    DeviceProxy.return_home()→ cmd_return_home()
    Custom manifest commands → handle_custom_command() [optional override]
"""

import asyncio
import logging
from typing import Any, AsyncGenerator

from henosync_sdk import (
    BatteryData,
    CapabilitySpec,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    Node,
    NodePlugin,
    NodePluginContext,
    Position,
    TelemetryFrame,
)

logger = logging.getLogger(__name__)


class _NodeState:
    """Per-node connection state. One instance per connected robot."""

    def __init__(self):
        self.connected: bool = False

        # Live sensor data — updated by topic callbacks or polling
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.speed: float = 0.0
        self.battery_percent: float = 100.0
        self.gps_received: bool = False  # guards against emitting lat=0,lon=0


class MyRobotPlugin(NodePlugin):
    """
    Replace MyRobotPlugin with your robot's name.
    Replace all TODO comments with your implementation.
    """

    PLUGIN_ID = "my-robot"           # must match manifest id
    PLUGIN_NAME = "My Robot"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Your Name"
    PLUGIN_DESCRIPTION = "Plugin for My Robot"

    def __init__(self):
        super().__init__()
        self._nodes: dict[str, _NodeState] = {}

    async def connect(
        self, node: Node, config: dict[str, Any], context: NodePluginContext
    ) -> tuple[bool, str]:
        """
        Establish connection to the robot.
        Return (False, "reason") on failure — never raise exceptions here.
        """
        self._context = context  # store for emit_event / command_completed

        host = config.get("host", "localhost")
        port = int(config.get("port", 9090))

        state = _NodeState()
        self._nodes[node.id] = state

        try:
            # TODO: Open your connection here (rosbridge, serial, HTTP, etc.)
            # Example for rosbridge via roslibpy:
            #
            #   import roslibpy
            #   ros = roslibpy.Ros(host=host, port=port)
            #   ... connect and wait for ready event ...
            #   state.ros = ros

            state.connected = True

            # Declare what this robot is and what it can do.
            # This drives capability matching, camera panel detection,
            # and control plugin device selection.
            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,  # TODO: change to your category
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.GPS),
                    CapabilitySpec(capability=DeviceCapability.BATTERY),
                    # TODO: add capabilities your robot supports, e.g.:
                    # CapabilitySpec(capability=DeviceCapability.CAMERA),
                    # CapabilitySpec(capability=DeviceCapability.LIDAR),
                ],
            )

            # TODO: Subscribe to your robot's topics here
            # Example:
            #   gps_topic = roslibpy.Topic(state.ros, "/gps", "sensor_msgs/NavSatFix")
            #   gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))

            logger.info("MyRobot [%s]: connected to %s:%d", node.name, host, port)
            return True, ""

        except Exception as e:
            logger.error("MyRobot [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False, str(e)

    # TODO: Add topic callback methods here, e.g.:
    #
    # def _on_gps(self, node_id: str, msg: dict) -> None:
    #     state = self._nodes.get(node_id)
    #     if state:
    #         state.lat = msg.get("latitude", 0.0)
    #         state.lon = msg.get("longitude", 0.0)
    #         state.alt = msg.get("altitude", 0.0)
    #         state.gps_received = True

    async def disconnect(self, node: Node) -> None:
        """Clean up all resources for this node."""
        state = self._nodes.pop(node.id, None)
        if not state:
            return
        state.connected = False
        # TODO: Unsubscribe topics and close connection here
        logger.info("MyRobot [%s]: disconnected", node.name)

    # ── Standard command handlers ─────────────────────────────────────────────
    # Override the methods below instead of send_command.
    # The base class routes move_to/stop/return_home here automatically.

    async def cmd_move_to(
        self, node: Node, lat: float, lon: float, alt: float = 0.0
    ) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # TODO: Send move command to robot
        logger.info("MyRobot [%s]: moving to %.5f, %.5f", node.name, lat, lon)
        return CommandResult(success=True, message=f"Moving to {lat:.5f}, {lon:.5f}")

    async def cmd_stop(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # TODO: Send stop command to robot
        logger.info("MyRobot [%s]: stop", node.name)
        return CommandResult(success=True, message="Stopped")

    async def cmd_return_home(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # TODO: Send return-home command to robot
        logger.info("MyRobot [%s]: return home", node.name)
        return CommandResult(success=True, message="Returning home")

    # ── Telemetry stream ──────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        """
        Yield typed TelemetryFrame at TELEMETRY_RATE_HZ until the node is removed.
        Connection checking is handled globally by node_registry — no connection
        logic belongs here. Override is_connected() if your transport can detect
        a dead connection faster than the 5 s failsafe heartbeat timeout.
        """
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]

            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                speed=state.speed,
                battery=BatteryData(percentage=state.battery_percent),
                # Only emit position once real GPS data has arrived.
                # Without this guard the robot appears at (0, 0) on the map.
                position=Position(
                    lat=state.lat, lon=state.lon, alt=state.alt
                ) if state.gps_received else None,
                status_text="Online" if state.gps_received else "Connected — waiting for GPS",
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── Safe state ────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        """
        Put the robot in its safest possible state immediately.
        Called automatically on heartbeat loss or emergency stop.

        Do NOT kill the telemetry stream here — the platform needs
        to keep receiving data after a failsafe triggers.
        """
        logger.warning("MyRobot [%s]: safe state engaged", node.name)
        # TODO: Send your robot's stop/safe command here
        return CommandResult(success=True, message="Safe state engaged")
