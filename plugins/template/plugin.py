"""
Henosync Plugin Template
========================
Copy this folder, rename it, and implement the five methods below.

Steps:
1. Update manifest.json with your robot's details
2. Implement connect() to establish connection to your hardware
3. Implement disconnect() to clean up on shutdown
4. Implement send_command() to handle each capability
5. Implement telemetry_stream() to yield live data
6. Implement get_safe_state() to put robot in safe state

For ROS2 robots, use self.transport (ROS2Transport instance)
to subscribe to topics and publish commands.

Full documentation: https://github.com/henosync/henosync/docs
"""

import asyncio
import sys
import os
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

# Add backend to path for imports
sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), '../../apps/backend')
)

from henosync.plugin_system.interfaces import NodePlugin
from henosync.models import Node, TelemetryFrame, CommandResult
from henosync.transport.registry import transport_registry


class MyRobotPlugin(NodePlugin):
    """
    Replace MyRobotPlugin with your robot's name.
    Replace all TODO comments with your implementation.
    """

    PLUGIN_ID = "my-robot"
    PLUGIN_NAME = "My Robot"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Your Name"
    PLUGIN_DESCRIPTION = "Plugin for My Robot"

    def __init__(self):
        self._running: dict[str, bool] = {}
        self._transport = None
        # TODO: Add any other state your plugin needs

    async def connect(self, node: Node, config: dict[str, Any]) -> bool:
        """
        Connect to your robot.
        For ROS2 robots, create a transport and connect to rosbridge.
        """
        host = config.get("host", "localhost")
        port = config.get("port", 9090)
        namespace = config.get("namespace", "")

        # Create ROS2 transport
        self._transport = transport_registry.create("ros2")
        if not self._transport:
            return False

        # Connect to rosbridge on the robot
        success = await self._transport.connect(host, port)
        if not success:
            return False

        self._running[node.id] = True

        # TODO: Subscribe to your robot's topics here
        # Example:
        # self._transport.subscribe_topic(
        #     f"{namespace}/battery_state",
        #     "sensor_msgs/BatteryState",
        #     lambda msg: self._on_battery(node.id, msg)
        # )

        return True

    async def disconnect(self, node: Node) -> None:
        """
        Disconnect from your robot.
        Clean up subscriptions and close transport.
        """
        self._running[node.id] = False
        if self._transport:
            await self._transport.disconnect()
            self._transport = None

    async def send_command(
        self,
        node: Node,
        capability: str,
        params: dict[str, Any]
    ) -> CommandResult:
        """
        Handle a capability command.
        Add an elif branch for each capability in your manifest.
        """
        if capability == "stop":
            # TODO: Implement stop
            return CommandResult(success=True, message="Stopped")

        elif capability == "move_to":
            # TODO: Implement move_to
            lat = params.get("lat", 0)
            lon = params.get("lon", 0)
            return CommandResult(
                success=True,
                message=f"Moving to {lat}, {lon}"
            )

        elif capability == "return_home":
            # TODO: Implement return_home
            return CommandResult(success=True, message="Returning home")

        return CommandResult(
            success=False,
            message=f"Unknown capability: {capability}"
        )

    async def telemetry_stream(
        self,
        node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        """
        Yield telemetry frames continuously.
        Update values dict with your robot's sensor data.
        """
        seq = 0
        while self._running.get(node.id, False):
            yield TelemetryFrame(
                node_id=node.id,
                timestamp=datetime.now(timezone.utc),
                sequence_number=seq,
                values={
                    # TODO: Replace with real sensor values
                    "battery_percent": 100.0,
                    "lat": 0.0,
                    "lon": 0.0,
                    "alt": 0.0,
                    "status_text": "Idle"
                }
            )
            seq += 1
            await asyncio.sleep(1.0)

    async def get_safe_state(self, node: Node) -> CommandResult:
        """
        Put the robot in the safest possible state.
        For a ground robot this should always be: stop all motors.
        Keep this simple and reliable.
        """
        # TODO: Send stop command to your robot
        self._running[node.id] = False
        return CommandResult(
            success=True,
            message="Robot stopped — safe state engaged"
        )
    
    