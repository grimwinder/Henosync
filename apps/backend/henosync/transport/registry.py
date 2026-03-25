import logging
from .base import BaseTransport
from .simulation import SimulationTransport
from .ros2 import ROS2Transport

logger = logging.getLogger(__name__)


class TransportRegistry:
    """
    Registry of available transport adapters.
    Maps transport scheme names to transport classes.
    """

    def __init__(self):
        self._transports: dict[str, type[BaseTransport]] = {}
        self._register_builtin_transports()

    def _register_builtin_transports(self) -> None:
        """Register the transports that ship with Henosync core."""
        self.register("sim", SimulationTransport)
        self.register("ros2", ROS2Transport)
        logger.info("Built-in transports registered: sim, ros2")

    def register(
        self,
        scheme: str,
        transport_class: type[BaseTransport]
    ) -> None:
        """Register a transport class for a scheme."""
        self._transports[scheme] = transport_class
        logger.debug(f"Registered transport: {scheme}")

    def get(self, scheme: str) -> type[BaseTransport] | None:
        """Get a transport class by scheme name."""
        return self._transports.get(scheme)

    def create(self, scheme: str) -> BaseTransport | None:
        """
        Create a new instance of a transport by scheme.

        Args:
            scheme: Transport scheme (e.g. "ros2", "sim", "ws")

        Returns:
            New transport instance, or None if scheme unknown.
        """
        transport_class = self._transports.get(scheme)
        if not transport_class:
            logger.error(f"Unknown transport scheme: {scheme}")
            return None
        return transport_class()

    def list_transports(self) -> list[str]:
        """List all registered transport scheme names."""
        return list(self._transports.keys())


# Global singleton
transport_registry = TransportRegistry()