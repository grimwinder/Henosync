from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Optional

from .models import (
    CommandEnvelope,
    CommandResult,
    CommandType,
    Node,
    NodePluginContext,
    TelemetryFrame,
)


class NodePlugin(ABC):
    """
    Base class for all Henosync device plugins.

    To create a plugin for a new robot or device:
    1. pip install -e packages/plugin-sdk
    2. Inherit from NodePlugin
    3. Implement the 4 abstract methods (connect, disconnect, telemetry_stream, get_safe_state)
    4. Override cmd_move_to / cmd_stop / cmd_return_home for the capabilities you declare
    5. Create a manifest.json
    6. Drop the folder into Henosync's plugins/ directory

    Standard command flow:
        DeviceProxy.move_to() → send_command(envelope) → cmd_move_to()
        DeviceProxy.stop()    → send_command(envelope) → cmd_stop()
        Custom commands       → send_command(envelope) → handle_custom_command()

    Override the cmd_* methods rather than send_command for standard capabilities.
    Override handle_custom_command() for device-specific extras.
    """

    PLUGIN_ID: str = ""
    PLUGIN_NAME: str = ""
    PLUGIN_VERSION: str = "0.1.0"
    PLUGIN_AUTHOR: str = ""
    PLUGIN_DESCRIPTION: str = ""

    # Declare your telemetry rate. Use in your sleep:
    #   await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)
    TELEMETRY_RATE_HZ: float = 1.0

    def __init__(self):
        # Set by node_registry before connect() is called.
        # Available from connect() onward — use self._context.emit_event() etc.
        self._context: Optional[NodePluginContext] = None

    # ── Abstract Methods (must implement all 4) ───────────────────────────────

    @abstractmethod
    async def connect(
        self, node: Node, config: dict[str, Any], context: NodePluginContext
    ) -> tuple[bool, str]:
        """
        Establish a connection to the physical device.

        Store context for use in send_command and telemetry_stream:
            self._context = context

        Set node.specs here so capability matching works:
            node.specs = DeviceSpecs(category=..., capabilities=[...])

        Returns (True, "") on success.
        Returns (False, "reason") on failure — never raise here.
        """

    @abstractmethod
    async def disconnect(self, node: Node) -> None:
        """
        Gracefully disconnect. Clean up all sockets, tasks, subscriptions.
        Must never raise exceptions.
        """

    @abstractmethod
    async def telemetry_stream(
        self, node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        """
        Async generator that yields TelemetryFrame at TELEMETRY_RATE_HZ.

        Use typed fields on TelemetryFrame — not custom{}:
            yield TelemetryFrame(
                node_id=node.id,
                position=Position(lat=..., lon=..., alt=...),
                battery=BatteryData(percentage=80.0),
                speed=2.5,
                status_text="Online",
            )
        """

    @abstractmethod
    async def get_safe_state(self, node: Node) -> CommandResult:
        """
        Put the device into its safest possible state immediately.
        Called on heartbeat loss, low battery, or emergency stop.
        Must be fast and reliable. Do NOT kill the telemetry stream here.
        """

    # ── Standard Command Dispatch ─────────────────────────────────────────────

    async def send_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        """
        Routes standard commands to typed cmd_* methods.
        Custom commands fall through to handle_custom_command().

        Override cmd_move_to / cmd_stop / cmd_return_home / cmd_take_photo
        instead of overriding this method directly.
        """
        if envelope.command_type == CommandType.MOVE_TO:
            p = envelope.params
            return await self.cmd_move_to(
                node,
                lat=p.get("lat", 0.0),
                lon=p.get("lon", 0.0),
                alt=p.get("alt", 0.0),
                x=p.get("x"),
                y=p.get("y"),
                z=p.get("z"),
                arrival_radius_m=p.get("arrival_radius_m"),
            )
        if envelope.command_type == CommandType.STOP:
            return await self.cmd_stop(node)
        if envelope.command_type == CommandType.RETURN_HOME:
            return await self.cmd_return_home(node)
        if envelope.command_type == CommandType.TAKE_PHOTO:
            return await self.cmd_take_photo(node)
        return await self.handle_custom_command(node, envelope)

    # ── Standard Command Handlers (override per declared capability) ──────────

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
    ) -> CommandResult:
        """
        Override if you declare MOVE_2D or MOVE_3D capability.

        For coordinate_frame="gps" devices, lat/lon/alt are the target (WGS84).
        For coordinate_frame="local" devices, DeviceProxy converts the WGS84
        target to local metres before dispatch — x/y/z are populated instead
        and lat/lon/alt are left at their defaults. Check node.specs.coordinate_frame
        (or simply whether x is not None) to know which set to use.
        """
        return CommandResult(success=False, message="move_to not implemented")

    async def cmd_stop(self, node: Node) -> CommandResult:
        """Override if you declare MOVE_2D or MOVE_3D capability."""
        return CommandResult(success=False, message="stop not implemented")

    async def cmd_return_home(self, node: Node) -> CommandResult:
        """Override to support return-home failsafe action."""
        return CommandResult(success=False, message="return_home not implemented")

    async def cmd_take_photo(self, node: Node) -> CommandResult:
        """Override if you declare CAMERA capability."""
        return CommandResult(success=False, message="take_photo not implemented")

    async def handle_custom_command(
        self, node: Node, envelope: CommandEnvelope
    ) -> CommandResult:
        """
        Override to handle device-specific commands not in CommandType.
        Called for any command_type not matched by the standard dispatch above.
        """
        return CommandResult(
            success=False, message=f"Unknown command: {envelope.command_type}"
        )

    # ── Optional Hooks ────────────────────────────────────────────────────────

    async def on_reconnect(
        self, node: Node, config: dict[str, Any], context: NodePluginContext
    ) -> tuple[bool, str]:
        """
        Called instead of connect() on manual reconnect or dropout recovery.
        Override for a faster reconnect path. Default: full connect() call.
        """
        return await self.connect(node, config, context)

    async def get_video_stream_url(self, node: Node) -> str | None:
        """Return MJPEG/RTSP stream URL, or None if no camera."""
        return None

    async def validate_config(self, config: dict[str, Any]) -> tuple[bool, str]:
        """
        Validate config before connection attempt.
        Return (True, "") if valid, (False, "reason") if not.
        """
        return True, ""

    async def on_mission_start(self, node: Node) -> None:
        """Called when a mission begins involving this node."""

    async def on_mission_end(self, node: Node) -> None:
        """Called when a mission ends involving this node."""

    async def is_connected(self, node: Node) -> bool:
        """
        Optional: return False if you know the underlying connection is dead.

        node_registry polls this every 2 seconds. If False, the telemetry
        stream is cancelled and the node is set to DEGRADED.

        Default returns True — the global heartbeat timeout handles detection.
        Override for faster detection when your transport can report its own
        state (e.g. ros.is_connected for rosbridge, serial port open, etc.).

        For silent TCP drop detection, also track the last time a real message
        arrived from the device and return False if that exceeds a threshold.
        """
        return True
