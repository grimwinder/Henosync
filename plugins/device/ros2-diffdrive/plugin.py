"""
ROS2 Diff-Drive — generic ground robot via rosbridge (roslibpy).

For any real ROS2 robot running rosbridge_server. Topic names are per-device
config (set in the Add Device form), not hardcoded — every robot names its
topics differently. Find yours with `ros2 topic list` / `ros2 topic info -t
<topic>` on the robot before adding it here.

Milestone 1: connect, drive via cmd_vel (arrow-key teleop), speed telemetry.
No GPS/map position yet — add it once you know whether your robot publishes
GPS (most indoor diff-drive robots only have odometry, not GPS).
"""

import asyncio
import logging
import threading
from typing import Any, AsyncGenerator, Optional

from henosync_sdk import (
    CapabilitySpec,
    CommandEnvelope,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    Node,
    NodePlugin,
    NodePluginContext,
    TelemetryFrame,
)

try:
    import roslibpy
    ROSLIBPY_AVAILABLE = True
except ImportError:
    ROSLIBPY_AVAILABLE = False

logger = logging.getLogger(__name__)

if not ROSLIBPY_AVAILABLE:
    logger.warning("roslibpy not installed — run: pip install roslibpy")

# Twisted's reactor is a process-wide singleton — once started it cannot be
# restarted. Start it once on a dedicated thread; a failed connect attempt
# never kills the reactor. Mirrors plugins/device/ue-sim/plugin.py.
_reactor_started = threading.Event()
_reactor_ready = threading.Event()


def _ensure_reactor() -> None:
    if _reactor_started.is_set():
        return
    _reactor_started.set()

    def _run() -> None:
        from twisted.internet import reactor
        reactor.callWhenRunning(_reactor_ready.set)
        reactor.run(installSignalHandlers=False)

    threading.Thread(target=_run, name="twisted-reactor", daemon=True).start()


class _NodeState:
    def __init__(self):
        self.connected: bool = False
        self.ros: Optional[Any] = None  # roslibpy.Ros instance
        self.cmd_vel_topic: Optional[Any] = None  # roslibpy.Topic publisher

        self.speed: float = 0.0
        self.odom_received: bool = False

        self._topics: list[Any] = []


class ROS2DiffDrivePlugin(NodePlugin):
    """
    Device plugin for a generic ROS2 differential-drive robot via rosbridge.
    Topic names come from per-device config — nothing robot-specific is
    hardcoded, unlike plugins/device/ue-sim which targets one known sim vehicle.
    """

    PLUGIN_ID = "ros2-diffdrive"
    PLUGIN_NAME = "ROS2 Diff-Drive Robot"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Generic ROS2 differential-drive ground robot via rosbridge"

    TELEMETRY_RATE_HZ: float = 2.0

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
                logger.error("ROS2 DiffDrive [%s]: rosbridge error: %s", node.name, e)
                failed_event.set()

            ros.on_ready(_on_ready)
            ros.on("close", lambda: self._on_close(node.id))
            ros.on("error", _on_error)

            _ensure_reactor()
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: _reactor_ready.wait(5.0)
            )
            if not _reactor_ready.is_set():
                self._nodes.pop(node.id, None)
                return False, "Twisted reactor failed to start"

            from twisted.internet import reactor as _reactor
            _reactor.callFromThread(ros.connect)

            await asyncio.wait(
                [
                    asyncio.ensure_future(connected_event.wait()),
                    asyncio.ensure_future(failed_event.wait()),
                ],
                timeout=10.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not connected_event.is_set():
                reason = f"timed out connecting to {host}:{port}"
                logger.error("ROS2 DiffDrive [%s]: %s", node.name, reason)
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
                capabilities=[CapabilitySpec(capability=DeviceCapability.MOVE_2D)],
            )
            logger.info("ROS2 DiffDrive [%s]: connected to %s:%d", node.name, host, port)

            self._subscribe_topics(node, state, config)
            return True, ""

        except Exception as e:
            logger.error("ROS2 DiffDrive [%s]: connect failed: %s", node.name, e)
            self._nodes.pop(node.id, None)
            return False, str(e)

    def _on_close(self, node_id: str) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.connected = False
            logger.warning("ROS2 DiffDrive [%s]: rosbridge connection closed", node_id)

    # ── Topics ────────────────────────────────────────────────────────────────

    def _subscribe_topics(self, node: Node, state: _NodeState, config: dict[str, Any]) -> None:
        cmd_vel_topic = config.get("cmd_vel_topic", "/cmd_vel")
        state.cmd_vel_topic = roslibpy.Topic(state.ros, cmd_vel_topic, "geometry_msgs/Twist")

        odom_topic = config.get("odom_topic", "/odom")
        if odom_topic:
            topic = roslibpy.Topic(state.ros, odom_topic, "nav_msgs/Odometry")
            topic.subscribe(lambda msg: self._on_odom(node.id, msg))
            state._topics.append(topic)

        logger.info(
            "ROS2 DiffDrive [%s]: cmd_vel=%s odom=%s",
            node.name, cmd_vel_topic, odom_topic or "(disabled)"
        )

    def _on_odom(self, node_id: str, msg: dict) -> None:
        state = self._nodes.get(node_id)
        if state:
            linear = msg.get("twist", {}).get("twist", {}).get("linear", {})
            state.speed = (linear.get("x", 0.0) ** 2 + linear.get("y", 0.0) ** 2) ** 0.5
            state.odom_received = True

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
                state.ros.close()
            except Exception:
                pass
        logger.info("ROS2 DiffDrive [%s]: disconnected", node.name)

    # ── Liveness check ──────────────────────────────────────────────────────

    async def is_connected(self, node: Node) -> bool:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return False
        if state.ros is None or not state.ros.is_connected:
            return False
        return True

    # ── Telemetry stream ──────────────────────────────────────────────────────

    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                speed=state.speed,
                status_text=(
                    f"speed {state.speed:.2f} m/s"
                    if state.odom_received else "Connected — no odometry data yet"
                ),
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── Custom commands ────────────────────────────────────────────────────────

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        """
        cmd_vel — drive with linear/angular velocity, scaled by this device's
        configured max speeds. params: linear (-1..1), angular (-1..1).
        Used by teleop-style control plugins (e.g. arrow-key driving).
        """
        if envelope.command_type != "cmd_vel":
            return CommandResult(
                success=False, message=f"Unknown command: {envelope.command_type}"
            )

        state = self._nodes.get(node.id)
        if not state or not state.cmd_vel_topic:
            return CommandResult(success=False, message="Not connected")

        max_linear = float(node.config.get("max_linear_speed", 0.5))
        max_angular = float(node.config.get("max_angular_speed", 1.0))

        linear = max(-1.0, min(1.0, envelope.params.get("linear", 0.0))) * max_linear
        angular = max(-1.0, min(1.0, envelope.params.get("angular", 0.0))) * max_angular

        state.cmd_vel_topic.publish(roslibpy.Message({
            "linear": {"x": linear, "y": 0.0, "z": 0.0},
            "angular": {"x": 0.0, "y": 0.0, "z": angular},
        }))
        return CommandResult(success=True, message="cmd_vel sent")

    # ── Safe state ────────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        state = self._nodes.get(node.id)
        if state and state.cmd_vel_topic:
            state.cmd_vel_topic.publish(roslibpy.Message({
                "linear": {"x": 0.0, "y": 0.0, "z": 0.0},
                "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
            }))
        return CommandResult(success=True, message="ROS2 DiffDrive — zero velocity sent")
