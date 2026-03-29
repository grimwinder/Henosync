import asyncio
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class EventBus:
    """
    Inter-plugin messaging system.

    Allows control plugins to communicate with each other.
    Messages are delivered asynchronously.

    Use cases:
    - Person search plugin alerts perimeter plugin of detected person
    - Coverage plugin tells search plugin which areas are done
    - Any plugin can broadcast status to all others
    """

    def __init__(self):
        # plugin_id -> async callback
        self._subscribers: dict[str, Callable] = {}

    def register_plugin(
        self,
        plugin_id: str,
        callback: Callable
    ) -> None:
        """Register a control plugin to receive messages."""
        self._subscribers[plugin_id] = callback
        logger.debug(f"EventBus: registered plugin {plugin_id}")

    def unregister_plugin(self, plugin_id: str) -> None:
        """Unregister a control plugin."""
        self._subscribers.pop(plugin_id, None)

    async def broadcast(
        self,
        sender_id: str,
        message: dict[str, Any]
    ) -> None:
        """Broadcast a message to all plugins except sender."""
        for plugin_id, callback in self._subscribers.items():
            if plugin_id != sender_id:
                try:
                    await callback(sender_id, message)
                except Exception as e:
                    logger.error(
                        f"EventBus delivery error to "
                        f"{plugin_id}: {e}"
                    )

    async def send(
        self,
        sender_id: str,
        target_id: str,
        message: dict[str, Any]
    ) -> bool:
        """Send a message to a specific plugin."""
        callback = self._subscribers.get(target_id)
        if not callback:
            logger.warning(
                f"EventBus: target plugin not found: {target_id}"
            )
            return False
        try:
            await callback(sender_id, message)
            return True
        except Exception as e:
            logger.error(
                f"EventBus delivery error to {target_id}: {e}"
            )
            return False


# Global singleton
event_bus = EventBus()