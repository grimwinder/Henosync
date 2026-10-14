"""
Clearpath Jackal UGV device plugin for Henosync.

Connects via rosbridge (roslibpy) to a Jackal running Clearpath's ROS2 stack.
Positioning:
  - VICON mode: handled entirely by henosync core (vicon_manager) — a direct
    TCP connection to the VICON DataStream SDK, independent of rosbridge.
    No plugin code here beyond setting node.local_origin.
  - GPS  mode:  subscribes to the onboard GPS topic via rosbridge.

Movement (move_to):
  Two modes — selected via the optional "Onboard Controller" capability:
    Default:         proportional velocity controller in Henosync; publishes
                     geometry_msgs/Twist to platform/cmd_vel_unstamped at 10 Hz.
    Onboard Ctrl:    Henosync publishes the waypoint (or, via follow_path, a
                     whole path) to the robot; henosync_controller.py on the
                     robot runs the proportional controller locally and
                     reports progress. Its pose comes from Henosync's relay
                     (henosync/vicon_pose) or, with onboard_pose_source=onboard,
                     from vicon_pose_publisher.py on the robot — then the robot
                     keeps driving its path while rosbridge is down, and
                     Henosync picks its progress back up after reconnecting.

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
  henosync/progress                   std_msgs/String  JSON           (onboard_ctrl only)

Topics published:
  platform/cmd_vel_unstamped           geometry_msgs/Twist
  henosync/waypoint                    std_msgs/String  JSON           (onboard_ctrl only)
  henosync/vicon_pose                  geometry_msgs/Pose2D           (onboard_ctrl + relay pose only)
"""

import asyncio
import json as _json
import logging
import math
import time
import uuid
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

        # Onboard controller publishers (created only when onboard_ctrl selected)
        self.waypoint_pub: Optional[Any] = None
        self.vicon_pose_pub: Optional[Any] = None

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

        # Set by cmd_stop/get_safe_state to interrupt an in-progress cmd_move_to
        self.stop_requested: bool = False

        # Warning flags — fire once to avoid spamming the operator
        self._no_fix_warned: bool = False
        self._stale_warned: bool = False

        self._subscriptions: list = []


class _PathTracker:
    """
    Progress of the path the onboard controller is driving, keyed by node id
    in _PATHS. Module-level rather than in _NodeState because a reconnect
    creates a new plugin instance: cmd_follow_path keeps waiting in the old
    instance while the new instance's progress subscription updates this.
    """

    def __init__(self, path_id: str, total: int, state: _NodeState):
        self.path_id = path_id
        self.total = total
        self.state = state  # live connection — swapped in by connect() after a reconnect
        self.completed: int = 0
        self.done: bool = False
        self.stopped: bool = False
        self.stop_requested: bool = False
        self.heard: bool = False
        now = time.monotonic()
        self.last_heard: float = now   # last progress message for this path
        self.last_change: float = now  # last time a waypoint was reached


_PATHS: dict[str, _PathTracker] = {}


class JackalPlugin(NodePlugin):
    """
    Clearpath Jackal UGV device plugin.

    Positioning: VICON (default, handled by core vicon_manager) or GPS.
    Movement: proportional velocity controller (default) or onboard controller
    (when ONBOARD_CTRL capability is selected — robot runs henosync_controller.py).
    """

    PLUGIN_ID = "jackal"
    PLUGIN_NAME = "Clearpath Jackal (ROS2)"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Clearpath Jackal UGV via rosbridge — ROS2 Clearpath stack, VICON/GPS positioning, proportional velocity controller or onboard controller"

    TELEMETRY_RATE_HZ: float = 2.0

    POSITION_FIX_TIMEOUT: float = 10.0
    POSITION_STALE_TIMEOUT: float = 3.0
    MESSAGE_TIMEOUT: float = 5.0

    ARRIVAL_THRESHOLD_M: float = 0.2
    MAX_LINEAR_VEL: float = 0.5
    MAX_ANGULAR_VEL: float = 1.0
    LINEAR_GAIN: float = 0.5
    ANGULAR_GAIN: float = 1.5
    ARRIVAL_POLL_S: float = 0.1

    # Onboard controller path tracking — the robot re-sends progress at 1 Hz
    PROGRESS_ACK_TIMEOUT_S: float = 5.0   # no progress at all → controller not running
    LINK_LOST_S: float = 3.0              # no progress for this long → link considered down
    LINK_LOSS_GRACE_S: float = 300.0      # give up if the link stays down this long

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
            if "onboard_ctrl" in selected:
                capabilities.append(CapabilitySpec(capability=DeviceCapability.ONBOARD_CTRL))

            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,
                capabilities=capabilities,
                coordinate_frame="local" if position_source == "vicon" else "gps",
            )

            if position_source == "vicon":
                # Position is published directly by the core vicon_manager.
                node.local_origin = LocalOrigin(lat=0.0, lon=0.0, alt=0.0)

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

            if "onboard_ctrl" in selected:
                # Publish waypoints (and, in relay mode, VICON pose) to the robot;
                # subscribe to the controller's progress reports.
                state.waypoint_pub = roslibpy.Topic(
                    ros, self._topic(ns, "henosync/waypoint"), "std_msgs/String"
                )
                state.waypoint_pub.advertise()

                if config.get("onboard_pose_source", "relay") == "relay":
                    state.vicon_pose_pub = roslibpy.Topic(
                        ros, self._topic(ns, "henosync/vicon_pose"), "geometry_msgs/Pose2D"
                    )
                    state.vicon_pose_pub.advertise()

                progress_topic = roslibpy.Topic(
                    ros, self._topic(ns, "henosync/progress"), "std_msgs/String"
                )
                progress_topic.subscribe(lambda msg: self._on_progress(node.id, msg))
                state._subscriptions.append(progress_topic)

                # Reconnected mid-path: let the waiting cmd_follow_path use this connection.
                tracker = _PATHS.get(node.id)
                if tracker:
                    tracker.state = state

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
        state.last_message_time = time.monotonic()

    def _on_progress(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.last_message_time = time.monotonic()
        tracker = _PATHS.get(node_id)
        if not tracker:
            return
        try:
            data = _json.loads(msg.get("data", ""))
        except ValueError:
            return
        if data.get("path_id") != tracker.path_id:
            return
        now = time.monotonic()
        tracker.heard = True
        tracker.last_heard = now
        completed = int(data.get("completed", 0))
        if completed > tracker.completed:
            tracker.completed = completed
            tracker.last_change = now
        tracker.done = bool(data.get("done", False))
        tracker.stopped = bool(data.get("stopped", False))

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

    def _publish_waypoint(self, state: _NodeState, waypoint_json: str) -> None:
        if not state.waypoint_pub:
            return
        try:
            from twisted.internet import reactor as _reactor
            msg = roslibpy.Message({"data": waypoint_json})
            _reactor.callFromThread(lambda: state.waypoint_pub.publish(msg))
        except Exception as e:
            logger.warning("Jackal: waypoint publish failed: %s", e)

    def _publish_stop_sentinel(self, state: _NodeState) -> None:
        self._publish_waypoint(state, '{"stop": true}')

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
        for pub in filter(None, [state.cmd_vel_pub, state.waypoint_pub, state.vicon_pose_pub]):
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

        threshold = arrival_radius_m if (arrival_radius_m is not None and arrival_radius_m > 0) else self.ARRIVAL_THRESHOLD_M
        speed_cap = min(float(max_speed), self.MAX_LINEAR_VEL) if max_speed is not None else self.MAX_LINEAR_VEL

        if use_vicon and self._has_onboard(node, state):
            # ── Onboard controller path — a path of one waypoint ──────────────
            return await self.cmd_follow_path(
                node, [{"x": float(x), "y": float(y)}], arrival_radius_m, max_speed
            )

        else:
            # ── Proportional velocity controller (default) ────────────────────
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

    @staticmethod
    def _has_onboard(node: Node, state: _NodeState) -> bool:
        return (
            state.waypoint_pub is not None
            and node.specs is not None
            and any(cs.capability == DeviceCapability.ONBOARD_CTRL for cs in node.specs.capabilities)
        )

    async def cmd_follow_path(
        self,
        node: Node,
        waypoints: list[dict[str, float]],
        arrival_radius_m: Optional[float] = None,
        max_speed: Optional[float] = None,
    ) -> CommandResult:
        """
        Onboard controller only (VICON mode): send the whole path to
        henosync_controller.py and wait for its progress reports. While the
        rosbridge link is down the robot keeps driving (given an onboard pose
        source) and this keeps waiting; after a reconnect the controller's
        1 Hz progress re-send tells us how far it got.
        """
        state = self._nodes.get(node.id)
        if (
            not state
            or not self._has_onboard(node, state)
            or not waypoints
            or waypoints[0].get("x") is None
        ):
            return CommandResult(success=False, message="follow_path not implemented")
        if not state.connected:
            return CommandResult(success=False, message="Not connected")

        threshold = arrival_radius_m if (arrival_radius_m is not None and arrival_radius_m > 0) else self.ARRIVAL_THRESHOLD_M
        speed_cap = min(float(max_speed), self.MAX_LINEAR_VEL) if max_speed is not None else self.MAX_LINEAR_VEL
        timeout = float(node.config.get("onboard_timeout_s", 120.0))

        tracker = _PathTracker(uuid.uuid4().hex[:8], len(waypoints), state)
        _PATHS[node.id] = tracker
        self._publish_waypoint(state, _json.dumps({
            "path_id": tracker.path_id,
            "path": [{"x": float(w["x"]), "y": float(w["y"])} for w in waypoints],
            "arrival_radius": threshold,
            "max_speed": speed_cap,
        }))
        logger.info(
            "Jackal [%s]: onboard ctrl → path %s, %d waypoint(s) radius=%.3f speed=%.3f",
            node.name, tracker.path_id, len(waypoints), threshold, speed_cap,
        )

        link_down_logged = False
        try:
            while True:
                await asyncio.sleep(0.2)
                now = time.monotonic()
                result_data = {"completed": tracker.completed}

                if tracker.done:
                    logger.info("Jackal [%s]: onboard controller — path complete", node.name)
                    return CommandResult(success=True, message="Arrived", data=result_data)
                if tracker.stop_requested or tracker.stopped:
                    return CommandResult(success=False, message="Stopped", data=result_data)

                if not tracker.heard:
                    if now - tracker.last_heard > self.PROGRESS_ACK_TIMEOUT_S:
                        self._publish_stop_sentinel(tracker.state)
                        return CommandResult(
                            success=False,
                            message="Onboard controller not responding — is henosync_controller.py running?",
                            data=result_data,
                        )
                    continue

                if now - tracker.last_heard > self.LINK_LOST_S:
                    if not link_down_logged:
                        link_down_logged = True
                        logger.warning(
                            "Jackal [%s]: no progress from robot — link down, robot continues onboard "
                            "(%d/%d waypoints reached)", node.name, tracker.completed, tracker.total,
                        )
                    if now - tracker.last_heard > self.LINK_LOSS_GRACE_S:
                        return CommandResult(
                            success=False,
                            message=f"Link to robot lost for {self.LINK_LOSS_GRACE_S:.0f}s",
                            data=result_data,
                        )
                    continue

                if link_down_logged:
                    link_down_logged = False
                    logger.info(
                        "Jackal [%s]: progress resumed — %d/%d waypoints reached",
                        node.name, tracker.completed, tracker.total,
                    )
                    # Time spent disconnected doesn't count against the waypoint timeout.
                    tracker.last_change = now

                if now - tracker.last_change > timeout:
                    self._publish_stop_sentinel(tracker.state)
                    return CommandResult(
                        success=False,
                        message=f"Onboard controller timeout — no waypoint reached in {timeout:.0f}s",
                        data=result_data,
                    )
        finally:
            if _PATHS.get(node.id) is tracker:
                del _PATHS[node.id]

    async def cmd_stop(self, node: Node) -> CommandResult:
        tracker = _PATHS.get(node.id)
        if tracker:
            tracker.stop_requested = True
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return CommandResult(success=False, message="Not connected")
        state.stop_requested = True
        self._publish_zero_twist(state)
        if state.waypoint_pub:
            self._publish_stop_sentinel(state)
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
        tracker = _PATHS.get(node.id)
        if tracker:
            tracker.stop_requested = True
        state = self._nodes.get(node.id)
        if state:
            state.stop_requested = True
            self._publish_zero_twist(state)
            if state.waypoint_pub:
                self._publish_stop_sentinel(state)
        logger.warning("Jackal [%s]: safe state — zero velocity sent", node.name)
        return CommandResult(success=True, message="Zero velocity sent.")

    # ── Telemetry stream ───────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        # Wait one tick before publishing to vicon_pose_pub — gives rosbridge time
        # to process the advertise message sent during connect() before the first
        # publish arrives, avoiding "topic not yet advertised" errors.
        await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
            now = time.monotonic()
            position_source = node.config.get("position_source", "vicon")

            # Publish VICON pose to robot when onboard controller is active
            if state.vicon_pose_pub:
                try:
                    from twisted.internet import reactor as _reactor
                    vx = float(node.telemetry.get("vicon_x", 0.0))
                    vy = float(node.telemetry.get("vicon_y", 0.0))
                    vtheta = float(node.telemetry.get("vicon_heading", 0.0))
                    _pose_msg = roslibpy.Message({"x": vx, "y": vy, "theta": vtheta})
                    _reactor.callFromThread(lambda: state.vicon_pose_pub.publish(_pose_msg))
                except Exception:
                    pass

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
