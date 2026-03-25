import asyncio
import json
import logging
from fastapi import WebSocket, WebSocketDisconnect
from ..core.telemetry_bus import telemetry_bus
from ..models import TelemetryFrame, SystemEvent

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages all active WebSocket connections from the GUI.
    Handles connect, disconnect, and broadcasting messages.
    """

    def __init__(self):
        # All active WebSocket connections
        self._telemetry_connections: list[WebSocket] = []
        self._event_connections: list[WebSocket] = []

    async def connect_telemetry(self, websocket: WebSocket) -> None:
        """Accept a new telemetry WebSocket connection."""
        await websocket.accept()
        self._telemetry_connections.append(websocket)
        logger.info(
            f"Telemetry WebSocket connected. "
            f"Total: {len(self._telemetry_connections)}"
        )

    async def connect_events(self, websocket: WebSocket) -> None:
        """Accept a new events WebSocket connection."""
        await websocket.accept()
        self._event_connections.append(websocket)
        logger.info(
            f"Events WebSocket connected. "
            f"Total: {len(self._event_connections)}"
        )

    def disconnect_telemetry(self, websocket: WebSocket) -> None:
        """Remove a disconnected telemetry WebSocket."""
        if websocket in self._telemetry_connections:
            self._telemetry_connections.remove(websocket)
        logger.info(
            f"Telemetry WebSocket disconnected. "
            f"Total: {len(self._telemetry_connections)}"
        )

    def disconnect_events(self, websocket: WebSocket) -> None:
        """Remove a disconnected events WebSocket."""
        if websocket in self._event_connections:
            self._event_connections.remove(websocket)

    async def broadcast_telemetry(self, frame: TelemetryFrame) -> None:
        """Broadcast a telemetry frame to all connected GUI clients."""
        if not self._telemetry_connections:
            return

        message = json.dumps({
            "type": "telemetry",
            "node_id": frame.node_id,
            "timestamp": frame.timestamp.isoformat(),
            "sequence": frame.sequence_number,
            "values": frame.values
        })

        disconnected = []
        for websocket in self._telemetry_connections:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.append(websocket)

        # Clean up dead connections
        for ws in disconnected:
            self.disconnect_telemetry(ws)

    async def broadcast_event(self, event: SystemEvent) -> None:
        """Broadcast a system event to all connected GUI clients."""
        if not self._event_connections:
            return

        message = json.dumps({
            "type": "event",
            "id": event.id,
            "severity": event.severity,
            "title": event.title,
            "message": event.message,
            "node_id": event.node_id,
            "timestamp": event.timestamp.isoformat(),
            "acknowledged": event.acknowledged
        })

        disconnected = []
        for websocket in self._event_connections:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.append(websocket)

        for ws in disconnected:
            self.disconnect_events(ws)


# Global singleton
connection_manager = ConnectionManager()


async def telemetry_websocket_handler(websocket: WebSocket) -> None:
    """
    Handles a telemetry WebSocket connection.
    Streams all node telemetry to the connected GUI client.
    """
    await connection_manager.connect_telemetry(websocket)

    # Subscribe to telemetry bus
    async def on_telemetry(frame: TelemetryFrame):
        await connection_manager.broadcast_telemetry(frame)

    telemetry_bus.subscribe_telemetry(on_telemetry)

    try:
        # Keep connection alive — wait for client to disconnect
        while True:
            await asyncio.sleep(1)
            # Send a ping to detect dead connections
            try:
                await websocket.send_text(
                    json.dumps({"type": "ping"})
                )
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        telemetry_bus.unsubscribe_telemetry(on_telemetry)
        connection_manager.disconnect_telemetry(websocket)


async def events_websocket_handler(websocket: WebSocket) -> None:
    """
    Handles an events WebSocket connection.
    Streams all system events to the connected GUI client.
    """
    await connection_manager.connect_events(websocket)

    async def on_event(event: SystemEvent):
        await connection_manager.broadcast_event(event)

    telemetry_bus.subscribe_events(on_event)

    try:
        while True:
            await asyncio.sleep(1)
            try:
                await websocket.send_text(
                    json.dumps({"type": "ping"})
                )
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        telemetry_bus.unsubscribe_events(on_event)
        connection_manager.disconnect_events(websocket)