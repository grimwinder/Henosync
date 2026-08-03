"""
UE Sim plugin — Unreal Engine AirSim (SUV1) via rosbridge.

Milestone 1 ✓: Connect to rosbridge, heartbeat telemetry, device goes Online.
Milestone 2 ✓: Subscribe to global_gps + car_state — position on map, speed in panel.
Milestone 2b ✓: Camera feed via web_video_server.
Milestone 3 (next): IMU heading.
"""

import asyncio
import logging
import time
from typing import Any, AsyncGenerator, Optional

logger = logging.getLogger(__name__)

from henosync_sdk import (
    BatteryData,
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    EventSeverity,
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

from henosync_sdk.rosbridge import ensure_reactor

# ── Topic names ──────────
GPS_TOPIC = "/airsim_node/SUV1/global_gps"   # sensor_msgs/NavSatFix
STATE_TOPIC = "/airsim_node/SUV1/car_state"  # airsim_ros_pkgs/CarState
CAR_CMD_TOPIC = "/airsim_node/SUV1/car_cmd"  # airsim_ros_pkgs/CarControls

class _NodeState:
    def __init__(self):
        self.connected: bool = False
        self.ros: Optional[Any] = None  # roslibpy.Ros instance
        self.car_cmd_topic: Optional[Any] = None  # roslibpy.Topic publisher

        self.lat: float = 0.0
        self.lon: float = 0.0
        self.alt: float = 0.0
        self.speed: float = 0.0
        self.gps_received: bool = False

        # Monotonic timestamp of the last received ROS topic message.
        # Used to detect silent TCP drops where ros.is_connected stays True
        # but no data is flowing.
        self.last_message_time: float = 0.0

        # Timing for no-fix warning
        self.connect_time: float = time.monotonic()
        self._no_fix_warned: bool = False

        # One-shot debug flags — each flips to True after the first log.
        self._gps_logged: bool = False
        self._car_state_logged: bool = False

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

    TELEMETRY_RATE_HZ: float = 2.0

    # Set True during testing to log the first raw message from each topic.
    # Confirms field names and data before relying on them. Set False when done.
    DEBUG_TOPICS: bool = False

    # If no ROS topic message arrives within this window, is_connected() returns
    # False even if the WebSocket appears alive (silent TCP half-open detection).
    # Increase if your topics publish slower than 1 Hz.
    MESSAGE_TIMEOUT: float = 10.0

    # Warn if no GPS fix arrives within this many seconds of connecting.
    # Catches: GPS topic not publishing, wrong topic name.
    POSITION_FIX_TIMEOUT: float = 10.0

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
                logger.error("UE Sim [%s]: rosbridge error: %s", node.name, e)
                failed_event.set()

            ros.on_ready(_on_ready)
            ros.on("close", lambda: self._on_close(node.id))
            ros.on("error", _on_error)

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
                logger.error("UE Sim [%s]: %s", node.name, reason)
                try:
                    ros.close()
                except Exception:
                    pass
                self._nodes.pop(node.id, None)
                return False, reason

            state.ros = ros
            state.connected = True
            node.specs = DeviceSpecs(
                category=DeviceCategory.AGV,
                capabilities=[
                    CapabilitySpec(capability=DeviceCapability.GPS),
                    CapabilitySpec(capability=DeviceCapability.CAMERA),
                    CapabilitySpec(capability=DeviceCapability.MOVE_2D),
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

    # ── Topic subscriptions ───────────────────────────────────────────────────

    def _subscribe_topics(self, node: Node, state: _NodeState) -> None:
        gps_topic = roslibpy.Topic(state.ros, GPS_TOPIC, "sensor_msgs/NavSatFix")
        gps_topic.subscribe(lambda msg: self._on_gps(node.id, msg))
        state._topics.append(gps_topic)

        car_topic = roslibpy.Topic(state.ros, STATE_TOPIC, "airsim_ros_pkgs/CarState")
        car_topic.subscribe(lambda msg: self._on_car_state(node.id, msg))
        state._topics.append(car_topic)

        state.car_cmd_topic = roslibpy.Topic(
            state.ros, CAR_CMD_TOPIC, "airsim_ros_pkgs/CarControls"
        )

        logger.info("UE Sim [%s]: subscribed to %s, %s", node.name, GPS_TOPIC, STATE_TOPIC)

    def _on_gps(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            if self.DEBUG_TOPICS and not state._gps_logged:
                logger.info("UE Sim [%s]: first GPS message: %s", node_id, msg)
                state._gps_logged = True
            state.lat = msg.get("latitude", 0.0)
            state.lon = msg.get("longitude", 0.0)
            state.alt = msg.get("altitude", 0.0)
            state.gps_received = True
            state.last_message_time = time.monotonic()

    def _on_car_state(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            if self.DEBUG_TOPICS and not state._car_state_logged:
                logger.info("UE Sim [%s]: first CarState message: %s", node_id, msg)
                state._car_state_logged = True
            state.speed = msg.get("speed", 0.0)
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
        logger.info("UE Sim [%s]: disconnected", node.name)

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
        # If we have received GPS before but nothing has arrived for
        # MESSAGE_TIMEOUT seconds, treat the connection as dead.
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
            now = time.monotonic()

            if (
                not state.gps_received
                and not state._no_fix_warned
                and now - state.connect_time > self.POSITION_FIX_TIMEOUT
            ):
                state._no_fix_warned = True
                logger.warning("UE Sim [%s]: no GPS received after %.0fs", node.name, self.POSITION_FIX_TIMEOUT)
                if self._context:
                    await self._context.emit_event(
                        "No GPS data",
                        f"Connected but no GPS received after {self.POSITION_FIX_TIMEOUT:.0f}s. "
                        f"Check that {GPS_TOPIC} is publishing.",
                        EventSeverity.WARNING,
                    )

            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                speed=state.speed,
                position=Position(
                    lat=state.lat, lon=state.lon, alt=state.alt
                ) if state.gps_received else None,
                status_text=(
                    f"GPS {state.lat:.5f}, {state.lon:.5f}  "
                    f"alt {state.alt:.1f} m  "
                    f"speed {state.speed:.1f} m/s"
                ) if state.gps_received else "Connected — waiting for GPS",
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── Camera feed ───────────────────────────────────────────────────────────

    async def get_video_stream_url(self, node: Node) -> str | None:
        host = node.config.get("host", "localhost")
        return (
            f"http://{host}:8080/stream"
            f"?topic=/airsim_node/SUV1/StereoCamera0_Scene/image"
        )

    # ── Custom commands ────────────────────────────────────────────────────────

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        """
        cmd_vel — drive the car with continuous throttle/steering.
        params: linear (-1..1, forward/back), angular (-1..1, left/right).
        Used by teleop-style control plugins (e.g. arrow-key driving).
        """
        if envelope.command_type != "cmd_vel":
            return CommandResult(
                success=False, message=f"Unknown command: {envelope.command_type}"
            )

        state = self._nodes.get(node.id)
        if not state or not state.car_cmd_topic:
            return CommandResult(success=False, message="Not connected")

        linear = max(-1.0, min(1.0, envelope.params.get("linear", 0.0)))
        angular = max(-1.0, min(1.0, envelope.params.get("angular", 0.0)))

        msg = {
            "throttle": abs(linear),
            "steering": angular,
            "brake": 1.0 if linear == 0.0 and angular == 0.0 else 0.0,
            "handbrake": False,
            "is_manual_gear": linear < 0.0,
            "manual_gear": -1 if linear < 0.0 else 0,
            "gear_immediate": True,
        }
        state.car_cmd_topic.publish(roslibpy.Message(msg))
        return CommandResult(success=True, message="cmd_vel sent")

    # ── Safe state ────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state and state.car_cmd_topic:
            state.car_cmd_topic.publish(
                roslibpy.Message(
                    {
                        "throttle": 0.0,
                        "steering": 0.0,
                        "brake": 1.0,
                        "handbrake": True,
                        "is_manual_gear": False,
                        "manual_gear": 0,
                        "gear_immediate": True,
                    }
                )
            )
        return CommandResult(success=True, message="UE Sim — brake applied")
