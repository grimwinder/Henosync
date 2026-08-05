"""
Henosync Plugin SDK — ROS2/rosbridge protocol starter
======================================================
Subclass ROS2Plugin instead of NodePlugin when your device connects via
rosbridge (roslibpy). The boilerplate — reactor lifecycle, connect/disconnect
with timeout, topic cleanup, thread-safe publish — is handled for you.

Minimum implementation:

    from henosync_sdk.protocols.ros2 import ROS2Plugin, ROS2NodeState
    from henosync_sdk import DeviceSpecs, TelemetryFrame, CommandResult, ...

    class _State(ROS2NodeState):          # add your device's data fields
        speed: float = 0.0
        battery: float = 100.0

    class MyRobotPlugin(ROS2Plugin):
        PLUGIN_ID   = "my-robot"
        PLUGIN_NAME = "My Robot"
        PLUGIN_VERSION = "0.1.0"
        PLUGIN_AUTHOR  = "..."

        def create_state(self):
            return _State()

        async def setup_node(self, node, state, config):
            node.specs = DeviceSpecs(category=..., capabilities=[...])
            self.subscribe(state, "/odom", "nav_msgs/Odometry",
                           lambda msg: self._on_odom(node.id, msg))
            state.cmd_pub = self.advertise(state, "/cmd_vel", "geometry_msgs/Twist")

        def build_telemetry(self, node, state, seq):
            return TelemetryFrame(node_id=node.id, sequence_number=seq,
                                  speed=state.speed)

        async def get_safe_state(self, node):
            state = self._nodes.get(node.id)
            if state:
                self.publish(state.cmd_pub, {
                    "linear":  {"x": 0.0, "y": 0.0, "z": 0.0},
                    "angular": {"x": 0.0, "y": 0.0, "z": 0.0},
                })
            return CommandResult(success=True, message="Stopped")

Optional overrides:
  - create_state()           return your _NodeState subclass (default: ROS2NodeState)
  - on_telemetry_tick()      async hook before each yield; use for emit_event calls
  - is_connected()           extend with message-timeout detection
  - Any NodePlugin cmd_* or handle_custom_command methods
"""

import asyncio
import logging
import threading
from abc import abstractmethod
from typing import Any, AsyncGenerator, Optional

logger = logging.getLogger(__name__)

try:
    import roslibpy
    _ROSLIBPY_AVAILABLE = True
except ImportError:
    _ROSLIBPY_AVAILABLE = False

from henosync_sdk.interfaces import NodePlugin


# ── Reactor lifecycle ──────────────────────────────────────────────────────────

_reactor_started = threading.Event()
_reactor_ready = threading.Event()


def ensure_reactor() -> threading.Event:
    """
    Start the Twisted reactor once on a background thread.
    Returns a threading.Event — wait on it before calling callFromThread.
    Safe to call from multiple plugins; only one reactor thread ever starts.
    """
    if not _reactor_started.is_set():
        _reactor_started.set()

        def _run() -> None:
            from twisted.internet import reactor
            reactor.callWhenRunning(_reactor_ready.set)
            reactor.run(installSignalHandlers=False)

        threading.Thread(target=_run, name="twisted-reactor", daemon=True).start()

    return _reactor_ready


# ── State base class ───────────────────────────────────────────────────────────

class ROS2NodeState:
    """
    Base state object for one connected node.
    Subclass to add device-specific data fields.
    """
    def __init__(self):
        self.connected: bool = False
        self.ros: Optional[Any] = None
        self._subscriptions: list = []
        self._publishers: list = []


# ── Plugin base class ──────────────────────────────────────────────────────────

class ROS2Plugin(NodePlugin):
    """
    Base class for ROS2 device plugins connecting via rosbridge (roslibpy).
    See module docstring for usage.
    """

    def __init__(self):
        super().__init__()
        self._nodes: dict[str, ROS2NodeState] = {}

    # ── Must implement ─────────────────────────────────────────────────────────

    def create_state(self) -> ROS2NodeState:
        """Return a new state object. Override to return your _NodeState subclass."""
        return ROS2NodeState()

    @abstractmethod
    async def setup_node(
        self, node: Any, state: ROS2NodeState, config: dict
    ) -> None:
        """
        Called immediately after rosbridge connects.
        Set node.specs, subscribe to topics, and create publishers here.
        Raise an exception to abort the connection with a reason message.
        """
        ...

    @abstractmethod
    def build_telemetry(self, node: Any, state: ROS2NodeState, seq: int) -> Any:
        """
        Return a TelemetryFrame built from current state.
        Called synchronously at TELEMETRY_RATE_HZ — no awaits allowed here.
        Use on_telemetry_tick() for async side effects.
        """
        ...

    # ── Optional hooks ─────────────────────────────────────────────────────────

    async def on_telemetry_tick(self, node: Any, state: ROS2NodeState) -> None:
        """
        Async hook called before each telemetry yield.
        Override to emit events, check timeouts, etc.
        """

    # ── Protocol helpers ───────────────────────────────────────────────────────

    def subscribe(
        self,
        state: ROS2NodeState,
        topic: str,
        msg_type: str,
        callback,
    ) -> None:
        """Subscribe to a ROS2 topic. Callback receives the message dict."""
        t = roslibpy.Topic(state.ros, topic, msg_type)
        t.subscribe(callback)
        state._subscriptions.append(t)

    def advertise(
        self,
        state: ROS2NodeState,
        topic: str,
        msg_type: str,
    ) -> Any:
        """
        Advertise a publisher on a ROS2 topic.
        Returns the Topic object — store it on state and pass to publish().
        """
        pub = roslibpy.Topic(state.ros, topic, msg_type)
        pub.advertise()
        state._publishers.append(pub)
        return pub

    def publish(self, pub: Any, message: dict) -> None:
        """
        Publish a message to a ROS2 topic.
        Thread-safe — call from asyncio coroutines, Twisted callbacks, or any thread.
        """
        from twisted.internet import reactor as _reactor
        msg = roslibpy.Message(message)

        def _do() -> None:
            try:
                pub.publish(msg)
            except Exception as e:
                logger.warning("ROS2Plugin: publish failed: %s", e)

        _reactor.callFromThread(_do)

    # ── NodePlugin implementation ──────────────────────────────────────────────

    async def connect(
        self, node: Any, config: dict, context: Any
    ) -> tuple[bool, str]:
        if not _ROSLIBPY_AVAILABLE:
            return False, "roslibpy not installed — run: pip install roslibpy"

        self._context = context
        host = config.get("host", "localhost")
        port = int(config.get("port", 9090))

        state = self.create_state()
        self._nodes[node.id] = state

        try:
            ros = roslibpy.Ros(host=host, port=port)
            connected_event = asyncio.Event()
            failed_event = asyncio.Event()

            ros.on_ready(lambda: connected_event.set())
            ros.on("close", lambda: self._on_close(node.id))
            ros.on(
                "error",
                lambda e: (
                    logger.error(
                        "%s [%s]: rosbridge error: %s", self.PLUGIN_NAME, node.name, e
                    ),
                    failed_event.set(),
                ),
            )

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
                    asyncio.ensure_future(connected_event.wait()),
                    asyncio.ensure_future(failed_event.wait()),
                ],
                timeout=10.0,
                return_when=asyncio.FIRST_COMPLETED,
            )

            if not connected_event.is_set():
                try:
                    ros.close()
                except Exception:
                    pass
                self._nodes.pop(node.id, None)
                return False, f"Timed out connecting to {host}:{port}"

            state.ros = ros
            state.connected = True

            await self.setup_node(node, state, config)

            logger.info(
                "%s [%s]: connected to %s:%d", self.PLUGIN_NAME, node.name, host, port
            )
            return True, ""

        except Exception as e:
            logger.error(
                "%s [%s]: connect failed: %s", self.PLUGIN_NAME, node.name, e
            )
            self._nodes.pop(node.id, None)
            return False, str(e)

    def _on_close(self, node_id: str) -> None:
        state = self._nodes.get(node_id)
        if state:
            state.connected = False

    async def disconnect(self, node: Any) -> None:
        state = self._nodes.pop(node.id, None)
        if not state:
            return
        state.connected = False
        for sub in state._subscriptions:
            try:
                sub.unsubscribe()
            except Exception:
                pass
        for pub in state._publishers:
            try:
                pub.unadvertise()
            except Exception:
                pass
        if state.ros:
            try:
                state.ros.close()
            except Exception:
                pass
        logger.info("%s [%s]: disconnected", self.PLUGIN_NAME, node.name)

    async def is_connected(self, node: Any) -> bool:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return False
        return state.ros is not None and state.ros.is_connected

    async def telemetry_stream(
        self, node: Any
    ) -> AsyncGenerator[Any, None]:
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
            await self.on_telemetry_tick(node, state)
            yield self.build_telemetry(node, state, seq)
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)
