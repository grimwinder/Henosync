"""
Jackal UGV plugin — Clearpath Jackal via ROS2 rosbridge.

Milestone 1 ✓: Connect to rosbridge, heartbeat telemetry, device goes Online.
Milestone 2 ✓: GPS on map, IMU heading, battery, speed.
Milestone 3 ✓: Stop and emergency stop via /cmd_vel zero-velocity Twist.
Milestone 4 ✓: Move-to GPS waypoint via Nav2 /goal_pose (requires Nav2 running).
Milestone 5 ✓: Camera feed via web_video_server.
"""

import asyncio
import logging
import math
import threading
import time
from typing import Any, AsyncGenerator, Optional

logger = logging.getLogger(__name__)

# Twisted's reactor is a process-wide singleton — once started it cannot be
# restarted. Track whether it's running so reconnects use callFromThread
# instead of ros.run() (which would raise ReactorNotRestartable).
_reactor_started = threading.Event()

from henosync_sdk import (
    BatteryData,
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    IMUData,
    Node,
    NodePlugin,
    NodePluginContext,
    Position,
    TelemetryFrame,
)

try:
    import roslibpy
    ROSLIBPY_AVAILABLE = True
except ImportError:
    ROSLIBPY_AVAILABLE = False
    logger.warning("roslibpy not installed — run: pip install roslibpy")

# ── Topic names — update if your Jackal's ROS2 namespace differs ─────────────
GPS_TOPIC     = "/navsat/fix"          # sensor_msgs/NavSatFix
IMU_TOPIC     = "/imu/data"            # sensor_msgs/Imu
BATTERY_TOPIC = "/battery_state"       # sensor_msgs/BatteryState
ODOM_TOPIC    = "/odometry/filtered"   # nav_msgs/Odometry
CMDVEL_TOPIC  = "/cmd_vel"             # geometry_msgs/Twist
GOAL_TOPIC    = "/goal_pose"           # geometry_msgs/PoseStamped


class _NodeState:
    def __init__(self):
        self.connected: bool = False
        self.ros: Optional[Any] = None  # roslibpy.Ros instance

        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.heading: float = 0.0
        self.speed: float = 0.0
        self.battery_percent: float = 0.0
        self.gps_received: bool = False
        self.battery_received: bool = False

        # GPS origin captured on first fix — used by cmd_move_to for
        # equirectangular projection into Nav2's local map frame.
        self.origin_lat: float = 0.0
        self.origin_lon: float = 0.0

        # Monotonic timestamp of the last received ROS topic message.
        # Used to detect silent TCP drops where ros.is_connected stays True
        # but no data is flowing.
        self.last_message_time: float = 0.0

        self._topics: list[Any] = []


class JackalPlugin(NodePlugin):
    """
    Device plugin for Clearpath Jackal UGV via ROS2 rosbridge (roslibpy).
    Connects over WiFi — no ROS2 install required on the Henosync machine.
    """

    PLUGIN_ID = "jackal"
    PLUGIN_NAME = "Clearpath Jackal UGV"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Plugin for Clearpath Jackal UGV via ROS2 rosbridge"

    # If no ROS topic message arrives within this window, is_connected() returns
    # False even if the WebSocket appears alive (silent TCP half-open detection).
    MESSAGE_TIMEOUT: float = 10.0

    def __init__(self):
        super().__init__()
        self._nodes: dict[str, _NodeState] = {}

    # ── Connect ───────────────────────────────────────────────────────────────

    async def connect(
        self, node: Node, config: dict[str, Any], context: NodePluginContext
    ) -> tuple[bool, str]:
        if not ROSLIBPY_AVAILABLE:
            return False, "roslibpy not installed — run: pip install roslibpy"

        self._context = context

        host = config.get("host", "localhost")
        port = int(config.get("port", 9090))

        state = _NodeState()
        self._nodes[node.id] = state

        try:
            ros = roslibpy.Ros(host=host, port=port)

            connected_event = asyncio.Event()
            failed_event = asyncio.Event()

            def _on_ready():
                connected_event.set()

            def _on_error(e):
                logger.error("Jackal [%s]: rosbridge error: %s", node.name, e)
                failed_event.set()

            ros.on_ready(_on_ready)
            ros.on("close", lambda: self._on_close(node.id))
            ros.on("error", _on_error)

            if not _reactor_started.is_set():
                _reactor_started.set()
                asyncio.get_running_loop().run_in_executor(None, ros.run)
            else:
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
                ros.terminate()
                self._nodes.pop(node.id, None)
                return False, reason

            state.ros = ros
            state.connected = True
            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.GPS),
                    CapabilitySpec(capability=DeviceCapability.IMU),
                    CapabilitySpec(capability=DeviceCapability.BATTERY),
                    CapabilitySpec(capability=DeviceCapability.CAMERA),
                    CapabilitySpec(capability=DeviceCapability.MOVE_2D),
                ],
                coordinate_frame="gps",
            )
            logger.info("Jackal [%s]: connected to %s:%d", node.name, host, port)

            self._subscribe_topics(node, state)
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

    # ── Topic subscriptions ───────────────────────────────────────────────────

    def _subscribe_topics(self, node: Node, state: _NodeState) -> None:
        gps_topic = roslibpy.Topic(state.ros, GPS_TOPIC, "sensor_msgs/NavSatFix")
        gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))
        state._topics.append(gps_topic)

        imu_topic = roslibpy.Topic(state.ros, IMU_TOPIC, "sensor_msgs/Imu")
        imu_topic.subscribe(lambda msg: self._on_imu(node.id, msg))
        state._topics.append(imu_topic)

        battery_topic = roslibpy.Topic(state.ros, BATTERY_TOPIC, "sensor_msgs/BatteryState")
        battery_topic.subscribe(lambda msg: self._on_battery(node.id, msg))
        state._topics.append(battery_topic)

        odom_topic = roslibpy.Topic(state.ros, ODOM_TOPIC, "nav_msgs/Odometry")
        odom_topic.subscribe(lambda msg: self._on_odom(node.id, msg))
        state._topics.append(odom_topic)

        logger.info(
            "Jackal [%s]: subscribed to %s, %s, %s, %s",
            node.name, GPS_TOPIC, IMU_TOPIC, BATTERY_TOPIC, ODOM_TOPIC,
        )

    def _on_gps(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        state.lat = msg.get("latitude", 0.0)
        state.lon = msg.get("longitude", 0.0)
        state.alt = msg.get("altitude", 0.0)
        if not state.gps_received:
            # Capture origin on first fix for equirectangular move-to projection
            state.origin_lat = state.lat
            state.origin_lon = state.lon
            state.gps_received = True
        state.last_message_time = time.monotonic()

    def _on_imu(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        q = msg.get("orientation", {})
        qx = q.get("x", 0.0)
        qy = q.get("y", 0.0)
        qz = q.get("z", 0.0)
        qw = q.get("w", 1.0)
        yaw_rad = math.atan2(
            2.0 * (qw * qz + qx * qy),
            1.0 - 2.0 * (qy ** 2 + qz ** 2),
        )
        state.heading = math.degrees(yaw_rad) % 360
        state.last_message_time = time.monotonic()

    def _on_battery(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        # sensor_msgs/BatteryState percentage is 0.0–1.0
        state.battery_percent = msg.get("percentage", 0.0) * 100.0
        state.battery_received = True
        state.last_message_time = time.monotonic()

    def _on_odom(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if not state:
            return
        twist = msg.get("twist", {}).get("twist", {})
        linear = twist.get("linear", {})
        vx = linear.get("x", 0.0)
        vy = linear.get("y", 0.0)
        state.speed = math.sqrt(vx ** 2 + vy ** 2)
        state.last_message_time = time.monotonic()

    # ── Disconnect ────────────────────────────────────────────────────────────

    async def disconnect(self, node: Node) -> None:
        state = self._nodes.pop(node.id, None)
        if not state:
            return
        state.connected = False
        for topic in state._topics:
            try:
                topic.unsubscribe()
            except Exception:
                pass
        if state.ros:
            try:
                state.ros.close()  # close WebSocket only — never stop the reactor
            except Exception:
                pass
        logger.info("Jackal [%s]: disconnected", node.name)

    # ── Liveness check (called by node_registry every 2 s) ───────────────────

    async def is_connected(self, node: Node) -> bool:
        """
        Reports whether the rosbridge connection is genuinely alive.

        Checks three conditions:
        1. state.connected — WebSocket close event has not fired
        2. ros.is_connected — Twisted-level connection flag
        3. last_message_time — real ROS topic data received recently
           (detects silent TCP drops where the WebSocket appears open
           but no data flows)
        """
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return False
        if state.ros is None or not state.ros.is_connected:
            return False
        # Only apply the message timeout after the first topic message arrives.
        if state.gps_received and (time.monotonic() - state.last_message_time) > self.MESSAGE_TIMEOUT:
            return False
        return True

    # ── Telemetry stream ──────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        """
        Yield telemetry at TELEMETRY_RATE_HZ until the node is removed.
        Connection checking is handled globally by node_registry via
        is_connected() — no connection logic belongs in this loop.
        """
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]

            if state.gps_received:
                status = (
                    f"GPS {state.lat:.5f}, {state.lon:.5f}  "
                    f"hdg {state.heading:.0f}°  "
                    f"batt {state.battery_percent:.0f}%  "
                    f"spd {state.speed:.1f} m/s"
                )
            else:
                status = "Connected — waiting for GPS"

            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                position=Position(
                    lat=state.lat,
                    lon=state.lon,
                    alt=state.alt,
                    heading=state.heading,
                ) if state.gps_received else None,
                battery=BatteryData(
                    percentage=state.battery_percent
                ) if state.battery_received else None,
                imu=IMUData(yaw=state.heading) if state.gps_received else None,
                speed=state.speed,
                status_text=status,
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── Commands ──────────────────────────────────────────────────────────────

    async def cmd_stop(self, node: Node, envelope: CommandEnvelope) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.ros:
            return CommandResult(success=False, message="Not connected")
        try:
            pub = roslibpy.Topic(state.ros, CMDVEL_TOPIC, "geometry_msgs/Twist")
            pub.publish(roslibpy.Message({
                "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
            }))
            logger.info("Jackal [%s]: stop command sent", node.name)
            return CommandResult(success=True, message="Stopped")
        except Exception as e:
            return CommandResult(success=False, message=str(e))

    async def cmd_move_to(self, node: Node, envelope: CommandEnvelope) -> CommandResult:
        state = self._nodes.get(node.id)
        if not state or not state.ros:
            return CommandResult(success=False, message="Not connected")
        if not state.gps_received:
            return CommandResult(success=False, message="No GPS fix yet")

        params = envelope.params
        try:
            target_lat = float(params.get("lat", 0))
            target_lon = float(params.get("lon", 0))
        except (TypeError, ValueError) as e:
            return CommandResult(success=False, message=f"Invalid params: {e}")

        # Equirectangular GPS → local x,y from first GPS fix (accurate <1 km)
        R = 6_371_000.0
        dlat = math.radians(target_lat - state.origin_lat)
        dlon = math.radians(target_lon - state.origin_lon)
        x = dlon * R * math.cos(math.radians(state.origin_lat))
        y = dlat * R

        # Bearing → yaw → quaternion (heading toward waypoint)
        bearing = math.atan2(x, y)
        qz = math.sin(bearing / 2.0)
        qw = math.cos(bearing / 2.0)

        try:
            pub = roslibpy.Topic(state.ros, GOAL_TOPIC, "geometry_msgs/PoseStamped")
            pub.publish(roslibpy.Message({
                "header": {"frame_id": "map"},
                "pose": {
                    "position":    {"x": x, "y": y, "z": 0.0},
                    "orientation": {"x": 0.0, "y": 0.0, "z": qz, "w": qw},
                },
            }))
            logger.info(
                "Jackal [%s]: move_to %.5f, %.5f (local x=%.2f y=%.2f)",
                node.name, target_lat, target_lon, x, y,
            )
            return CommandResult(
                success=True,
                message=f"Moving to {target_lat:.5f}, {target_lon:.5f}",
            )
        except Exception as e:
            return CommandResult(success=False, message=str(e))

    async def cmd_return_home(self, node: Node, envelope: CommandEnvelope) -> CommandResult:
        if not node.home_position:
            return CommandResult(success=False, message="No home position set")
        home = node.home_position
        fake_envelope = CommandEnvelope(
            command_type="move_to",
            params={"lat": home.lat, "lon": home.lon, "alt": home.alt},
        )
        return await self.cmd_move_to(node, fake_envelope)

    # ── Safe state ────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        return await self.cmd_stop(node, None)

    # ── Camera feed ───────────────────────────────────────────────────────────

    async def get_video_stream_url(self, node: Node) -> str | None:
        host = node.config.get("host", "localhost")
        port = node.config.get("camera_port", 8080)
        topic = node.config.get("camera_topic", "/front_camera/image_raw")
        return f"http://{host}:{port}/stream?topic={topic}"
