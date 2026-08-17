"""
Clearpath Jackal UGV device plugin for Henosync.

Connects via rosbridge (roslibpy) to a Jackal running Clearpath's ROS2 stack.
Positioning:
  - VICON mode: handled entirely by henosync core (vicon_manager) — a direct
    TCP connection to the VICON DataStream SDK, independent of rosbridge.
    No plugin code here beyond setting node.local_origin.
  - GPS  mode:  subscribes to the onboard GPS topic via rosbridge.

Two ways to move it:

  - move_to: publishes geometry_msgs/PoseStamped to bt_navigator's goal_pose
    topic rather than calling the NavigateToPose action — roslibpy's ROS2
    action support is documented as unreliable over rosbridge, while
    goal_pose is a plain topic publish and avoids that failure mode entirely.
  - cmd_vel (custom command): continuous manual driving for the `teleop`
    control plugin — normalised [-1, 1] linear/angular, scaled to
    max_linear_speed/max_angular_speed and published as a plain Twist.

All roslibpy publish() calls run via reactor.callFromThread() — Twisted's
WebSocket send is not thread-safe when called directly from the asyncio
event loop thread (this bit turtlebot3/ue-sim; see CLAUDE.md changelog).

ASSUMPTION: in VICON mode, the VICON arena origin (home_lat/home_lon) is
assumed aligned with the Jackal's Nav2 "map" frame origin (same origin, same
axes). If they differ, goal_pose targets will land at the wrong physical
location — verify this alignment on the robot before trusting cmd_move_to.

Topics subscribed (all optionally prefixed with `namespace`, e.g. a200_0000):
  sensors/gps_0/fix                   sensor_msgs/NavSatFix           (GPS mode — topic varies by
                                                                        attached GPS unit, override
                                                                        via gps_topic config)
  platform/odom/filtered              nav_msgs/Odometry               (speed)
  platform/bms/state                  sensor_msgs/BatteryState        (battery)
  platform/imu/data                   sensor_msgs/Imu                 (orientation — verify via
                                                                        `ros2 topic list`, not
                                                                        independently confirmed)
  sensors/lidar2d_0/scan              sensor_msgs/LaserScan            (optional — topic varies by
                                                                        attached lidar, override
                                                                        via lidar_topic config)

Topics published:
  platform/cmd_vel_unstamped           geometry_msgs/Twist              (stop / safe state)
  goal_pose                            geometry_msgs/PoseStamped        (move_to — Nav2 goal)

KNOWN LIMITATION: cmd_stop / get_safe_state publish zero Twist directly to
platform/cmd_vel_unstamped. If Nav2 is actively navigating, its controller
server may resume publishing velocity commands moments later — this does
NOT cancel the underlying Nav2 goal (goal cancellation would need a working
ROS2 action-cancel call, which has the same rosbridge reliability problem
noted above). Verify actual stopping behaviour on the robot before relying
on this for safety-critical stops.
"""

import asyncio
import logging
import math
import time
from typing import Any, AsyncGenerator, Optional

from henosync_sdk import (
    BatteryData,
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    EventSeverity,
    IMUData,
    LidarPoint,
    LidarScan,
    LocalOrigin,
    Node,
    NodePlugin,
    NodePluginContext,
    Position,
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
        self.goal_pose_pub: Optional[Any] = None

        # Position — GPS mode only, written by _on_gps.
        # VICON mode: vicon_manager sets node.position directly, nothing here.
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.position_received: bool = False

        # Telemetry
        self.speed: float = 0.0
        self.battery_percent: float = 100.0
        self.imu: IMUData = IMUData()
        self.lidar: Optional[LidarScan] = None

        # Timing
        self.connect_time: float = time.monotonic()
        self.last_position_time: float = 0.0
        self.last_message_time: float = 0.0

        # Warning flags — fire once to avoid spamming the operator
        self._no_fix_warned: bool = False
        self._stale_warned: bool = False

        self._subscriptions: list = []


class JackalPlugin(NodePlugin):
    """
    Clearpath Jackal UGV device plugin.

    Positioning: VICON (default, handled by core vicon_manager) or GPS
    (subscribed here) — selected in Add Device config.
    Movement: publishes a Nav2 goal_pose (PoseStamped) for move_to; direct
    zero-Twist to cmd_vel for stop/safe state.
    """

    PLUGIN_ID = "jackal"
    PLUGIN_NAME = "Clearpath Jackal (ROS2)"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Clearpath Jackal UGV via rosbridge — ROS2 Clearpath stack, VICON/GPS positioning, Nav2 goal_pose movement"

    TELEMETRY_RATE_HZ: float = 2.0

    # Warn if no position arrives this many seconds after connecting
    POSITION_FIX_TIMEOUT: float = 10.0
    # Warn and suppress position if updates stop for this long
    POSITION_STALE_TIMEOUT: float = 3.0
    # Treat connection as dead if no ROS message arrives for this long
    MESSAGE_TIMEOUT: float = 5.0

    def __init__(self):
        super().__init__()
        self._nodes: dict[str, _NodeState] = {}

    # ── Topic naming ─────────────────────────────────────────────────────────

    @staticmethod
    def _topic(ns: str, path: str) -> str:
        return f"/{ns}/{path}" if ns else f"/{path}"

    # ── Connect ────────────────────────────────────────────────────────────────

    async def connect(
        self, node: Node, config: dict[str, Any], context: NodePluginContext
    ) -> tuple[bool, str]:
        if not ROSLIBPY_AVAILABLE:
            return False, "roslibpy not installed — run: pip install roslibpy"

        self._context = context

        host = config.get("host", "localhost")
        port = int(config.get("port", 9090))
        ns = (config.get("namespace") or "").strip("/")
        position_source = config.get("position_source", "vicon")
        selected = set(config.get("selected_capabilities", []))

        state = _NodeState()
        self._nodes[node.id] = state

        try:
            ros = roslibpy.Ros(host=host, port=port)

            connected_event = asyncio.Event()
            failed_event = asyncio.Event()

            ros.on_ready(lambda: connected_event.set())
            ros.on("close", lambda: self._on_close(node.id))
            ros.on("error", lambda e: (
                logger.error("Jackal [%s]: rosbridge error: %s", node.name, e),
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
                logger.error("Jackal [%s]: %s", node.name, reason)
                try:
                    ros.close()
                except Exception:
                    pass
                self._nodes.pop(node.id, None)
                return False, reason

            state.ros = ros
            state.connected = True

            # Advertise publishers before any command can be sent
            state.cmd_vel_pub = roslibpy.Topic(
                ros, self._topic(ns, "platform/cmd_vel_unstamped"), "geometry_msgs/Twist"
            )
            state.cmd_vel_pub.advertise()

            state.goal_pose_pub = roslibpy.Topic(
                ros, self._topic(ns, "goal_pose"), "geometry_msgs/PoseStamped"
            )
            state.goal_pose_pub.advertise()

            capabilities = [
                CapabilitySpec(capability=DeviceCapability.GPS),
                CapabilitySpec(capability=DeviceCapability.BATTERY),
                CapabilitySpec(capability=DeviceCapability.IMU),
                CapabilitySpec(capability=DeviceCapability.MOVE_2D),
            ]
            if "camera" in selected:
                capabilities.append(CapabilitySpec(capability=DeviceCapability.CAMERA))
            if "lidar" in selected:
                capabilities.append(CapabilitySpec(capability=DeviceCapability.LIDAR))

            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,
                capabilities=capabilities,
                coordinate_frame="local" if position_source == "vicon" else "gps",
            )

            if position_source == "vicon":
                home_lat = float(config.get("home_lat", 0.0))
                home_lon = float(config.get("home_lon", 0.0))
                if home_lat == 0.0 and home_lon == 0.0:
                    self._nodes.pop(node.id, None)
                    return False, "VICON mode requires home_lat and home_lon in config"

                # Position is published directly by the core vicon_manager (a
                # TCP connection to the VICON DataStream SDK, independent of
                # rosbridge) — nothing to subscribe here.
                node.local_origin = LocalOrigin(lat=home_lat, lon=home_lon)

            else:
                gps_topic_name = config.get("gps_topic") or self._topic(ns, "sensors/gps_0/fix")
                gps_topic = roslibpy.Topic(ros, gps_topic_name, "sensor_msgs/NavSatFix")
                gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))
                state._subscriptions.append(gps_topic)

            odom_topic = roslibpy.Topic(
                ros, self._topic(ns, "platform/odom/filtered"), "nav_msgs/Odometry"
            )
            odom_topic.subscribe(lambda msg: self._on_odom(node.id, msg))
            state._subscriptions.append(odom_topic)

            battery_topic = roslibpy.Topic(
                ros, self._topic(ns, "platform/bms/state"), "sensor_msgs/BatteryState"
            )
            battery_topic.subscribe(lambda msg: self._on_battery(node.id, msg))
            state._subscriptions.append(battery_topic)

            imu_topic = roslibpy.Topic(
                ros, self._topic(ns, "platform/imu/data"), "sensor_msgs/Imu"
            )
            imu_topic.subscribe(lambda msg: self._on_imu(node.id, msg))
            state._subscriptions.append(imu_topic)

            if "lidar" in selected:
                lidar_topic_name = config.get("lidar_topic") or self._topic(
                    ns, "sensors/lidar2d_0/scan"
                )
                lidar_topic = roslibpy.Topic(ros, lidar_topic_name, "sensor_msgs/LaserScan")
                lidar_topic.subscribe(lambda msg: self._on_lidar(node.id, msg))
                state._subscriptions.append(lidar_topic)

            logger.info(
                "Jackal [%s]: connected to %s:%d (%s mode, ns='%s')",
                node.name, host, port, position_source, ns or "/",
            )
            return True, ""

        except Exception as e:
            logger.error("Jackal [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False, str(e)

    def _on_close(self, node_id: str) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.connected = False
            logger.warning("Jackal [%s]: rosbridge connection closed", node_id)

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

    def _on_odom(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        state.speed = (
            msg.get("twist", {}).get("twist", {}).get("linear", {}).get("x", 0.0)
        )
        state.last_message_time = time.monotonic()

    def _on_battery(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        pct = msg.get("percentage", -1.0)
        if pct >= 0.0:
            # Some BMS nodes publish 0-100, others 0.0-1.0 per the ROS message convention
            state.battery_percent = pct if pct > 1.0 else pct * 100.0
        state.last_message_time = time.monotonic()

    def _on_imu(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        roll, pitch, yaw = self._quat_to_euler(msg.get("orientation", {}))
        av = msg.get("angular_velocity", {})
        state.imu = IMUData(
            roll=roll,
            pitch=pitch,
            yaw=yaw,
            angular_velocity_x=av.get("x", 0.0),
            angular_velocity_y=av.get("y", 0.0),
            angular_velocity_z=av.get("z", 0.0),
        )
        state.last_message_time = time.monotonic()

    def _on_lidar(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        ranges = msg.get("ranges", [])
        angle_min = msg.get("angle_min", 0.0)
        angle_increment = msg.get("angle_increment", 0.0)
        range_min = msg.get("range_min", 0.0)
        range_max = msg.get("range_max", 0.0)

        points = []
        for i, r in enumerate(ranges):
            if r is None or not math.isfinite(r) or r < range_min or r > range_max:
                continue
            angle = angle_min + i * angle_increment
            points.append(LidarPoint(x=r * math.cos(angle), y=r * math.sin(angle)))

        state.lidar = LidarScan(
            points=points, frame_id="lidar", range_min=range_min, range_max=range_max, dimensions=2
        )
        state.last_message_time = time.monotonic()

    # ── Utilities ──────────────────────────────────────────────────────────────

    @staticmethod
    def _quat_to_euler(q: dict) -> tuple[float, float, float]:
        """Convert quaternion {x,y,z,w} to roll/pitch/yaw in radians."""
        w = q.get("w", 1.0)
        x = q.get("x", 0.0)
        y = q.get("y", 0.0)
        z = q.get("z", 0.0)

        sinr_cosp = 2.0 * (w * x + y * z)
        cosr_cosp = 1.0 - 2.0 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)

        sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
        pitch = math.asin(sinp)

        siny_cosp = 2.0 * (w * z + x * y)
        cosy_cosp = 1.0 - 2.0 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)

        return roll, pitch, yaw

    def _publish_twist(self, state: _NodeState, linear: float, angular: float) -> None:
        if not state.cmd_vel_pub:
            return
        try:
            from twisted.internet import reactor as _reactor
            msg = roslibpy.Message({
                "linear": {"x": float(linear), "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": float(angular)},
            })

            def _do_publish():
                try:
                    state.cmd_vel_pub.publish(msg)
                except Exception as e:
                    logger.warning("Jackal: /cmd_vel publish raised: %s", e)

            _reactor.callFromThread(_do_publish)
        except Exception as e:
            logger.warning("Jackal: /cmd_vel publish failed: %s", e)

    def _publish_zero_twist(self, state: _NodeState) -> None:
        self._publish_twist(state, 0.0, 0.0)

    # ── Disconnect ─────────────────────────────────────────────────────────────

    async def disconnect(self, node: Node) -> None:
        state = self._nodes.pop(node.id, None)
        if not state:
            return
        state.connected = False
        for sub in state._subscriptions:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        for pub in (state.cmd_vel_pub, state.goal_pose_pub):
            if pub:
                try:
                    pub.unadvertise()
                except Exception:
                    pass
        if state.ros:
            try:
                state.ros.close()
            except Exception:
                pass
        logger.info("Jackal [%s]: disconnected", node.name)

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
        Publishes a Nav2 goal_pose (PoseStamped) — one-shot, not a blocking
        controller. Nav2's bt_navigator plans and drives the path itself.

        Only supports local-frame (VICON) targets for now: a raw WGS84 target
        can't be turned into a Nav2 "map"-frame goal without the robot's own
        GPS→map localisation (e.g. navsat_transform_node), which isn't set up
        here. GPS-mode devices should use cmd_move_to only once that exists.
        """
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        if not state.goal_pose_pub:
            return CommandResult(success=False, message="goal_pose topic not advertised")

        if x is None or y is None:
            return CommandResult(
                success=False,
                message=(
                    "Jackal move_to requires a local (VICON) target — "
                    "GPS-frame Nav2 goals are not implemented"
                ),
            )

        try:
            from twisted.internet import reactor as _reactor
            msg = roslibpy.Message({
                "header": {"frame_id": "map", "stamp": {"sec": 0, "nanosec": 0}},
                "pose": {
                    "position": {"x": float(x), "y": float(y), "z": float(z or 0.0)},
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
            })
            _reactor.callFromThread(state.goal_pose_pub.publish, msg)
        except Exception as e:
            return CommandResult(success=False, message=f"Failed to publish goal: {e}")

        logger.info("Jackal [%s]: Nav2 goal published — local (%.2f, %.2f)", node.name, x, y)
        return CommandResult(
            success=True,
            message=(
                f"Nav2 goal sent to local ({x:.2f}, {y:.2f}). Assumes the VICON home "
                "origin is aligned with the Jackal's Nav2 map frame — verify this if "
                "the robot doesn't arrive at the expected position."
            ),
        )

    async def cmd_stop(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        self._publish_zero_twist(state)
        logger.info("Jackal [%s]: stop", node.name)
        return CommandResult(
            success=True,
            message=(
                "Zero velocity sent. If Nav2 is actively navigating, its controller "
                "may resume commanding velocity moments later — this does not cancel "
                "the underlying Nav2 goal."
            ),
        )

    async def cmd_return_home(self, node: Node) -> CommandResult:
        if not node.home_position:
            return CommandResult(success=False, message="No home position set")

        if node.local_origin:
            # Direct call bypasses DeviceProxy's GPS→local conversion — do it here.
            origin = node.local_origin
            R = 6_371_000.0
            dlat = math.radians(node.home_position.lat - origin.lat)
            dlon = math.radians(node.home_position.lon - origin.lon)
            local_y = R * dlat
            local_x = R * dlon * math.cos(math.radians(origin.lat))
            return await self.cmd_move_to(node, x=local_x, y=local_y)

        return await self.cmd_move_to(
            node, lat=node.home_position.lat, lon=node.home_position.lon
        )

    # ── Camera feed ────────────────────────────────────────────────────────────

    async def get_video_stream_url(self, node: Node) -> str | None:
        if not node.specs or not any(
            c.capability == DeviceCapability.CAMERA for c in node.specs.capabilities
        ):
            return None
        host = node.config.get("host", "localhost")
        ns = (node.config.get("namespace") or "").strip("/")
        camera_topic = node.config.get("camera_topic") or self._topic(
            ns, "sensors/camera_0/color/image"
        )
        # Requires web_video_server running on the robot: ros2 run web_video_server web_video_server
        return f"http://{host}:8080/stream?topic={camera_topic}"

    # ── Custom commands ────────────────────────────────────────────────────────

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        """
        cmd_vel — continuous manual driving for teleop-style control plugins.
        params: linear, angular, both normalised [-1, 1].
        """
        if envelope.command_type != "cmd_vel":
            return CommandResult(
                success=False, message=f"Unknown command: {envelope.command_type}"
            )
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")

        max_linear = float(node.config.get("max_linear_speed", 1.0))
        max_angular = float(node.config.get("max_angular_speed", 1.0))
        # Negate angular: teleop right=+1, but ROS angular.z positive=CCW (left) —
        # matches the same convention used by turtlebot3's handle_custom_command.
        linear = max(-1.0, min(1.0, float(envelope.params.get("linear", 0.0)))) * max_linear
        angular = -max(-1.0, min(1.0, float(envelope.params.get("angular", 0.0)))) * max_angular

        self._publish_twist(state, linear, angular)
        return CommandResult(success=True, message="cmd_vel sent")

    # ── Safe state ─────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state:
            self._publish_zero_twist(state)
        logger.warning("Jackal [%s]: safe state — zero velocity sent", node.name)
        return CommandResult(
            success=True,
            message=(
                "Zero velocity sent. If Nav2 is actively navigating it may resume "
                "commanding velocity — goal cancellation over rosbridge isn't implemented."
            ),
        )

    # ── Telemetry stream ───────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
            now = time.monotonic()
            position_source = node.config.get("position_source", "vicon")

            if position_source == "gps":
                if (
                    not state.position_received
                    and not state._no_fix_warned
                    and now - state.connect_time > self.POSITION_FIX_TIMEOUT
                ):
                    state._no_fix_warned = True
                    logger.warning(
                        "Jackal [%s]: no position after %.0fs", node.name, self.POSITION_FIX_TIMEOUT
                    )
                    if self._context:
                        await self._context.emit_event(
                            "No position data",
                            f"No position received after {self.POSITION_FIX_TIMEOUT:.0f}s. "
                            "Check the GPS topic and gps_topic config.",
                            EventSeverity.WARNING,
                        )

                position_stale = (
                    state.position_received
                    and now - state.last_position_time > self.POSITION_STALE_TIMEOUT
                )
                if position_stale and not state._stale_warned:
                    state._stale_warned = True
                    logger.warning("Jackal [%s]: position updates stopped", node.name)
                    if self._context:
                        await self._context.emit_event(
                            "Position tracking lost",
                            f"No position update for {self.POSITION_STALE_TIMEOUT:.0f}s. "
                            "GPS signal may be lost.",
                            EventSeverity.WARNING,
                        )
                if not position_stale and state._stale_warned:
                    state._stale_warned = False

                position = Position(
                    lat=state.lat, lon=state.lon, alt=state.alt
                ) if state.position_received and not position_stale else None
                status_text = (
                    "Position lost" if position_stale
                    else "Online" if state.position_received
                    else "Connected — waiting for GPS fix"
                )
            else:
                # VICON mode: node.position is set by the core vicon_manager,
                # which also emits its own no-fix warning — nothing to do here.
                position = None
                status_text = "Online" if node.position is not None else "Connected — waiting for VICON"

            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                speed=state.speed,
                battery=BatteryData(percentage=state.battery_percent),
                imu=state.imu,
                lidar=state.lidar,
                position=position,
                status_text=status_text,
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)
