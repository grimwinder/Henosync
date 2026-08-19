"""
Henosync Plugin SDK — MAVLink protocol starter
===============================================
Subclass MAVLinkPlugin instead of NodePlugin when your device uses MAVLink
(PX4, ArduPilot, Pixhawk). The boilerplate — UDP connection, heartbeat wait,
background message loop, disconnect — is handled for you.

Minimum implementation:

    from henosync_sdk.protocols.mavlink import MAVLinkPlugin, MAVLinkNodeState
    from henosync_sdk import DeviceSpecs, TelemetryFrame, CommandResult, ...

    class _State(MAVLinkNodeState):       # add your device's data fields
        lat: float = 0.0
        lon: float = 0.0
        battery: float = 100.0

    class MyDronePlugin(MAVLinkPlugin):
        PLUGIN_ID   = "my-drone"
        PLUGIN_NAME = "My Drone"
        PLUGIN_VERSION = "0.1.0"
        PLUGIN_AUTHOR  = "..."

        def create_state(self):
            return _State()

        async def setup_node(self, node, state, config):
            node.specs = DeviceSpecs(category=DeviceCategory.DRONE, capabilities=[...])

            # Register handlers for incoming MAVLink messages
            self.register_handler(state, "GLOBAL_POSITION_INT", self._on_position)
            self.register_handler(state, "BATTERY_STATUS",      self._on_battery)

            # Request messages at desired rate (interval in microseconds)
            self.request_message_interval(state, 33, 100_000)   # GLOBAL_POSITION_INT @ 10 Hz
            self.request_message_interval(state, 147, 1_000_000) # BATTERY_STATUS @ 1 Hz

        def _on_position(self, state, msg):
            state.lat = msg.lat / 1e7
            state.lon = msg.lon / 1e7

        def _on_battery(self, state, msg):
            state.battery = msg.battery_remaining  # 0-100

        def build_telemetry(self, node, state, seq):
            return TelemetryFrame(
                node_id=node.id, sequence_number=seq,
                position=Position(lat=state.lat, lon=state.lon, alt=0.0),
                battery=BatteryData(percentage=state.battery),
            )

        async def get_safe_state(self, node):
            state = self._nodes.get(node.id)
            if state:
                self.send_command_long(state, 21)  # MAV_CMD_NAV_LAND
            return CommandResult(success=True, message="Landing")

Optional overrides:
  - create_state()          return your _NodeState subclass (default: MAVLinkNodeState)
  - on_telemetry_tick()     async hook before each yield; use for emit_event calls
  - is_connected()          default checks heartbeat timeout (HEARTBEAT_TIMEOUT seconds)
  - Any NodePlugin cmd_* or handle_custom_command methods

MAVLink command helpers (call from command handlers):
  - send_command_long(state, command, p1..p7)
  - send_set_position_target(state, lat, lon, alt_m)
  - send_vision_position(state, x, y, z, roll, pitch, yaw) — VICON/external position
  - request_message_interval(state, message_id, interval_us)
"""

import asyncio
import logging
import time
from abc import abstractmethod
from typing import Any, AsyncGenerator, Callable, Optional

logger = logging.getLogger(__name__)

try:
    import pymavlink.mavutil as mavutil
    _PYMAVLINK_AVAILABLE = True
except ImportError:
    _PYMAVLINK_AVAILABLE = False

from henosync_sdk.interfaces import NodePlugin


# ── State base class ───────────────────────────────────────────────────────────

class MAVLinkNodeState:
    """
    Base state object for one connected MAVLink device.
    Subclass to add device-specific data fields.
    """
    def __init__(self):
        self.connected: bool = False
        self.mav: Optional[Any] = None           # mavutil.mavlink_connection instance
        self.last_heartbeat: float = 0.0          # monotonic time of last heartbeat
        self._handlers: dict[str, list[Callable]] = {}
        self._recv_task: Optional[asyncio.Task] = None


# ── Plugin base class ──────────────────────────────────────────────────────────

class MAVLinkPlugin(NodePlugin):
    """
    Base class for MAVLink device plugins (PX4, ArduPilot, Pixhawk).
    See module docstring for usage.
    """

    HEARTBEAT_TIMEOUT: float = 5.0  # seconds without heartbeat before DEGRADED

    def __init__(self):
        super().__init__()
        self._nodes: dict[str, MAVLinkNodeState] = {}

    # ── Must implement ─────────────────────────────────────────────────────────

    def create_state(self) -> MAVLinkNodeState:
        """Return a new state object. Override to return your _NodeState subclass."""
        return MAVLinkNodeState()

    @abstractmethod
    async def setup_node(
        self, node: Any, state: MAVLinkNodeState, config: dict
    ) -> None:
        """
        Called immediately after the first MAVLink heartbeat is received.
        Set node.specs and call register_handler() for each message type you need.
        Raise an exception to abort the connection with a reason message.
        """
        ...

    @abstractmethod
    def build_telemetry(self, node: Any, state: MAVLinkNodeState, seq: int) -> Any:
        """
        Return a TelemetryFrame built from current state.
        Called synchronously at TELEMETRY_RATE_HZ — no awaits allowed here.
        Use on_telemetry_tick() for async side effects.
        """
        ...

    # ── Optional hooks ─────────────────────────────────────────────────────────

    async def on_telemetry_tick(self, node: Any, state: MAVLinkNodeState) -> None:
        """
        Async hook called before each telemetry yield.
        Override to emit events, check timeouts, etc.
        """

    # ── Protocol helpers ───────────────────────────────────────────────────────

    def register_handler(
        self,
        state: MAVLinkNodeState,
        msg_type: str,
        callback: Callable[[MAVLinkNodeState, Any], None],
    ) -> None:
        """
        Register a handler for a MAVLink message type.
        Callback signature: callback(state, msg) — called from the recv loop.

        Example:
            self.register_handler(state, "GLOBAL_POSITION_INT", self._on_position)

            def _on_position(self, state, msg):
                state.lat = msg.lat / 1e7
        """
        state._handlers.setdefault(msg_type, []).append(callback)

    def send_command_long(
        self,
        state: MAVLinkNodeState,
        command: int,
        p1: float = 0, p2: float = 0, p3: float = 0, p4: float = 0,
        p5: float = 0, p6: float = 0, p7: float = 0,
    ) -> None:
        """
        Send a MAV_CMD via COMMAND_LONG. Common commands:
          21  MAV_CMD_NAV_LAND
          22  MAV_CMD_NAV_TAKEOFF          p7 = altitude (m)
          400 MAV_CMD_COMPONENT_ARM_DISARM p1=1 arm, p1=0 disarm
        """
        if not state.mav:
            return
        state.mav.mav.command_long_send(
            state.mav.target_system,
            state.mav.target_component,
            command,
            0,  # confirmation
            p1, p2, p3, p4, p5, p6, p7,
        )

    def send_set_position_target(
        self,
        state: MAVLinkNodeState,
        lat: float,
        lon: float,
        alt_m: float,
    ) -> None:
        """
        Command the vehicle to fly to a GPS position (offboard / guided mode).
        lat/lon in decimal degrees, alt_m relative to home (metres).
        """
        if not state.mav:
            return
        state.mav.mav.set_position_target_global_int_send(
            0,  # time_boot_ms
            state.mav.target_system,
            state.mav.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            0b0000_1111_1111_1000,  # type_mask: position only
            int(lat * 1e7),
            int(lon * 1e7),
            alt_m,
            0, 0, 0,   # velocity
            0, 0, 0,   # acceleration
            0, 0,      # yaw, yaw_rate
        )

    def send_vision_position(
        self,
        state: MAVLinkNodeState,
        x_m: float, y_m: float, z_m: float,
        roll: float = 0.0, pitch: float = 0.0, yaw: float = 0.0,
    ) -> None:
        """
        Inject an external position estimate (e.g. VICON) into the vehicle's EKF.
        Position in metres relative to local origin; angles in radians.
        Call at ≥10 Hz for stable EKF fusion.
        """
        if not state.mav:
            return
        now_us = int(time.time() * 1e6)
        state.mav.mav.vision_position_estimate_send(
            now_us, x_m, y_m, z_m, roll, pitch, yaw,
        )

    def request_message_interval(
        self,
        state: MAVLinkNodeState,
        message_id: int,
        interval_us: int,
    ) -> None:
        """
        Ask the vehicle to send a specific message at the given interval.
        interval_us: microseconds between messages (e.g. 100_000 = 10 Hz).
        Uses MAV_CMD_SET_MESSAGE_INTERVAL (supported by PX4 and ArduPilot).
        """
        self.send_command_long(state, 511, message_id, interval_us)

    # ── NodePlugin implementation ──────────────────────────────────────────────

    async def connect(
        self, node: Any, config: dict, context: Any
    ) -> tuple[bool, str]:
        if not _PYMAVLINK_AVAILABLE:
            return False, "pymavlink not installed — run: pip install pymavlink"

        self._context = context
        host = config.get("host", "localhost")
        port = int(config.get("port", 14550))

        state = self.create_state()
        self._nodes[node.id] = state

        try:
            connection_string = f"udp:{host}:{port}"
            loop = asyncio.get_running_loop()

            mav = await loop.run_in_executor(
                None, lambda: mavutil.mavlink_connection(connection_string)
            )

            heartbeat = await asyncio.wait_for(
                loop.run_in_executor(None, mav.wait_heartbeat),
                timeout=10.0,
            )

            state.mav = mav
            state.connected = True
            state.last_heartbeat = time.monotonic()

            await self.setup_node(node, state, config)

            state._recv_task = asyncio.ensure_future(
                self._recv_loop(node.id, state)
            )

            logger.info(
                "%s [%s]: connected to %s (sysid=%d)",
                self.PLUGIN_NAME, node.name, connection_string,
                mav.target_system,
            )
            return True, ""

        except asyncio.TimeoutError:
            self._nodes.pop(node.id, None)
            return False, f"No heartbeat from {host}:{port} within 10 s"
        except Exception as e:
            logger.error(
                "%s [%s]: connect failed: %s", self.PLUGIN_NAME, node.name, e
            )
            self._nodes.pop(node.id, None)
            return False, str(e)

    async def _recv_loop(
        self, node_id: str, state: MAVLinkNodeState
    ) -> None:
        """Background task: continuously receive and dispatch MAVLink messages."""
        loop = asyncio.get_running_loop()
        while node_id in self._nodes and state.connected:
            try:
                msg = await loop.run_in_executor(
                    None,
                    lambda: state.mav.recv_match(blocking=True, timeout=1.0),
                )
                if msg is None:
                    continue
                msg_type = msg.get_type()
                if msg_type == "HEARTBEAT":
                    state.last_heartbeat = time.monotonic()
                for handler in state._handlers.get(msg_type, []):
                    handler(state, msg)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(
                    "%s: recv loop error: %s", self.PLUGIN_NAME, e
                )

    async def disconnect(self, node: Any) -> None:
        state = self._nodes.pop(node.id, None)
        if not state:
            return
        state.connected = False
        if state._recv_task:
            state._recv_task.cancel()
            try:
                await state._recv_task
            except asyncio.CancelledError:
                pass
        if state.mav:
            try:
                state.mav.close()
            except Exception:
                pass
        logger.info("%s [%s]: disconnected", self.PLUGIN_NAME, node.name)

    async def is_connected(self, node: Any) -> bool:
        state = self._nodes.get(node.id)
        if not state or not state.connected:
            return False
        return (time.monotonic() - state.last_heartbeat) < self.HEARTBEAT_TIMEOUT

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
