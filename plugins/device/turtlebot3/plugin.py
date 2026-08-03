"""
TurtleBot3 Burger device plugin for Henosync.

Connects via rosbridge (roslibpy). Supports VICON or GPS positioning.
Movement uses a simple proportional goto controller publishing
geometry_msgs/Twist to /cmd_vel — no nav2 required.

Topics subscribed (all prefixed with namespace if configured):
  /vicon/{object_name}/{object_name}   geometry_msgs/TransformStamped  (VICON mode)
  /gps/fix                             sensor_msgs/NavSatFix            (GPS mode)
  /odom                                nav_msgs/Odometry                (speed + heading)
  /battery_state                       sensor_msgs/BatteryState         (battery %)

Topics published:
  /cmd_vel                             geometry_msgs/Twist              (movement)
"""

import asyncio
import logging
import math
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
from henosync_sdk.rosbridge import ensure_reactor

try:
    import roslibpy
    ROSLIBPY_AVAILABLE = True
except ImportError:
    ROSLIBPY_AVAILABLE = False
    logging.getLogger(__name__).warning("roslibpy not installed — run: pip install roslibpy")

logger = logging.getLogger(__name__)


class _NodeState:
    def __init__(self):
        self.connected: bool = False
        self.ros: Optional[Any] = None
        self.cmd_vel_pub: Optional[Any] = None

        # Position — written by _on_vicon or _on_gps
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.local_x: float = 0.0
        self.local_y: float = 0.0
        self.heading: float = 0.0       # yaw in radians, ENU (0=East, CCW positive)
        self.position_received: bool = False

        # Telemetry
        self.speed: float = 0.0
        self.battery_percent: float = 100.0

        # Timing
        self.connect_time: float = time.monotonic()
        self.last_position_time: float = 0.0
        self.last_message_time: float = 0.0

        # Warning flags — fire once to avoid spamming the operator
        self._no_fix_warned: bool = False
        self._stale_warned: bool = False

        # Set True by cmd_stop or disconnect to interrupt an active goto loop
        self.stop_requested: bool = False

        self._subscriptions: list = []


class TurtleBot3Plugin(NodePlugin, PositioningMixin):
    """
    TurtleBot3 Burger device plugin.

    Positioning: VICON (default) or GPS — selected in Add Device config.
    Movement: proportional goto controller; publishes Twist to /cmd_vel.
    """

    PLUGIN_ID = "turtlebot3"
    PLUGIN_NAME = "TurtleBot3 Burger"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "TurtleBot3 Burger via rosbridge — VICON or GPS positioning"

    TELEMETRY_RATE_HZ: float = 2.0

    # Warn if no position arrives this many seconds after connecting
    POSITION_FIX_TIMEOUT: float = 10.0
    # Warn and suppress position if updates stop for this long
    POSITION_STALE_TIMEOUT: float = 3.0
    # Treat connection as dead if no ROS message arrives for this long
    MESSAGE_TIMEOUT: float = 5.0

    # Goto controller — tuned for TurtleBot3 Burger (max 0.22 m/s, 2.84 rad/s)
    ARRIVAL_THRESHOLD_M: float = 0.30
    MAX_LINEAR_VEL: float = 0.20
    MAX_ANGULAR_VEL: float = 1.50
    LINEAR_GAIN: float = 0.50
    ANGULAR_GAIN: float = 1.50

    def __init__(self):
        super().__init__()
        self._nodes: dict[str, _NodeState] = {}

    # ── Connect ────────────────────────────────────────────────────────────────

    async def connect(
        self, node: Node, config: dict[str, Any], context: NodePluginContext
    ) -> tuple[bool, str]:
        if not ROSLIBPY_AVAILABLE:
            return False, "roslibpy not installed — run: pip install roslibpy"

        self._context = context

        host = config.get("host", "localhost")
        port = int(config.get("port", 9090))
        ns = config.get("namespace", "").rstrip("/")
        position_source = config.get("position_source", "vicon")

        state = _NodeState()
        self._nodes[node.id] = state

        try:
            ros = roslibpy.Ros(host=host, port=port)

            connected_event = asyncio.Event()
            failed_event = asyncio.Event()

            ros.on_ready(lambda: connected_event.set())
            ros.on("close", lambda: self._on_close(node.id))
            ros.on("error", lambda e: (
                logger.error("TurtleBot3 [%s]: rosbridge error: %s", node.name, e),
                failed_event.set(),
            ))

            reactor_ready = ensure_reactor()
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: reactor_ready.wait(5.0)
            )
            if not reactor_ready.is_set():
                self._nodes.pop(node.id, None)
                return False, "Twisted reactor failed to start"

            from twisted.internet import reactor as _reactor
            _reactor.callFromThread(ros.connect)

            done, _ = await asyncio.wait(
                [
                    asyncio.ensure_future(connected_event.wait()),
                    asyncio.ensure_future(failed_event.wait()),
                ],
                timeout=10.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not connected_event.is_set():
                reason = f"timed out connecting to {host}:{port}"
                logger.error("TurtleBot3 [%s]: %s", node.name, reason)
                try:
                    ros.close()
                except Exception:
                    pass
                self._nodes.pop(node.id, None)
                return False, reason

            state.ros = ros
            state.connected = True

            # Advertise /cmd_vel before sending any commands
            cmd_vel_topic = f"{ns}/cmd_vel" if ns else "/cmd_vel"
            state.cmd_vel_pub = roslibpy.Topic(ros, cmd_vel_topic, "geometry_msgs/Twist")
            state.cmd_vel_pub.advertise()

            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.GPS),
                    CapabilitySpec(capability=DeviceCapability.MOVE_2D),
                    CapabilitySpec(capability=DeviceCapability.BATTERY),
                ],
                coordinate_frame="local" if position_source == "vicon" else "gps",
            )

            if position_source == "gps":
                gps_topic_name = f"{ns}/gps/fix" if ns else "/gps/fix"
                gps_topic = roslibpy.Topic(ros, gps_topic_name, "sensor_msgs/NavSatFix")
                gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))
                state._subscriptions.append(gps_topic)

            else:
                home_lat = float(config.get("home_lat", 0.0))
                home_lon = float(config.get("home_lon", 0.0))
                if home_lat == 0.0 and home_lon == 0.0:
                    self._nodes.pop(node.id, None)
                    return False, "VICON mode requires home_lat and home_lon in config"

                node.local_origin = LocalOrigin(lat=home_lat, lon=home_lon)

                object_name = config.get("vicon_object_name", "TurtleBot3")
                vicon_topic = roslibpy.Topic(
                    ros,
                    f"/vicon/{object_name}/{object_name}",
                    "geometry_msgs/TransformStamped",
                )
                vicon_topic.subscribe(
                    lambda msg: self._on_vicon(node.id, msg, home_lat, home_lon)
                )
                state._subscriptions.append(vicon_topic)

            odom_topic_name = f"{ns}/odom" if ns else "/odom"
            odom_topic = roslibpy.Topic(ros, odom_topic_name, "nav_msgs/Odometry")
            odom_topic.subscribe(lambda msg: self._on_odom(node.id, msg))
            state._subscriptions.append(odom_topic)

            battery_topic_name = f"{ns}/battery_state" if ns else "/battery_state"
            battery_topic = roslibpy.Topic(ros, battery_topic_name, "sensor_msgs/BatteryState")
            battery_topic.subscribe(lambda msg: self._on_battery(node.id, msg))
            state._subscriptions.append(battery_topic)

            logger.info(
                "TurtleBot3 [%s]: connected to %s:%d (%s mode, ns='%s')",
                node.name, host, port, position_source, ns or "/",
            )
            return True, ""

        except Exception as e:
            logger.error("TurtleBot3 [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False, str(e)

    def _on_close(self, node_id: str) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.connected = False
            logger.warning("TurtleBot3 [%s]: rosbridge connection closed", node_id)

    # ── Topic callbacks ────────────────────────────────────────────────────────
    # Run on the Twisted thread — write to state fields only, no awaits.

    def _on_gps(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        state.lat = msg.get("latitude", 0.0)
        state.lon = msg.get("longitude", 0.0)
        state.alt = msg.get("altitude", 0.0)
        state.position_received = True
        now = time.monotonic()
        state.last_position_time = now
        state.last_message_time = now

    def _on_vicon(
        self, node_id: str, msg: dict, home_lat: float, home_lon: float
    ) -> None:
        """
        Assumes VICON X = East, Y = North from arena origin.
        If your setup uses a different axis convention, swap/negate x_m/y_m here.
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
        now = time.monotonic()
        state.last_position_time = now
        state.last_message_time = now

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

    def _on_battery(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        pct = msg.get("percentage", -1.0)
        if pct >= 0.0:
            # TurtleBot3 publishes percentage on a 0-100 scale, not 0.0-1.0 per ROS standard
            state.battery_percent = pct if pct > 1.0 else pct * 100.0

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def _quat_to_yaw(q: dict) -> float:
        """Convert quaternion {x,y,z,w} to yaw in radians (ENU: 0=East, CCW positive)."""
        w = q.get("w", 1.0)
        x = q.get("x", 0.0)
        y = q.get("y", 0.0)
        z = q.get("z", 0.0)
        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        return math.atan2(siny_cosp, cosy_cosp)

    def _publish_twist(self, state: _NodeState, linear: float, angular: float) -> None:
        if not state.cmd_vel_pub:
            return
        try:
            state.cmd_vel_pub.publish(roslibpy.Message({
                "linear": {"x": float(linear), "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": float(angular)},
            }))
        except Exception as e:
            logger.warning("TurtleBot3: /cmd_vel publish failed: %s", e)

    # ── Disconnect ─────────────────────────────────────────────────────────────

    async def disconnect(self, node: Node) -> None:
        state = self._nodes.pop(node.id, None)
        if not state:
            return
        state.connected = False
        state.stop_requested = True
        for sub in state._subscriptions:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        if state.cmd_vel_pub:
            try:
                state.cmd_vel_pub.unadvertise()
            except Exception:
                pass
        if state.ros:
            try:
                state.ros.close()
            except Exception:
                pass
        logger.info("TurtleBot3 [%s]: disconnected", node.name)

    # ── Liveness check ─────────────────────────────────────────────────────────

    async def is_connected(self, node: Node) -> bool:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return False
        if state.ros is None or not state.ros.is_connected:
            return False
        if (
            state.last_message_time > 0
            and time.monotonic() - state.last_message_time > self.MESSAGE_TIMEOUT
        ):
            return False
        return True

    # ── Command handlers ───────────────────────────────────────────────────────

    async def cmd_move_to(
        self, node: Node, lat: float, lon: float, alt: float = 0.0
    ) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        if not state.position_received:
            return CommandResult(success=False, message="No position fix — cannot navigate")

        state.stop_requested = False
        logger.info("TurtleBot3 [%s]: goto %.6f, %.6f", node.name, lat, lon)

        while node.id in self._nodes and state.connected:
            if state.stop_requested:
                state.stop_requested = False
                self._publish_twist(state, 0.0, 0.0)
                return CommandResult(success=False, message="Stopped")

            # Local ENU offsets in metres
            R = 6_371_000.0
            dy = R * math.radians(lat - state.lat)
            dx = R * math.radians(lon - state.lon) * math.cos(math.radians(state.lat))
            distance = math.sqrt(dx * dx + dy * dy)

            if distance < self.ARRIVAL_THRESHOLD_M:
                self._publish_twist(state, 0.0, 0.0)
                logger.info("TurtleBot3 [%s]: arrived (%.2fm)", node.name, distance)
                return CommandResult(success=True, message="Arrived")

            # Bearing in ENU frame (0=East, CCW positive) — matches odom yaw convention
            bearing = math.atan2(dy, dx)
            heading_error = math.atan2(
                math.sin(bearing - state.heading),
                math.cos(bearing - state.heading),
            )

            # Scale linear velocity down when misaligned — rotate first, then drive
            linear = min(
                self.MAX_LINEAR_VEL,
                self.LINEAR_GAIN * distance * max(0.0, math.cos(heading_error)),
            )
            angular = max(
                -self.MAX_ANGULAR_VEL,
                min(self.MAX_ANGULAR_VEL, self.ANGULAR_GAIN * heading_error),
            )

            self._publish_twist(state, linear, angular)
            await asyncio.sleep(0.1)

        self._publish_twist(state, 0.0, 0.0)
        return CommandResult(success=False, message="Navigation aborted")

    async def cmd_stop(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        state.stop_requested = True
        self._publish_twist(state, 0.0, 0.0)
        logger.info("TurtleBot3 [%s]: stop", node.name)
        return CommandResult(success=True, message="Stopped")

    async def cmd_return_home(self, node: Node) -> CommandResult:
        if node.home_position:
            return await self.cmd_move_to(
                node, node.home_position.lat, node.home_position.lon
            )
        return CommandResult(success=False, message="No home position set")

    # ── Safe state ─────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state:
            state.stop_requested = True
            self._publish_twist(state, 0.0, 0.0)
        logger.warning("TurtleBot3 [%s]: safe state — stopped", node.name)
        return CommandResult(success=True, message="Stopped")

    # ── Telemetry stream ───────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
            now = time.monotonic()

            # No initial position fix
            if (
                not state.position_received
                and not state._no_fix_warned
                and now - state.connect_time > self.POSITION_FIX_TIMEOUT
            ):
                state._no_fix_warned = True
                logger.warning(
                    "TurtleBot3 [%s]: no position after %.0fs", node.name, self.POSITION_FIX_TIMEOUT
                )
                if self._context:
                    await self._context.emit_event(
                        "No position data",
                        f"No position received after {self.POSITION_FIX_TIMEOUT:.0f}s. "
                        "Check VICON bridge, object name, and home_lat/lon.",
                        EventSeverity.WARNING,
                    )

            # Stale position detection
            position_stale = (
                state.position_received
                and now - state.last_position_time > self.POSITION_STALE_TIMEOUT
            )
            if position_stale and not state._stale_warned:
                state._stale_warned = True
                logger.warning("TurtleBot3 [%s]: position updates stopped", node.name)
                if self._context:
                    await self._context.emit_event(
                        "Position tracking lost",
                        f"No position update for {self.POSITION_STALE_TIMEOUT:.0f}s. "
                        "VICON may have lost tracking.",
                        EventSeverity.WARNING,
                    )
            if not position_stale and state._stale_warned:
                state._stale_warned = False

            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                speed=state.speed,
                battery=BatteryData(percentage=state.battery_percent),
                position=Position(
                    lat=state.lat, lon=state.lon, alt=state.alt
                ) if state.position_received and not position_stale else None,
                status_text=(
                    "Position lost" if position_stale
                    else "Online"   if state.position_received
                    else "Connected — waiting for position"
                ),
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)
