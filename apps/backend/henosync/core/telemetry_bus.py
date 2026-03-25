import asyncio
import logging
from datetime import datetime, timezone
from typing import Callable
from ..models import TelemetryFrame, SystemEvent, EventSeverity
import uuid

logger = logging.getLogger(__name__)


class TelemetryBus:
    """
    Central pub/sub bus for all real-time data in Henosync.

    Publishers:  Node plugins (via node registry)
    Subscribers: WebSocket server (forwards to GUI)

    Each node has its own async queue. The WebSocket server
    subscribes to all queues and forwards frames to the GUI.
    """

    def __init__(self):
        # node_id -> asyncio.Queue of TelemetryFrames
        self._telemetry_queues: dict[str, asyncio.Queue] = {}
        # Queue for system events (node status changes, alerts)
        self._event_queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        # Callbacks subscribed to telemetry updates
        self._telemetry_subscribers: list[Callable] = []
        # Callbacks subscribed to system events
        self._event_subscribers: list[Callable] = []

    # ── Telemetry ─────────────────────────────────────────────────

    def create_node_queue(self, node_id: str) -> None:
        """Create a telemetry queue for a node."""
        if node_id not in self._telemetry_queues:
            # Max 50 frames buffered per node
            # Old frames dropped if GUI can't keep up
            self._telemetry_queues[node_id] = asyncio.Queue(maxsize=50)
            logger.debug(f"Created telemetry queue for node: {node_id}")

    def remove_node_queue(self, node_id: str) -> None:
        """Remove a node's telemetry queue."""
        self._telemetry_queues.pop(node_id, None)
        logger.debug(f"Removed telemetry queue for node: {node_id}")

    async def publish_telemetry(self, frame: TelemetryFrame) -> None:
        """
        Publish a telemetry frame from a node.
        Called by the node registry when new telemetry arrives.
        """
        queue = self._telemetry_queues.get(frame.node_id)
        if queue:
            try:
                # Non-blocking put — drop frame if queue is full
                # This prevents slow GUI from blocking fast robots
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                # Drop oldest frame and add new one
                try:
                    queue.get_nowait()
                    queue.put_nowait(frame)
                except asyncio.QueueEmpty:
                    pass

        # Notify all telemetry subscribers directly
        for callback in self._telemetry_subscribers:
            try:
                await callback(frame)
            except Exception as e:
                logger.error(f"Telemetry subscriber error: {e}")

    async def get_telemetry_frame(
        self,
        node_id: str,
        timeout: float = 1.0
    ) -> TelemetryFrame | None:
        """
        Get the next telemetry frame for a node.
        Returns None if no frame arrives within timeout.
        """
        queue = self._telemetry_queues.get(node_id)
        if not queue:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def subscribe_telemetry(self, callback: Callable) -> None:
        """Subscribe to all telemetry frames from all nodes."""
        self._telemetry_subscribers.append(callback)

    def unsubscribe_telemetry(self, callback: Callable) -> None:
        """Unsubscribe from telemetry frames."""
        self._telemetry_subscribers.remove(callback)

    # ── System Events ─────────────────────────────────────────────

    async def publish_event(
        self,
        title: str,
        message: str,
        severity: EventSeverity = EventSeverity.INFO,
        node_id: str | None = None
    ) -> None:
        """
        Publish a system event.
        Events are things like: node connected, mission started,
        low battery warning, connection lost.
        """
        event = SystemEvent(
            id=str(uuid.uuid4()),
            severity=severity,
            title=title,
            message=message,
            node_id=node_id,
            timestamp=datetime.now(timezone.utc)
        )

        try:
            self._event_queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Event queue full — dropping oldest event")
            try:
                self._event_queue.get_nowait()
                self._event_queue.put_nowait(event)
            except asyncio.QueueEmpty:
                pass

        # Notify event subscribers directly
        for callback in self._event_subscribers:
            try:
                await callback(event)
            except Exception as e:
                logger.error(f"Event subscriber error: {e}")

        # Log critical events
        if severity == EventSeverity.CRITICAL:
            logger.critical(f"CRITICAL EVENT: {title} — {message}")
        elif severity == EventSeverity.WARNING:
            logger.warning(f"WARNING EVENT: {title} — {message}")

    def subscribe_events(self, callback: Callable) -> None:
        """Subscribe to all system events."""
        self._event_subscribers.append(callback)

    def unsubscribe_events(self, callback: Callable) -> None:
        """Unsubscribe from system events."""
        self._event_subscribers.remove(callback)

    def get_queue_sizes(self) -> dict[str, int]:
        """Returns current queue sizes — useful for debugging."""
        return {
            node_id: queue.qsize()
            for node_id, queue in self._telemetry_queues.items()
        }


# Global singleton instance
telemetry_bus = TelemetryBus()