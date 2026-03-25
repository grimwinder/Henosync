from abc import ABC, abstractmethod
from typing import Any, Callable
import logging

logger = logging.getLogger(__name__)


class BaseTransport(ABC):
    """
    Base class for all transport adapters.

    A transport handles the raw connection to a device.
    A plugin uses a transport to send/receive data.

    Transports are registered by scheme:
        "ros2://"   -> ROS2Transport
        "ws://"     -> WebSocketTransport
        "sim://"    -> SimulationTransport

    Plugin developers don't usually need to create new
    transports — they just use an existing one in their
    plugin by specifying the transport scheme in their
    manifest.json.
    """

    # Override in subclass — e.g. "ros2", "ws", "sim"
    SCHEME: str = ""

    @abstractmethod
    async def connect(self, host: str, port: int, **kwargs) -> bool:
        """
        Open a connection to the target device.

        Args:
            host:   IP address or hostname
            port:   Port number
            kwargs: Transport-specific options

        Returns:
            True if connected, False otherwise.
        """

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the connection and clean up resources."""

    @abstractmethod
    async def send(self, data: dict[str, Any]) -> bool:
        """
        Send data to the device.

        Args:
            data: Dict of data to send

        Returns:
            True if sent successfully.
        """

    @abstractmethod
    async def is_connected(self) -> bool:
        """Return True if currently connected."""

    # ── Optional ──────────────────────────────────────────────────

    async def on_message(
        self,
        callback: Callable[[dict], None]
    ) -> None:
        """
        Register a callback for incoming messages.
        Not all transports support this — default is no-op.
        """

    async def ping(self) -> bool:
        """
        Check if the connection is still alive.
        Default implementation just checks is_connected().
        """
        return await self.is_connected()