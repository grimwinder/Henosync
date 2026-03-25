from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any
from ..models import Node, TelemetryFrame, CommandResult


class NodePlugin(ABC):
    """
    Base class for all Henosync node plugins.

    To create a plugin for a new robot or device:
    1. Install henosync-plugin-sdk
    2. Create a class that inherits from NodePlugin
    3. Implement all 5 abstract methods below
    4. Create a manifest.json describing your plugin
    5. Drop the folder into Henosync's plugins directory

    The core application ONLY communicates with hardware
    through these 5 methods. Nothing else.
    """

    # ── Plugin Metadata ───────────────────────────────────────────
    # Override these in your plugin class

    PLUGIN_ID: str = ""
    PLUGIN_NAME: str = ""
    PLUGIN_VERSION: str = "0.1.0"
    PLUGIN_AUTHOR: str = ""
    PLUGIN_DESCRIPTION: str = ""

    # ── Required Methods ──────────────────────────────────────────

    @abstractmethod
    async def connect(self, node: Node, config: dict[str, Any]) -> bool:
        """
        Establish a connection to the physical node.

        Called when:
        - User adds a new node
        - Henosync attempts to reconnect after a dropout

        Args:
            node:   The node object representing this device
            config: Connection config from the plugin manifest
                    schema (e.g. IP address, port, ROS topics)

        Returns:
            True if connection succeeded, False otherwise.
            Do NOT raise exceptions here — return False instead.

        Example config for a ROS2 robot:
            {
                "host": "192.168.1.100",
                "port": 9090,
                "namespace": "/jackal"
            }
        """

    @abstractmethod
    async def disconnect(self, node: Node) -> None:
        """
        Gracefully disconnect from the node.

        Called when:
        - User manually removes a node
        - Application is shutting down
        - Reconnection is about to be attempted

        Clean up all resources here — close sockets,
        cancel async tasks, unsubscribe from topics.
        This method should never raise exceptions.
        """

    @abstractmethod
    async def send_command(
        self,
        node: Node,
        capability: str,
        params: dict[str, Any]
    ) -> CommandResult:
        """
        Execute a named capability on the node.

        Called when:
        - User clicks an action button in the GUI
        - Mission engine executes an ACTION step
        - Failsafe manager triggers a safe state command

        Args:
            node:       The target node
            capability: The capability id from your manifest
                        (e.g. "move_to", "take_photo")
            params:     Parameters for the capability
                        (e.g. {"lat": 1.0, "lon": 2.0, "alt": 5.0})

        Returns:
            CommandResult with success status and optional message.

        Important: This method should block until the command
        is ACCEPTED by the robot, not until it is completed.
        For long-running commands (e.g. navigate to waypoint),
        return success=True immediately after the robot confirms
        it received the command. Use telemetry to track progress.
        """

    @abstractmethod
    async def telemetry_stream(
        self,
        node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        """
        Continuously yield telemetry frames while connected.

        Called when:
        - Node successfully connects
        - Runs as a background task until disconnected

        This is an async generator — use 'yield' to emit frames.
        Yield at whatever rate makes sense for your hardware.
        1Hz is sufficient for most mission planning purposes.

        The values dict can contain anything your robot reports.
        Standard keys the GUI will automatically display:
            battery_percent  (float 0-100)
            signal_strength  (float 0-100)
            lat              (float)
            lon              (float)
            alt              (float, metres)
            speed            (float, m/s)
            heading          (float, degrees)
            status_text      (str)

        Any additional keys will appear in the telemetry panel.

        Example:
            while self._connected[node.id]:
                yield TelemetryFrame(
                    node_id=node.id,
                    values={
                        "battery_percent": 85.0,
                        "lat": -37.8136,
                        "lon": 144.9631,
                        "alt": 0.0,
                        "status_text": "Idle"
                    }
                )
                await asyncio.sleep(1.0)
        """

    @abstractmethod
    async def get_safe_state(self, node: Node) -> CommandResult:
        """
        Put the node into the safest possible state immediately.

        Called by the failsafe manager when:
        - Node connection is lost mid-mission
        - Critical battery level is reached
        - Operator triggers emergency stop

        This should be the single safest thing your robot can do:
        - Ground robot: stop all motors
        - Drone: hover in place or land
        - Arm: move to safe position

        This method must be fast and reliable above all else.
        Keep it simple — do not attempt complex recovery here.
        """

    # ── Optional Methods ──────────────────────────────────────────
    # Override these in your plugin for additional functionality.
    # Default implementations are provided so they don't need to
    # be implemented if not needed.

    async def get_video_stream_url(self, node: Node) -> str | None:
        """
        Return a video stream URL for this node if available.

        Returns an RTSP or MJPEG URL string, or None if this
        node has no camera capability.

        Example:
            return f"http://192.168.1.100:8080/stream"
        """
        return None

    async def validate_config(
        self,
        config: dict[str, Any]
    ) -> tuple[bool, str]:
        """
        Validate a config dict before attempting connection.

        Called when the user fills in the Add Node wizard.
        Return (True, "") if valid.
        Return (False, "error message") if invalid.

        Default implementation accepts any config.
        """
        return True, ""

    async def on_mission_start(self, node: Node) -> None:
        """
        Called when a mission begins that involves this node.
        Optional setup before mission execution starts.
        """

    async def on_mission_end(self, node: Node) -> None:
        """
        Called when a mission ends (complete, aborted, or failed)
        that involved this node. Optional cleanup.
        """