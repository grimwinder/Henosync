"""
UE Sim plugin — Unreal Engine AirSim (SUV1) via rosbridge.

Milestone 1 ✓: Connect to rosbridge, heartbeat telemetry, device goes Online.
Milestone 2 (this): Subscribe to global_gps + car_state topics.
  → Success: position marker appears on map, lat/lon/alt/speed in telemetry panel.

Milestone 3 (next): Subscribe remaining topics (IMU heading, cameras).
  → Run `ros2 topic echo /airsim_node/SUV1/car_state` to confirm field names if needed.
"""

import asyncio
import logging
import sys
import os
from datetime import datetime, timezone
from typing import AsyncGenerator, Any, Optional

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from henosync.plugin_system.interfaces import NodePlugin
from henosync.models import (
    Node, TelemetryFrame, CommandResult,
    DeviceSpecs, DeviceCategory, DeviceCapability, CapabilitySpec,
)

try:
    import roslibpy
    ROSLIBPY_AVAILABLE = True
except ImportError:
    ROSLIBPY_AVAILABLE = False
    logger.warning("roslibpy not installed — run: pip install roslibpy")

# ── Topic names — update if your AirSim namespace differs from SUV1 ──────────
GPS_TOPIC   = "/airsim_node/SUV1/global_gps"  # sensor_msgs/NavSatFix
STATE_TOPIC = "/airsim_node/SUV1/car_state"   # airsim_ros_pkgs/CarState


class _NodeState:
    def __init__(self):
        self.connected: bool = False
        self.ros: Optional[Any] = None  # roslibpy.Ros instance

        # ── MILESTONE 2: live topic data ──────────────────────────────────
        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.speed: float = 0.0
        self.gps_received: bool = False  # True once first GPS message arrives

        # Keep topic objects so we can unsubscribe on disconnect
        self._topics: list[Any] = []


class UESimPlugin(NodePlugin):
    """
    Device plugin for Unreal Engine AirSim SUV via rosbridge (roslibpy).
    Vehicle is a ground vehicle — treated as AGV category.
    """

    PLUGIN_ID = "ue-sim"
    PLUGIN_NAME = "UE Sim (ROS2)"
    PLUGIN_VERSION = "0.2.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Plugin for Unreal Engine AirSim SUV via rosbridge"

    def __init__(self):
        self._nodes: dict[str, _NodeState] = {}

    # ── Connect ───────────────────────────────────────────────────────────────

    async def connect(self, node: Node, config: dict[str, Any]) -> tuple[bool, str]:
        if not ROSLIBPY_AVAILABLE:
            return False, "roslibpy not installed — run: pip install roslibpy"

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
                logger.error("UE Sim [%s]: rosbridge error: %s", node.name, e)
                failed_event.set()

            ros.on_ready(_on_ready)
            ros.on("close", lambda: self._on_close(node.id))
            ros.on("error", _on_error)

            asyncio.get_running_loop().run_in_executor(None, ros.run)

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
                logger.error("UE Sim [%s]: %s", node.name, reason)
                ros.terminate()
                self._nodes.pop(node.id, None)
                return False, reason

            state.ros = ros
            state.connected = True
            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.GPS),
                    CapabilitySpec(capability=DeviceCapability.CAMERA),
                ],
            )
            logger.info("UE Sim [%s]: connected to %s:%d", node.name, host, port)

            self._subscribe_topics(node, state)

            return True, ""

        except Exception as e:
            logger.error("UE Sim [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False, str(e)

    def _on_close(self, node_id: str) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.connected = False
            logger.warning("UE Sim [%s]: rosbridge connection closed", node_id)

    # ── Milestone 2: topic subscriptions ─────────────────────────────────────

    def _subscribe_topics(self, node: Node, state: _NodeState) -> None:
        gps_topic = roslibpy.Topic(state.ros, GPS_TOPIC, "sensor_msgs/NavSatFix")
        gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))
        state._topics.append(gps_topic)

        # If car_state fields differ, check with: ros2 topic echo /airsim_node/SUV1/car_state
        car_topic = roslibpy.Topic(state.ros, STATE_TOPIC, "airsim_ros_pkgs/CarState")
        car_topic.subscribe(lambda msg: self._on_car_state(node.id, msg))
        state._topics.append(car_topic)

        logger.info("UE Sim [%s]: subscribed to %s, %s", node.name, GPS_TOPIC, STATE_TOPIC)

    def _on_gps(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.lat = msg.get("latitude", 0.0)
            state.lon = msg.get("longitude", 0.0)
            state.alt = msg.get("altitude", 0.0)
            state.gps_received = True

    def _on_car_state(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.speed = msg.get("speed", 0.0)

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
                state.ros.terminate()
            except Exception:
                pass
        logger.info("UE Sim [%s]: disconnected", node.name)

    # ── Telemetry stream ──────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        seq = 0
        while node.id in self._nodes and self._nodes[node.id].connected:
            state = self._nodes[node.id]

            values: dict[str, Any] = {
                "speed": state.speed,
            }

            if state.gps_received:
                # Only emit lat/lon once real GPS data has arrived.
                # Without this guard the device would appear at (0, 0) on the map.
                values["lat"] = state.lat
                values["lon"] = state.lon
                values["alt"] = state.alt
                values["status_text"] = (
                    f"GPS {state.lat:.5f}, {state.lon:.5f}  "
                    f"alt {state.alt:.1f} m  "
                    f"speed {state.speed:.1f} m/s"
                )
            else:
                values["status_text"] = "Connected — waiting for GPS"

            yield TelemetryFrame(
                node_id=node.id,
                timestamp=datetime.now(timezone.utc),
                sequence_number=seq,
                values=values,
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── Camera feed ───────────────────────────────────────────────────────────

    async def get_video_stream_url(self, node: Node) -> str | None:
        host = node.config.get("host", "localhost")
        return f"http://{host}:8080/stream?topic=/airsim_node/SUV1/StereoCamera0_Scene/image"

    # ── Commands ──────────────────────────────────────────────────────────────

    async def send_command(
        self, node: Node, capability: str, params: dict[str, Any]
    ) -> CommandResult:
        return CommandResult(success=False, message=f"Commands not implemented yet: {capability}")

    async def get_safe_state(self, node: Node) -> CommandResult:
        return CommandResult(success=True, message="UE Sim — no safe state required")
