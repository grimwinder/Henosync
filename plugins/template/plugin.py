"""
Henosync Device Plugin Template
================================
Copy this folder, rename it, and implement the five methods below.

Steps:
1. Update manifest.json with your robot's details
2. Rename MyRobotPlugin and set PLUGIN_ID to match manifest id
3. Implement connect() — establish connection and set node.specs
4. Implement disconnect() — clean up all resources
5. Implement send_command() — handle each capability from your manifest
6. Implement telemetry_stream() — yield live sensor data
7. Implement get_safe_state() — stop the robot safely
"""

import asyncio
import sys
import os
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from henosync.plugin_system.interfaces import NodePlugin
from henosync.models import (
    Node, TelemetryFrame, CommandResult,
    DeviceSpecs, DeviceCategory, DeviceCapability, CapabilitySpec,
)

logger = logging.getLogger(__name__)


class _NodeState:
    """Per-node connection state. One instance per connected robot."""

    def __init__(self):
        self.connected: bool = False

        # Live sensor data — updated by topic callbacks
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
        # One _NodeState entry per connected node.
        # Never use a single shared connection — this plugin class handles
        # all nodes of this type simultaneously.
        self._nodes: dict[str, _NodeState] = {}

    async def connect(self, node: Node, config: dict[str, Any]) -> bool:
        """
        Establish connection to the robot.
        Return False (never raise) on failure.
        """
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
            #
            # Return False immediately if the connection cannot be established.

            state.connected = True

            # Declare what this robot is and what it can do.
            # This drives capability matching, camera panel detection,
            # and control plugin device selection.
            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,  # TODO: change to your category
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.GPS),
                    # TODO: add capabilities your robot supports, e.g.:
                    # CapabilitySpec(capability=DeviceCapability.CAMERA),
                    # CapabilitySpec(capability=DeviceCapability.BATTERY),
                ],
            )

            # TODO: Subscribe to your robot's topics here
            # Example:
            #   gps_topic = roslibpy.Topic(state.ros, "/gps", "sensor_msgs/NavSatFix")
            #   gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))

            logger.info("MyRobot [%s]: connected to %s:%d", node.name, host, port)
            return True

        except Exception as e:
            logger.error("MyRobot [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False

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

    async def send_command(
        self,
        node: Node,
        capability: str,
        params: dict[str, Any],
    ) -> CommandResult:
        """
        Handle a capability command.
        Return success once the robot ACCEPTS the command, not when it finishes.
        """
        if capability == "stop":
            # TODO: Send stop command to robot
            return CommandResult(success=True, message="Stopped")

        elif capability == "move_to":
            lat = params.get("lat")
            lon = params.get("lon")
            if lat is None or lon is None:
                return CommandResult(success=False, message="Missing lat/lon params")
            # TODO: Send move command to robot (alt available via params.get("alt", 0.0))
            return CommandResult(success=True, message=f"Moving to {lat}, {lon}")

        elif capability == "return_home":
            # TODO: Send return home command to robot
            return CommandResult(success=True, message="Returning home")

        return CommandResult(success=False, message=f"Unknown capability: {capability}")

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        """Yield telemetry frames at ~1Hz while connected."""
        seq = 0
        while node.id in self._nodes and self._nodes[node.id].connected:
            state = self._nodes[node.id]

            values: dict[str, Any] = {
                "battery_percent": state.battery_percent,
                "speed": state.speed,
            }

            if state.gps_received:
                # Only emit position once real GPS data has arrived.
                # Without this guard the robot appears at (0, 0) on the map.
                values["lat"] = state.lat
                values["lon"] = state.lon
                values["alt"] = state.alt
                values["status_text"] = "Online"
            else:
                values["status_text"] = "Connected — waiting for GPS"

            yield TelemetryFrame(
                node_id=node.id,
                timestamp=datetime.now(timezone.utc),
                sequence_number=seq,
                values=values,
            )
            seq += 1
            await asyncio.sleep(1.0)

    async def get_safe_state(self, node: Node) -> CommandResult:
        """
        Put the robot in its safest possible state immediately.
        Called automatically on heartbeat loss or emergency stop.

        Do NOT kill the telemetry stream here — the platform needs
        to keep receiving data after a failsafe triggers.
        Keep this simple and reliable above all else.
        """
        # TODO: Send your robot's stop/safe command here
        logger.warning("MyRobot [%s]: safe state engaged", node.name)
        return CommandResult(success=True, message="Safe state engaged")
