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
8. Override is_connected() so node_registry can detect a dead connection quickly

Standard commands flow through the base class send_command dispatcher automatically:
    DeviceProxy.move_to()    → cmd_move_to()
    DeviceProxy.stop()       → cmd_stop()
    DeviceProxy.return_home()→ cmd_return_home()
    Custom manifest commands → handle_custom_command() [optional override]
"""

import asyncio
import logging
from typing import Any, AsyncGenerator, Optional

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
    """Per-node connection state. One instance per connected turtlebot."""

    def __init__(self):
        self.connected: bool = False
        self.transport: Optional[Any] = None  # roslibpy.Ros instance
        self.cmd_vel_topic: Optional[Any] = None  # roslibpy.Topic for /cmd_vel
 
        # Live data -- updated by topic callbacks
        # x, y, z come from Vicon's local tracking-volume frame (meters),
        # NOT lat/lon/alt. See CONFIRM SDK note above.
        self.x: float = 0.0
        self.y: float = 0.0
        self.z: float = 0.0
        self.battery_percent: float = 100.0
        self.vicon_received: bool = False  # guards against emitting (0,0,0) before first pose

        self._subscriptions: list = []
 

class TurtleBotPlugin(NodePlugin):
    """TurtleBot plugin using Vicon motion capture for position instead of GPS."""

 
    PLUGIN_ID = "turtlebot"          # must match manifest id
    PLUGIN_NAME = "TurtleBot"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Your Name"
    PLUGIN_DESCRIPTION = "Plugin for TurtleBot (ROS2, Vicon-tracked)"
 
    def __init__(self):
        super().__init__()
        self._nodes: dict[str, _NodeState] = {}

    # ── Connect ───────────────────────────────────────────────────────────────

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
        namespace = config.get("namespace", "/turtlebot")
        vicon_object_name = config.get("vicon_object_name")
 
        if not vicon_object_name:
            return False, "vicon_object_name is required"
 

        state = _NodeState()
        self._nodes[node.id] = state

        try:
            # TODO: Open your connection here (rosbridge, serial, HTTP, etc.)
            # Example for rosbridge via roslibpy:
            #
            #   ros = roslibpy.Ros(host=host, port=port)
            #   ... connect and wait for ready event ...
            #   state.transport = ros
            import roslibpy
 
            ros = roslibpy.Ros(host=host, port=port)
            ros.run()
            state.transport = ros
            state.connected = True

            # Declare what this robot is and what it can do.
            # This drives capability matching, camera panel detection,
            # and control plugin device selection.
            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,  # TODO: change to your category
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.BATTERY),
                    # TODO: add capabilities your robot supports, e.g.:
                    # CapabilitySpec(capability=DeviceCapability.CAMERA),
                    # CapabilitySpec(capability=DeviceCapability.LIDAR),
                ],
            )




            # Subscribe to Vicon pose for this object
            vicon_topic = roslibpy.Topic(
                ros,
                f"/vicon/{vicon_object_name}/pose",
                "geometry_msgs/PoseStamped",
            )
            vicon_topic.subscribe(lambda msg: self._on_vicon_pose(node.id, msg))
            state._subscriptions.append(vicon_topic)
 
            # Subscribe to battery state
            battery_topic = roslibpy.Topic(
                ros,
                f"{namespace}/battery_state",
                "sensor_msgs/BatteryState",
            )
            battery_topic.subscribe(lambda msg: self._on_battery(node.id, msg))
            state._subscriptions.append(battery_topic)
 
            # Publisher for velocity commands
            state.cmd_vel_topic = roslibpy.Topic(
                ros, f"{namespace}/cmd_vel", "geometry_msgs/Twist"
            )
 
            logger.info(
                "TurtleBot [%s]: connected to %s:%d, tracking Vicon object '%s'",
                node.name, host, port, vicon_object_name,
            )
            return True, ""

 
        except Exception as e:
            logger.error("Turtlebot [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False, str(e)



    def _on_vicon_pose(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        pos = msg.get("pose", {}).get("position", {})
        state.x = pos.get("x", 0.0)
        state.y = pos.get("y", 0.0)
        state.z = pos.get("z", 0.0)
        state.vicon_received = True
 
    def _on_battery(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            # sensor_msgs/BatteryState percentage is 0.0-1.0
            state.battery_percent = msg.get("percentage", 1.0) * 100.0
 

    # ── Disconnect ────────────────────────────────────────────────────────────

    async def disconnect(self, node: Node) -> None:
        """Clean up all resources for this node."""
        state = self._nodes.pop(node.id, None)
        if not state:
            return
        state.connected = False
        for sub in state._subscriptions:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        if state.transport:
            try:
                state.transport.close()  # TODO: use your transport's close method
            except Exception:
                pass
        logger.info("Turtlebot [%s]: disconnected", node.name)

    # ── Liveness check ────────────────────────────────────────────────────────

    async def is_connected(self, node: Node) -> bool:
        """
        Return False if you know the underlying connection is dead.
        node_registry polls this every 2 s and sets the node DEGRADED if False,
        which is faster than the 5 s failsafe heartbeat fallback.

        """
        state = self._nodes.get(node.id)
        return (
            state is not None
            and state.connected
            and state.transport is not None
            and state.transport.is_connected
        )

    # ── Standard command handlers ─────────────────────────────────────────────
    # Override the methods below instead of send_command.
    # The base class routes move_to/stop/return_home here automatically.

    async def cmd_move_to(
        self, node: Node, x: float, y: float, z: float = 0.0
    ) -> CommandResult:
        """
        NOTE: TurtleBot doesn't take absolute-position goals over /cmd_vel directly.
        This is a placeholder that just logs the target -- real navigation should
        either publish a nav2 goal pose (if nav2 is running) or implement a simple
        proportional controller driving toward (x, y) using the current Vicon
        position. Left as TODO since it depends on your navigation stack.
        """
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # TODO: publish nav2 goal or drive toward (x, y, z) using Vicon feedback
        logger.info("TurtleBot [%s]: move_to requested %.2f, %.2f, %.2f", node.name, x, y, z)
        return CommandResult(success=True, message=f"Moving to {x:.2f}, {y:.2f}, {z:.2f}")

 

    async def cmd_stop(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        self._publish_zero_twist(state)
        logger.info("TurtleBot [%s]: stop", node.name)
        return CommandResult(success=True, message="Stopped")
    
    async def cmd_return_home(self, node: Node) -> CommandResult:
        """
        Home is confirmed to be Vicon origin (0, 0, 0) for this testing setup.
        Still needs actual navigation logic -- see TODO in cmd_move_to, same
        caveat applies (nav2 goal vs. simple P-controller toward the target).
        """
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        # TODO: drive toward (0.0, 0.0, 0.0) using Vicon feedback, once
        # Vicon is confirmed live and a navigation approach is chosen
        logger.info("TurtleBot [%s]: return home (target 0,0,0)", node.name)
        return CommandResult(success=True, message="Returning home")
 
    def _publish_zero_twist(self, state: _NodeState) -> None:
        if state.cmd_vel_topic:
            state.cmd_vel_topic.publish(
                {"linear": {"x": 0, "y": 0, "z": 0}, "angular": {"x": 0, "y": 0, "z": 0}}
            )

    # ── Telemetry stream ──────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
 
            # CONFIRM SDK: this repurposes lat/lon/alt to carry Vicon's local
            # x/y/z (meters, tracking-volume frame) -- NOT geographic coords.
            # Revisit if henosync_sdk has a dedicated local-position type.
            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                #speed=state.speed,  # TODO: compute from consecutive Vicon poses if needed
                battery=BatteryData(percentage=state.battery_percent),
                position=Position(
                    lat=state.x, lon=state.y, alt=state.z
                ) if state.vicon_received else None,
                status_text="Online" if state.vicon_received else "Connected — waiting for Vicon",
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── Safe state ────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state:
            self._publish_zero_twist(state)
        logger.warning("TurtleBot [%s]: safe state engaged", node.name)
        return CommandResult(success=True, message="Safe state engaged")