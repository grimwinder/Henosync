"""
Henosync Device Plugin Template
================================
Copy this folder, rename it, and implement the methods below.

Supports two positioning modes selectable at device-setup time:
  GPS   — robot has its own GPS; reads sensor_msgs/NavSatFix
  VICON — VICON motion capture provides position; converts local X/Y to WGS84

Steps:
1. Update manifest.json with your robot's details
2. Rename MyRobotPlugin and set PLUGIN_ID to match manifest id
3. Fill in the TODO sections for your transport (rosbridge, serial, HTTP, …)
4. Implement the command handlers and get_safe_state()
5. Override is_connected() for fast dead-connection detection

Standard commands flow through the base class send_command dispatcher:
    DeviceProxy.move_to()     → cmd_move_to()
    DeviceProxy.stop()        → cmd_stop()
    DeviceProxy.return_home() → cmd_return_home()
    Custom manifest commands  → handle_custom_command()
"""

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Optional

from henosync_sdk import (
    BatteryData,
    CapabilitySpec,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    EventSeverity,
    LocalOrigin,
    Node,
    NodePlugin,
    NodePluginContext,
    Position,
    PositioningMixin,
    TelemetryFrame,
)

logger = logging.getLogger(__name__)


class _NodeState:
    """Per-node connection state. One instance per connected robot."""

    def __init__(self):
        self.connected: bool = False
        self.transport: Optional[Any] = None  # TODO: replace with your connection type

        # Live sensor data — written by position callbacks below
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.speed: float = 0.0
        self.battery_percent: float = 100.0
        self.position_received: bool = False  # guards against emitting lat=0,lon=0 before first fix

        # VICON local frame (used only in "vicon" positioning mode)
        self.local_x: float = 0.0
        self.local_y: float = 0.0

        # Timing for position health checks
        self.connect_time: float = time.monotonic()
        self.last_position_time: float = 0.0

        # Warning flags — each fires once so the operator isn't spammed
        self._no_fix_warned: bool = False
        self._stale_warned: bool = False

        # Track active subscriptions so disconnect() can unsubscribe cleanly
        self._subscriptions: list = []


class MyRobotPlugin(NodePlugin, PositioningMixin):
    """
    Replace MyRobotPlugin with your robot's name.
    Replace all TODO comments with your implementation.

    Inheriting PositioningMixin provides _local_to_gps() for VICON mode.
    """

    PLUGIN_ID = "my-robot"           # must match manifest id
    PLUGIN_NAME = "My Robot"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Your Name"
    PLUGIN_DESCRIPTION = "Plugin for My Robot"

    TELEMETRY_RATE_HZ: float = 2.0

    # Warn if no position arrives within this many seconds of connecting.
    # Catches: vicon_bridge not running, wrong object name, GPS topic missing.
    POSITION_FIX_TIMEOUT: float = 10.0

    # Warn and stop emitting position if no update arrives for this many seconds.
    # Catches: VICON tracking loss, marker occlusion, GPS signal lost.
    POSITION_STALE_TIMEOUT: float = 3.0

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
        self._context = context

        host = config.get("host", "localhost")
        port = int(config.get("port", 9090))
        position_source = config.get("position_source", "gps")

        state = _NodeState()
        self._nodes[node.id] = state

        try:
            # TODO: Open your transport connection here.
            # Example for rosbridge via roslibpy:
            #
            #   import roslibpy
            #   ros = roslibpy.Ros(host=host, port=port)
            #   ros.run_in_thread()          # or use the _ensure_reactor() pattern
            #   ... wait for connected event ...
            #   state.transport = ros

            state.connected = True

            # Declare what this robot is and what it can do.
            # Drives capability matching, camera detection, and control plugin selection.
            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,    # TODO: change to your robot's category
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.GPS),
                    CapabilitySpec(capability=DeviceCapability.BATTERY),
                    # TODO: add capabilities your robot has, e.g.:
                    # CapabilitySpec(capability=DeviceCapability.CAMERA),
                    # CapabilitySpec(capability=DeviceCapability.LIDAR),
                ],
                # "local" tells DeviceProxy this device works in a local coordinate frame.
                # GPS mode uses "gps" — DeviceProxy converts GPS waypoints directly.
                coordinate_frame="local" if position_source == "vicon" else "gps",
            )

            if position_source == "gps":
                # ── GPS mode ───────────────────────────────────────────────────
                # Subscribe to the robot's GPS topic (sensor_msgs/NavSatFix).
                # TODO: replace "/gps/fix" with your robot's actual topic name.
                #
                #   gps_topic = roslibpy.Topic(ros, "/gps/fix", "sensor_msgs/NavSatFix")
                #   gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))
                #   state._subscriptions.append(gps_topic)
                pass

            else:
                # ── VICON mode ─────────────────────────────────────────────────
                # VICON publishes local X/Y/Z in metres from the arena origin.
                # We convert to WGS84 using the home lat/lon from config.
                home_lat = float(config.get("home_lat", 0.0))
                home_lon = float(config.get("home_lon", 0.0))
                if home_lat == 0.0 and home_lon == 0.0:
                    self._nodes.pop(node.id, None)
                    return False, "VICON mode requires home_lat and home_lon in config"

                # Store the local origin so DeviceProxy can convert GPS waypoints
                # back to local frame when sending move_to commands.
                node.local_origin = LocalOrigin(lat=home_lat, lon=home_lon)

                # Subscribe to the VICON topic for this object.
                # Standard vicon_bridge topic: /vicon/{object_name}/{object_name}
                # Message type: geometry_msgs/TransformStamped
                # TODO: update topic path and type to match your VICON bridge setup.
                #
                #   object_name = config.get("vicon_object_name", "robot")
                #   vicon_topic = roslibpy.Topic(
                #       ros,
                #       f"/vicon/{object_name}/{object_name}",
                #       "geometry_msgs/TransformStamped",
                #   )
                #   vicon_topic.subscribe(
                #       lambda msg: self._on_vicon(node.id, msg, home_lat, home_lon)
                #   )
                #   state._subscriptions.append(vicon_topic)
                pass

            logger.info(
                "MyRobot [%s]: connected to %s:%d (%s mode)",
                node.name, host, port, position_source,
            )
            return True, ""

        except Exception as e:
            logger.error("MyRobot [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False, str(e)

    # ── Position callbacks ────────────────────────────────────────────────────
    # These run on the transport thread — only write to state fields, no awaits.

    def _on_gps(self, node_id: str, msg: dict) -> None:
        """Callback for sensor_msgs/NavSatFix (GPS mode)."""
        state = self._nodes.get(node_id)
        if not state:
            return
        state.lat = msg.get("latitude", 0.0)
        state.lon = msg.get("longitude", 0.0)
        state.alt = msg.get("altitude", 0.0)
        state.position_received = True
        state.last_position_time = time.monotonic()

    def _on_vicon(
        self, node_id: str, msg: dict, home_lat: float, home_lon: float
    ) -> None:
        """
        Callback for geometry_msgs/TransformStamped (VICON mode).

        Assumes X = East, Y = North from the VICON arena origin.
        If your VICON setup uses a different axis convention, swap or negate
        x_m / y_m before calling _local_to_gps().
        """
        state = self._nodes.get(node_id)
        if not state:
            return
        t = msg.get("transform", {}).get("translation", {})
        x_m = t.get("x", 0.0)
        y_m = t.get("y", 0.0)
        z_m = t.get("z", 0.0)
        state.local_x = x_m
        state.local_y = y_m
        state.lat, state.lon = self._local_to_gps(x_m, y_m, home_lat, home_lon)
        state.alt = z_m
        state.position_received = True
        state.last_position_time = time.monotonic()

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
        logger.info("MyRobot [%s]: disconnected", node.name)

    # ── Liveness check ────────────────────────────────────────────────────────

    async def is_connected(self, node: Node) -> bool:
        """
        Return False if the underlying connection is dead.
        node_registry polls this every 2 s and sets DEGRADED if False —
        faster than the 5 s failsafe heartbeat fallback.

        TODO: check your transport's live state, e.g.:
            return (
                state is not None
                and state.connected
                and state.transport is not None
                and state.transport.is_connected
            )
        """
        state = self._nodes.get(node.id)
        return state is not None and state.connected

    # ── Standard command handlers ─────────────────────────────────────────────
    # Override these instead of send_command. The base class routes
    # move_to / stop / return_home to these methods automatically.

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
        logic belongs in this loop.
        """
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
            now = time.monotonic()

            # ── Fix 1: no initial position ─────────────────────────────────
            # Fires once if no position arrives within POSITION_FIX_TIMEOUT seconds.
            # Likely causes: vicon_bridge not running, wrong object name, GPS topic missing.
            if (
                not state.position_received
                and not state._no_fix_warned
                and now - state.connect_time > self.POSITION_FIX_TIMEOUT
            ):
                state._no_fix_warned = True
                logger.warning("MyRobot [%s]: no position received after %.0fs", node.name, self.POSITION_FIX_TIMEOUT)
                if self._context:
                    await self._context.emit_event(
                        "No position data",
                        f"Connected but no position received after {self.POSITION_FIX_TIMEOUT:.0f}s. "
                        "Check that the position topic is publishing and the object name is correct.",
                        EventSeverity.WARNING,
                    )

            # ── Fix 2: position gone stale ─────────────────────────────────
            # Fires once when updates stop arriving after an initial fix.
            # Likely causes: VICON tracking loss, marker occlusion, GPS signal lost.
            position_stale = (
                state.position_received
                and now - state.last_position_time > self.POSITION_STALE_TIMEOUT
            )
            if position_stale and not state._stale_warned:
                state._stale_warned = True
                logger.warning("MyRobot [%s]: position updates stopped", node.name)
                if self._context:
                    await self._context.emit_event(
                        "Position tracking lost",
                        f"No position update for {self.POSITION_STALE_TIMEOUT:.0f}s. "
                        "VICON may have lost tracking or GPS signal is lost.",
                        EventSeverity.WARNING,
                    )

            # ── Fix 3: recovery ────────────────────────────────────────────
            # Clear stale warning when updates resume so the next dropout fires again.
            if not position_stale and state._stale_warned:
                state._stale_warned = False

            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                speed=state.speed,
                battery=BatteryData(percentage=state.battery_percent),
                # Suppress position when stale — robot stays at last known location
                # on the map rather than freezing at a potentially wrong position.
                position=Position(
                    lat=state.lat, lon=state.lon, alt=state.alt
                ) if state.position_received and not position_stale else None,
                status_text=(
                    "Position lost"    if position_stale
                    else "Online"      if state.position_received
                    else "Connected — waiting for position"
                ),
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── Safe state ────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        """
        Put the robot in its safest possible state immediately.
        Called automatically on heartbeat loss or emergency stop.
        Do NOT kill the telemetry stream here.
        """
        logger.warning("MyRobot [%s]: safe state engaged", node.name)
        # TODO: Send your robot's stop/safe command here
        return CommandResult(success=True, message="Safe state engaged")
