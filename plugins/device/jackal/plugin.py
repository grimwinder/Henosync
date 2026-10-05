"""
Clearpath Jackal UGV device plugin for Henosync.

Connects via rosbridge (roslibpy) to a Jackal running Clearpath's ROS2 stack.
Positioning:
  - VICON mode: handled entirely by henosync core (vicon_manager) — a direct
    TCP connection to the VICON DataStream SDK, independent of rosbridge.
    No plugin code here beyond setting node.local_origin.
  - GPS  mode:  subscribes to the onboard GPS topic via rosbridge.

Movement (move_to):
  Proportional velocity controller — reads node.position (VICON yaw from
  pos.heading, or IMU yaw from state.imu.yaw in GPS mode) to steer toward
  the GPS target. Publishes geometry_msgs/Twist to platform/cmd_vel_unstamped
  at 10 Hz until arrival or cancellation. Works without Nav2.

Manual driving (cmd_vel custom command):
  For the `teleop` control plugin — normalised [-1, 1] linear/angular,
  scaled and published as a plain Twist.

All roslibpy publish() calls run via reactor.callFromThread() — Twisted's
WebSocket send is not thread-safe from the asyncio event loop thread.

Topics subscribed (all optionally prefixed with `namespace`, e.g. a200_0000):
  sensors/gps_0/fix                   sensor_msgs/NavSatFix
  platform/odom/filtered              nav_msgs/Odometry               (speed)
  platform/bms/state                  sensor_msgs/BatteryState        (battery)
  sensors/imu_0/data                  sensor_msgs/Imu                 (orientation)
  sensors/lidar2d_0/scan              sensor_msgs/LaserScan           (optional)

Topics published:
  platform/cmd_vel_unstamped           geometry_msgs/Twist
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
        self.nav2_goal_pub: Optional[Any] = None
        self.nav2_cancel_service: Optional[Any] = None

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

        # Odom pose — used to compute Nav2 goals in the robot's map frame.
        self.odom_x: float = 0.0
        self.odom_y: float = 0.0
        self.odom_yaw: float = 0.0

        # Timing
        self.connect_time: float = time.monotonic()
        self.last_position_time: float = 0.0
        self.last_message_time: float = 0.0

        # Set by cmd_stop/get_safe_state to interrupt an in-progress cmd_move_to
        self.stop_requested: bool = False

        # Warning flags — fire once to avoid spamming the operator
        self._no_fix_warned: bool = False
        self._stale_warned: bool = False

        self._subscriptions: list = []


class JackalPlugin(NodePlugin):
    """
    Clearpath Jackal UGV device plugin.

    Positioning: VICON (default, handled by core vicon_manager) or GPS.
    Movement: proportional velocity controller publishing Twist to
    platform/cmd_vel_unstamped — works without Nav2.
    """

    PLUGIN_ID = "jackal"
    PLUGIN_NAME = "Clearpath Jackal (ROS2)"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Clearpath Jackal UGV via rosbridge — ROS2 Clearpath stack, VICON/GPS positioning, proportional velocity controller"

    TELEMETRY_RATE_HZ: float = 2.0

    POSITION_FIX_TIMEOUT: float = 10.0
    POSITION_STALE_TIMEOUT: float = 3.0
    MESSAGE_TIMEOUT: float = 5.0

    ARRIVAL_THRESHOLD_M: float = 0.5
    MAX_LINEAR_VEL: float = 0.5
    MAX_ANGULAR_VEL: float = 1.0
    LINEAR_GAIN: float = 0.5
    ANGULAR_GAIN: float = 1.5
    ARRIVAL_POLL_S: float = 0.1

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
            ros.on("close", lambda *_: self._on_close(node.id))
            ros.on("error", lambda e: (
                logger.error("Jackal [%s]: rosbridge error: %s", node.name, e),
                failed_event.set(),
            ))

            reactor_ready = ensure_reactor()
            await asyncio.get_running_loop().run_in_executor(
                None, lambda: reactor_ready.wait(5.0)
            )
            if not reactor_ready.is_set():
                self._nodes.pop(node.id, None)
                return False, "Twisted reactor failed to start"

            from twisted.internet import reactor as _reactor
            _reactor.callFromThread(ros.connect)

            done, _ = await asyncio.wait(
                [
                    asyncio.create_task(connected_event.wait()),
                    asyncio.create_task(failed_event.wait()),
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
            if "nav2" in selected:
                capabilities.append(CapabilitySpec(capability=DeviceCapability.NAV2))

            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,
                capabilities=capabilities,
                coordinate_frame="local" if position_source == "vicon" else "gps",
            )

            if position_source == "vicon":
                # Position is published directly by the core vicon_manager.
                # local_origin defaults to (0, 0) — GPS conversion will be
                # approximate until the arena origin is configured elsewhere.
                node.local_origin = LocalOrigin(
                    lat=float(config.get("home_lat", 0.0)),
                    lon=float(config.get("home_lon", 0.0)),
                )

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
                ros,
                config.get("imu_topic") or self._topic(ns, "sensors/imu_0/data"),
                "sensor_msgs/Imu",
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

            if "nav2" in selected:
                nav2_topic = config.get("nav2_goal_topic") or self._topic(
                    ns, "goal_pose"
                )
                state.nav2_goal_pub = roslibpy.Topic(
                    ros, nav2_topic, "geometry_msgs/PoseStamped"
                )
                state.nav2_goal_pub.advertise()
                # Service to cancel all active Nav2 goals (zeros UUID = cancel all).
                nav2_cancel_topic = self._topic(
                    ns, "navigate_to_pose/_action/cancel_goal"
                )
                state.nav2_cancel_service = roslibpy.Service(
                    ros, nav2_cancel_topic, "action_msgs/srv/CancelGoal"
                )

            # Anchor liveness clock to connect time so a wrong namespace
            # (topics never publish) triggers DEGRADED within MESSAGE_TIMEOUT seconds.
            state.last_message_time = time.monotonic()

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
        pose = msg.get("pose", {}).get("pose", {})
        pos = pose.get("position", {})
        state.odom_x = float(pos.get("x", state.odom_x))
        state.odom_y = float(pos.get("y", state.odom_y))
        q = pose.get("orientation", {})
        qx = float(q.get("x", 0.0))
        qy = float(q.get("y", 0.0))
        qz = float(q.get("z", 0.0))
        qw = float(q.get("w", 1.0))
        state.odom_yaw = math.atan2(2.0 * (qw * qz + qx * qy), 1.0 - 2.0 * (qy * qy + qz * qz))
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

    def _set_nav2_max_speed(self, state: _NodeState, ns: str, max_speed: float) -> None:
        """Dynamically set Nav2 controller_server max_vel_x via set_parameters service."""
        try:
            from twisted.internet import reactor as _reactor
            svc_name = f"/{ns}/controller_server/set_parameters" if ns else "/controller_server/set_parameters"
            svc = roslibpy.Service(state.ros, svc_name, "rcl_interfaces/srv/SetParameters")
            req = roslibpy.ServiceRequest({
                "parameters": [{
                    "name": "FollowPath.max_vel_x",
                    "value": {"type": 3, "double_value": float(max_speed)},
                }]
            })
            _reactor.callFromThread(
                lambda: svc.call(req, lambda _: None, lambda _: None)
            )
            logger.info("Jackal: Nav2 max_vel_x set to %.2f m/s", max_speed)
        except Exception as e:
            logger.warning("Jackal: Nav2 set_parameters failed: %s", e)

    def _cancel_nav2_goals(self, state: _NodeState) -> None:
        """Cancel all active Nav2 goals via the navigate_to_pose action cancel service."""
        if not state.nav2_cancel_service:
            return
        try:
            from twisted.internet import reactor as _reactor
            req = roslibpy.ServiceRequest(
                {"goal_info": {"goal_id": {"uuid": [0] * 16}, "stamp": {"sec": 0, "nanosec": 0}}}
            )
            _reactor.callFromThread(
                lambda: state.nav2_cancel_service.call(req, lambda _: None, lambda _: None)
            )
        except Exception as e:
            logger.warning("Jackal: Nav2 cancel failed: %s", e)

    def _publish_nav2_goal(self, state: _NodeState, x: float, y: float) -> None:
        if not state.nav2_goal_pub:
            return
        try:
            from twisted.internet import reactor as _reactor
            msg = roslibpy.Message({
                "header": {"frame_id": "map"},
                "pose": {
                    "position": {"x": float(x), "y": float(y), "z": 0.0},
                    "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
                },
            })
            _reactor.callFromThread(lambda: state.nav2_goal_pub.publish(msg))
        except Exception as e:
            logger.warning("Jackal: nav2 goal publish failed: %s", e)

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
        for pub in filter(None, [state.cmd_vel_pub, state.nav2_goal_pub]):
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
        arrival_radius_m: Optional[float] = None,
        max_speed: Optional[float] = None,
    ) -> CommandResult:
        """
        Navigation mode depends on whether the operator selected the Nav2 capability:
          Nav2 selected:  publish a PoseStamped goal to move_base_simple/goal; poll
                          for arrival. Nav2 handles path planning and obstacle avoidance.
          Nav2 not selected: proportional velocity controller publishing Twist directly.

        For VICON-mode devices (coordinate_frame="local"), DeviceProxy converts
        the WGS84 target to local x/y metres before dispatch; this method converts
        them back to GPS for haversine distance checks.
        """
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        if node.position is None:
            return CommandResult(success=False, message="No position fix — cannot navigate")

        # VICON mode: DeviceProxy dispatches x/y metres; convert back to GPS
        use_vicon = x is not None and y is not None
        if use_vicon:
            if not node.local_origin:
                return CommandResult(success=False, message="No local_origin set — add a home position")
            R = 6_371_000.0
            lat = node.local_origin.lat + math.degrees(y / R)
            lon = node.local_origin.lon + math.degrees(x / (R * math.cos(math.radians(node.local_origin.lat))))

        threshold = arrival_radius_m if arrival_radius_m is not None else self.ARRIVAL_THRESHOLD_M
        has_nav2 = node.specs and any(
            cs.capability == DeviceCapability.NAV2 for cs in node.specs.capabilities
        )

        if has_nav2:
            # ── Nav2 path ────────────────────────────────────────────────────
            # The Nav2 map frame has its origin at the odom start (wherever the
            # robot was when Nav2 launched) and axes aligned with the robot's
            # initial heading.  VICON and GPS coordinates are in a different
            # frame, so we cannot use them directly as Nav2 goals.
            #
            # Strategy: compute the delta from the robot's current position to
            # the target IN the source frame, rotate it into the Nav2 map frame
            # using the difference between odom yaw and robot heading, then add
            # it to the robot's current odom position.
            #
            # For VICON: robot position comes from node.position (lon=x_m, lat=y_m).
            # For GPS: robot position is node.position (lat/lon); delta via haversine.

            if use_vicon:
                # Robot's VICON position in metres — node.position.lat/lon are GPS (degrees),
                # the raw metres live in node.telemetry from vicon_manager's custom fields.
                rx = float(node.telemetry.get("vicon_x", 0.0))
                ry = float(node.telemetry.get("vicon_y", 0.0))
                dx_src = float(x) - rx
                dy_src = float(y) - ry
                vicon_yaw = node.position.heading if node.position.heading is not None else state.odom_yaw
            else:
                # Delta in GPS-derived local space (equirectangular)
                R = 6_371_000.0
                pos = node.position
                dx_src = R * math.radians(lon - pos.lon) * math.cos(math.radians(pos.lat))
                dy_src = R * math.radians(lat - pos.lat)
                vicon_yaw = pos.heading if pos.heading is not None else (state.imu.yaw if state.imu.yaw else state.odom_yaw)

            # Rotate delta from source frame into Nav2 odom/map frame
            theta = state.odom_yaw - vicon_yaw
            dx_map = dx_src * math.cos(theta) - dy_src * math.sin(theta)
            dy_map = dx_src * math.sin(theta) + dy_src * math.cos(theta)
            goal_x = state.odom_x + dx_map
            goal_y = state.odom_y + dy_map

            logger.info(
                "Jackal [%s]: Nav2 goal → map (%.3f, %.3f) | odom (%.3f, %.3f) | delta (%.3f, %.3f) | "
                "odom_yaw=%.3f src_yaw=%.3f",
                node.name, goal_x, goal_y, state.odom_x, state.odom_y, dx_map, dy_map,
                state.odom_yaw, vicon_yaw,
            )
            if max_speed is not None:
                ns = (node.config.get("namespace") or "").strip("/")
                self._set_nav2_max_speed(state, ns, min(float(max_speed), self.MAX_LINEAR_VEL))
            self._publish_nav2_goal(state, goal_x, goal_y)

            state.stop_requested = False
            try:
                while node.id in self._nodes and state.connected:
                    if state.stop_requested:
                        state.stop_requested = False
                        return CommandResult(success=False, message="Stopped")
                    pos = node.position
                    if pos is None:
                        await asyncio.sleep(self.ARRIVAL_POLL_S)
                        continue
                    R = 6_371_000.0
                    dy = R * math.radians(lat - pos.lat)
                    dx = R * math.radians(lon - pos.lon) * math.cos(math.radians(pos.lat))
                    if math.sqrt(dx * dx + dy * dy) < threshold:
                        return CommandResult(success=True, message="Arrived")
                    await asyncio.sleep(self.ARRIVAL_POLL_S)
                return CommandResult(success=False, message="Navigation aborted")
            finally:
                self._cancel_nav2_goals(state)

        else:
            # ── Proportional velocity controller ─────────────────────────────
            speed_cap = min(float(max_speed), self.MAX_LINEAR_VEL) if max_speed is not None else self.MAX_LINEAR_VEL
            logger.info(
                "Jackal [%s]: velocity controller → target GPS (%.8f, %.8f) | threshold %.2f m | speed_cap %.2f",
                node.name, lat, lon, threshold, speed_cap,
            )
            state.stop_requested = False
            _tick = 0
            try:
                while node.id in self._nodes and state.connected:
                    if state.stop_requested:
                        state.stop_requested = False
                        return CommandResult(success=False, message="Stopped")

                    pos = node.position
                    if pos is None:
                        await asyncio.sleep(self.ARRIVAL_POLL_S)
                        continue

                    R = 6_371_000.0
                    dy = R * math.radians(lat - pos.lat)
                    dx = R * math.radians(lon - pos.lon) * math.cos(math.radians(pos.lat))
                    distance = math.sqrt(dx * dx + dy * dy)

                    if distance < threshold:
                        return CommandResult(success=True, message="Arrived")

                    bearing = math.atan2(dy, dx)
                    heading = (
                        pos.heading
                        if (use_vicon and pos.heading is not None)
                        else state.imu.yaw
                    )
                    heading_error = math.atan2(
                        math.sin(bearing - heading),
                        math.cos(bearing - heading),
                    )
                    linear = min(
                        speed_cap,
                        self.LINEAR_GAIN * distance * max(0.0, math.cos(heading_error)),
                    )
                    angular = max(
                        -self.MAX_ANGULAR_VEL,
                        min(self.MAX_ANGULAR_VEL, self.ANGULAR_GAIN * heading_error),
                    )

                    _tick += 1
                    if _tick % 10 == 1:
                        logger.info(
                            "Jackal goto | pos (%.8f, %.8f) | target (%.8f, %.8f) | "
                            "dist=%.3fm bearing=%.3f heading=%.3f err=%.3f lin=%.3f ang=%.3f",
                            pos.lat, pos.lon, lat, lon,
                            distance, bearing, heading, heading_error, linear, angular,
                        )

                    self._publish_twist(state, linear, angular)
                    await asyncio.sleep(self.ARRIVAL_POLL_S)

                return CommandResult(success=False, message="Navigation aborted")
            finally:
                self._publish_zero_twist(state)

    async def cmd_stop(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        state.stop_requested = True
        self._publish_zero_twist(state)
        if state.nav2_cancel_service:
            # Cancel all active Nav2 goals — zeros UUID means "cancel all".
            self._cancel_nav2_goals(state)
        logger.info("Jackal [%s]: stop", node.name)
        return CommandResult(success=True, message="Stopped")

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
            state.stop_requested = True
            self._publish_zero_twist(state)
            if state.nav2_cancel_service:
                self._cancel_nav2_goals(state)
        logger.warning("Jackal [%s]: safe state — zero velocity sent, Nav2 goals cancelled", node.name)
        return CommandResult(success=True, message="Zero velocity sent; Nav2 goals cancelled.")

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
