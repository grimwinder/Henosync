"""
Henosync Plugin — Clearpath Jackal UGV
=======================================
Connects to a Jackal UGV running ROS2 and Nav2 via rosbridge.

Requirements on the Jackal:
    ros2 launch rosbridge_server rosbridge_websocket_launch.xml
    ros2 launch nav2_bringup navigation_launch.py

Supports multiple Jackals simultaneously via namespace configuration.
"""

import asyncio
import sys
import os
import math
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

sys.path.insert(
    0,
    os.path.join(os.path.dirname(__file__), '../../apps/backend')
)

from henosync.plugin_system.interfaces import NodePlugin
from henosync.models import Node, TelemetryFrame, CommandResult
from henosync.transport.registry import transport_registry
from henosync.transport.ros2 import ROS2Transport

logger = logging.getLogger(__name__)


class JackalUGVPlugin(NodePlugin):
    """
    Plugin for Clearpath Jackal UGV.

    Uses Nav2's /navigate_to_pose action server for waypoint
    navigation — the most robust navigation method available,
    providing full path planning and obstacle avoidance.

    Supports multiple simultaneous Jackals via ROS2 namespacing.
    """

    PLUGIN_ID = "jackal-ugv"
    PLUGIN_NAME = "Clearpath Jackal UGV"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Clearpath Jackal UGV via ROS2 Nav2"

    @staticmethod
    def get_device_specs(config: dict):
        """Return device specs for this Jackal configuration."""
        from henosync.models import (
            DeviceSpecs, DeviceCategory, DeviceCapability,
            CapabilitySpec
        )
        use_gps = config.get("use_gps", False)

        capabilities = [
            CapabilitySpec(
                capability=DeviceCapability.MOVE_2D,
                max_range=None,
                notes="Differential drive ground robot"
            ),
            CapabilitySpec(capability=DeviceCapability.BATTERY),
            CapabilitySpec(capability=DeviceCapability.IMU),
            CapabilitySpec(
                capability=DeviceCapability.LIDAR,
                max_range=30.0,
                dimensions=2,
                notes="2D planar lidar"
            ),
            CapabilitySpec(
                capability=DeviceCapability.CAMERA,
                notes="Optional — depends on hardware config"
            ),
        ]

        if use_gps:
            capabilities.append(
                CapabilitySpec(capability=DeviceCapability.GPS)
            )

        return DeviceSpecs(
            category=DeviceCategory.AGV,
            capabilities=capabilities,
            weight_kg=17.0,
            max_speed_ms=2.0,
            has_gps=use_gps,
            uses_odometry=True,
            coordinate_frame="gps" if use_gps else "local"
        )

    def __init__(self):
        # node_id -> running flag
        self._running: dict[str, bool] = {}
        # node_id -> ROS2Transport instance
        self._transports: dict[str, ROS2Transport] = {}
        # node_id -> latest telemetry values
        self._telemetry: dict[str, dict] = {}
        # node_id -> namespace string
        self._namespaces: dict[str, str] = {}
        # node_id -> home position
        self._home: dict[str, dict] = {}
        # node_id -> use_gps flag
        self._use_gps: dict[str, bool] = {}

    # ── Connection ────────────────────────────────────────────────

    async def connect(self, node: Node, config: dict[str, Any]) -> bool:
        """Connect to Jackal via rosbridge WebSocket."""
        host = config.get("host", "localhost")
        port = int(config.get("port", 9090))
        namespace = config.get("namespace", "").rstrip("/")
        use_gps = config.get("use_gps", False)

        self._namespaces[node.id] = namespace
        self._use_gps[node.id] = use_gps
        self._home[node.id] = {
            "lat": config.get("home_lat", 0.0),
            "lon": config.get("home_lon", 0.0)
        }

        # Initialise telemetry defaults
        self._telemetry[node.id] = {
            "battery_percent": None,
            "lat": 0.0,
            "lon": 0.0,
            "alt": 0.0,
            "heading": 0.0,
            "speed": 0.0,
            "nav_status": "Idle",
            "status_text": "Connecting...",
            "use_gps": use_gps
        }

        # Create and connect transport
        transport = transport_registry.create("ros2")
        if not transport:
            logger.error("ROS2 transport unavailable — install roslibpy")
            return False

        success = await transport.connect(host, port)
        if not success:
            logger.error(
                f"Failed to connect to Jackal at {host}:{port}"
            )
            return False

        self._transports[node.id] = transport
        self._running[node.id] = True

        # Subscribe to all topics
        self._subscribe_topics(node.id, transport, namespace, use_gps)

        self._telemetry[node.id]["status_text"] = "Online"

        node.specs = self.get_device_specs(config)

        logger.info(
            f"Jackal connected: {node.name} at {host}:{port} "
            f"namespace='{namespace}' gps={use_gps}"
        )
        return True

    def _subscribe_topics(
        self,
        node_id: str,
        transport: ROS2Transport,
        namespace: str,
        use_gps: bool
    ) -> None:
        """Subscribe to all relevant Jackal ROS2 topics."""

        def ns(topic: str) -> str:
            """Prepend namespace to topic if set."""
            return f"{namespace}{topic}" if namespace else topic

        # Battery state
        transport.subscribe_topic(
            ns("/jackal_velocity_controller/battery_state"),
            "sensor_msgs/BatteryState",
            lambda msg: self._on_battery(node_id, msg)
        )

        # Odometry — always available, used for speed and
        # position when GPS is not available
        transport.subscribe_topic(
            ns("/odometry/filtered"),
            "nav_msgs/Odometry",
            lambda msg: self._on_odometry(node_id, msg)
        )

        # IMU — heading/orientation
        transport.subscribe_topic(
            ns("/imu/data"),
            "sensor_msgs/Imu",
            lambda msg: self._on_imu(node_id, msg)
        )

        # Nav2 feedback topic — navigation status
        transport.subscribe_topic(
            ns("/navigate_to_pose/_action/feedback"),
            "nav2_msgs/NavigateToPose_FeedbackMessage",
            lambda msg: self._on_nav_feedback(node_id, msg)
        )

        # GPS — only subscribe if available on this robot
        if use_gps:
            transport.subscribe_topic(
                ns("/navsat/fix"),
                "sensor_msgs/NavSatFix",
                lambda msg: self._on_gps(node_id, msg)
            )

    async def disconnect(self, node: Node) -> None:
        """Disconnect from Jackal cleanly."""
        self._running[node.id] = False

        transport = self._transports.pop(node.id, None)
        if transport:
            await transport.disconnect()

        self._telemetry.pop(node.id, None)
        self._namespaces.pop(node.id, None)
        logger.info(f"Jackal disconnected: {node.name}")

    # ── Commands ──────────────────────────────────────────────────

    async def send_command(
        self,
        node: Node,
        capability: str,
        params: dict[str, Any]
    ) -> CommandResult:
        """Dispatch a capability command to the Jackal."""
        transport = self._transports.get(node.id)
        if not transport:
            return CommandResult(
                success=False,
                message="Not connected to Jackal"
            )

        namespace = self._namespaces.get(node.id, "")

        def ns(topic: str) -> str:
            return f"{namespace}{topic}" if namespace else topic

        if capability == "stop":
            return await self._stop(node, transport, ns)

        elif capability == "move_to":
            return await self._move_to(node, transport, ns, params)

        elif capability == "return_home":
            return await self._return_home(node, transport, ns)

        elif capability == "cancel_navigation":
            return await self._cancel_navigation(node, transport, ns)

        return CommandResult(
            success=False,
            message=f"Unknown capability: {capability}"
        )

    async def _stop(self, node, transport, ns) -> CommandResult:
        """Stop all movement by publishing zero velocity."""
        success = transport.publish_to_topic(
            ns("/cmd_vel"),
            "geometry_msgs/Twist",
            {
                "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
            }
        )

        # Also cancel any active Nav2 goal
        await self._cancel_navigation(node, transport, ns)

        self._telemetry[node.id]["nav_status"] = "Stopped"
        self._telemetry[node.id]["status_text"] = "Stopped"

        return CommandResult(
            success=success,
            message="Jackal stopped"
        )

    async def _move_to(
        self,
        node,
        transport,
        ns,
        params: dict
    ) -> CommandResult:
        """
        Navigate to a GPS waypoint using Nav2 navigate_to_pose.

        Nav2 handles all path planning and obstacle avoidance.
        The goal is sent as a PoseStamped in the map frame.

        Note: Requires Nav2 to be running and a valid map/odometry
        source to be available on the Jackal.
        """
        lat = params.get("lat", 0.0)
        lon = params.get("lon", 0.0)
        alt = params.get("alt", 0.0)

        # Convert GPS to map frame x/y if GPS is available
        # Otherwise use lat/lon directly as x/y (for indoor use
        # where coordinates are in metres from origin)
        use_gps = self._use_gps.get(node.id, False)
        if use_gps:
            x, y = self._gps_to_metres(node.id, lat, lon)
        else:
            # Treat lat/lon as x/y in metres from origin
            x, y = lat, lon

        # Send goal to Nav2 navigate_to_pose action server
        # via the action goal topic
        goal_msg = {
            "goal": {
                "pose": {
                    "header": {
                        "frame_id": "map",
                        "stamp": {"sec": 0, "nanosec": 0}
                    },
                    "pose": {
                        "position": {
                            "x": float(x),
                            "y": float(y),
                            "z": float(alt)
                        },
                        "orientation": {
                            "x": 0.0,
                            "y": 0.0,
                            "z": 0.0,
                            "w": 1.0
                        }
                    }
                },
                "behavior_tree": ""
            }
        }

        success = transport.publish_to_topic(
            ns("/navigate_to_pose/_action/send_goal"),
            "nav2_msgs/NavigateToPose_SendGoal_Request",
            goal_msg
        )

        if success:
            self._telemetry[node.id]["nav_status"] = "Navigating"
            self._telemetry[node.id]["status_text"] = (
                f"Moving to ({x:.2f}, {y:.2f})"
            )

        return CommandResult(
            success=success,
            message=f"Navigation goal sent to ({x:.2f}, {y:.2f})"
        )

    async def _return_home(self, node, transport, ns) -> CommandResult:
        """Navigate back to the configured home position."""
        home = self._home.get(node.id, {"lat": 0.0, "lon": 0.0})
        return await self._move_to(
            node, transport, ns,
            {"lat": home["lat"], "lon": home["lon"], "alt": 0.0}
        )

    async def _cancel_navigation(
        self,
        node,
        transport,
        ns
    ) -> CommandResult:
        """Cancel any active Nav2 navigation goal."""
        success = transport.publish_to_topic(
            ns("/navigate_to_pose/_action/cancel_goal"),
            "action_msgs/CancelGoal_Request",
            {"goal_info": {"goal_id": {"uuid": [0] * 16}}}
        )

        self._telemetry[node.id]["nav_status"] = "Idle"
        self._telemetry[node.id]["status_text"] = "Navigation cancelled"

        return CommandResult(
            success=success,
            message="Navigation cancelled"
        )

    # ── Telemetry Stream ──────────────────────────────────────────

    async def telemetry_stream(
        self,
        node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        """
        Yield telemetry frames at 1Hz.
        Values are updated by ROS2 topic callbacks as data arrives.
        """
        seq = 0
        while self._running.get(node.id, False):
            values = dict(self._telemetry.get(node.id, {}))
            yield TelemetryFrame(
                node_id=node.id,
                timestamp=datetime.now(timezone.utc),
                sequence_number=seq,
                values=values
            )
            seq += 1
            await asyncio.sleep(1.0)

    # ── Safe State ────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        """
        Stop all movement immediately.
        Called by failsafe manager on connection loss or emergency stop.
        Simple and reliable — just zero velocity.
        """
        transport = self._transports.get(node.id)
        namespace = self._namespaces.get(node.id, "")

        def ns(topic: str) -> str:
            return f"{namespace}{topic}" if namespace else topic

        if transport:
            # Publish zero velocity
            transport.publish_to_topic(
                ns("/cmd_vel"),
                "geometry_msgs/Twist",
                {
                    "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
                    "angular": {"x": 0.0, "y": 0.0, "z": 0.0}
                }
            )

        self._running[node.id] = False
        logger.warning(f"Safe state engaged for Jackal: {node.name}")

        return CommandResult(
            success=True,
            message="Jackal stopped — safe state engaged"
        )

    # ── Topic Callbacks ───────────────────────────────────────────

    def _on_battery(self, node_id: str, msg: dict) -> None:
        """Handle battery state message."""
        try:
            percentage = msg.get("percentage", None)
            if percentage is not None:
                # ROS2 BatteryState percentage is 0.0-1.0
                self._telemetry[node_id]["battery_percent"] = round(
                    float(percentage) * 100, 1
                )
        except Exception as e:
            logger.debug(f"Battery callback error: {e}")

    def _on_odometry(self, node_id: str, msg: dict) -> None:
        """Handle odometry message — position and speed."""
        try:
            twist = msg.get("twist", {}).get("twist", {})
            linear = twist.get("linear", {})
            speed = math.sqrt(
                linear.get("x", 0) ** 2 +
                linear.get("y", 0) ** 2
            )
            self._telemetry[node_id]["speed"] = round(speed, 3)

            # Use odometry for position if GPS not available
            if not self._use_gps.get(node_id, False):
                pose = msg.get("pose", {}).get("pose", {})
                position = pose.get("position", {})
                self._telemetry[node_id]["lat"] = round(
                    position.get("x", 0.0), 4
                )
                self._telemetry[node_id]["lon"] = round(
                    position.get("y", 0.0), 4
                )
        except Exception as e:
            logger.debug(f"Odometry callback error: {e}")

    def _on_imu(self, node_id: str, msg: dict) -> None:
        """Handle IMU message — heading from quaternion."""
        try:
            orientation = msg.get("orientation", {})
            x = orientation.get("x", 0)
            y = orientation.get("y", 0)
            z = orientation.get("z", 0)
            w = orientation.get("w", 1)

            # Convert quaternion to yaw (heading)
            siny_cosp = 2 * (w * z + x * y)
            cosy_cosp = 1 - 2 * (y * y + z * z)
            yaw = math.atan2(siny_cosp, cosy_cosp)
            heading = math.degrees(yaw) % 360

            self._telemetry[node_id]["heading"] = round(heading, 1)
        except Exception as e:
            logger.debug(f"IMU callback error: {e}")

    def _on_gps(self, node_id: str, msg: dict) -> None:
        """Handle GPS NavSatFix message."""
        try:
            status = msg.get("status", {}).get("status", -1)
            # status >= 0 means fix acquired
            if status >= 0:
                self._telemetry[node_id]["lat"] = round(
                    msg.get("latitude", 0.0), 6
                )
                self._telemetry[node_id]["lon"] = round(
                    msg.get("longitude", 0.0), 6
                )
                self._telemetry[node_id]["alt"] = round(
                    msg.get("altitude", 0.0), 2
                )
                self._telemetry[node_id]["gps_fix"] = True
            else:
                self._telemetry[node_id]["gps_fix"] = False
        except Exception as e:
            logger.debug(f"GPS callback error: {e}")

    def _on_nav_feedback(self, node_id: str, msg: dict) -> None:
        """Handle Nav2 navigation feedback."""
        try:
            feedback = msg.get("feedback", {})
            distance = feedback.get(
                "distance_remaining", None
            )
            if distance is not None:
                self._telemetry[node_id]["distance_remaining"] = round(
                    float(distance), 2
                )
                self._telemetry[node_id]["status_text"] = (
                    f"Navigating — {distance:.1f}m remaining"
                )
        except Exception as e:
            logger.debug(f"Nav feedback callback error: {e}")

    # ── Helpers ───────────────────────────────────────────────────

    def _gps_to_metres(
        self,
        node_id: str,
        lat: float,
        lon: float
    ) -> tuple[float, float]:
        """
        Convert GPS coordinates to approximate metres offset
        from the home position.

        Uses equirectangular approximation — accurate enough
        for short distances (< 1km) typical in robot operations.
        """
        home = self._home.get(node_id, {"lat": 0.0, "lon": 0.0})
        home_lat = home.get("lat", 0.0)
        home_lon = home.get("lon", 0.0)

        R = 6371000  # Earth radius in metres
        dlat = math.radians(lat - home_lat)
        dlon = math.radians(lon - home_lon)
        lat_rad = math.radians(home_lat)

        x = dlon * R * math.cos(lat_rad)
        y = dlat * R

        return round(x, 3), round(y, 3)

    async def get_video_stream_url(self, node: Node) -> str | None:
        """
        Return camera stream URL if camera is available.
        Requires a web_video_server node running on the Jackal.
        Post-MVP: make camera topic configurable.
        """
        config = node.config
        host = config.get("host", "localhost")
        # web_video_server default port
        return f"http://{host}:8080/stream?topic=/camera/image_raw"