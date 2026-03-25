import asyncio
import logging
from typing import Any, Callable
from .base import BaseTransport

logger = logging.getLogger(__name__)


class SimulationTransport(BaseTransport):
    """
    Transport for simulated nodes.
    No real network connection — everything is local.
    Used by the sim-dummy plugin and for testing.
    """

    SCHEME = "sim"

    def __init__(self):
        self._connected = False
        self._message_callbacks: list[Callable] = []
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self, host: str = "", port: int = 0, **kwargs) -> bool:
        """Simulation always connects successfully."""
        self._connected = True
        logger.debug("Simulation transport connected")
        return True

    async def disconnect(self) -> None:
        """Simulation disconnect — just mark as disconnected."""
        self._connected = False
        logger.debug("Simulation transport disconnected")

    async def send(self, data: dict[str, Any]) -> bool:
        """
        Simulation send — puts message in local queue.
        The sim plugin reads from this queue.
        """
        if not self._connected:
            return False
        await self._message_queue.put(data)
        return True

    async def is_connected(self) -> bool:
        return self._connected

    async def on_message(self, callback: Callable) -> None:
        self._message_callbacks.append(callback)

    async def receive(self) -> dict[str, Any] | None:
        """Get next message from queue (non-blocking)."""
        try:
            return self._message_queue.get_nowait()
        except asyncio.QueueEmpty:
            return None