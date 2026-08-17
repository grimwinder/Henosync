import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import aiosqlite

from ..models import (
    EventSeverity,
    Node,
    NodeCreate,
    NodePluginContext,
    NodeStatus,
    Position,
    TelemetryFrame,
)
from ..plugin_system.registry import plugin_registry
from ..storage.database import DB_PATH, init_db
from .telemetry_bus import telemetry_bus

logger = logging.getLogger(__name__)


# Seconds to wait for the next telemetry frame before declaring the stream frozen.
# A frozen generator means the plugin's async loop is stuck — distinct from a
# dead connection that still yields stale data (handled by the liveness monitor).
FRAME_TIMEOUT = 15.0

# How often node_registry polls plugin.is_connected() to detect dead connections.
# Faster than the failsafe heartbeat (5 s) so we catch drops sooner.
LIVENESS_CHECK_INTERVAL = 2.0


class NodeRegistry:
    """
    Single source of truth for all nodes in the system.

    Responsibilities:
    - Add, remove, and retrieve nodes
    - Persist nodes to SQLite
    - Connect nodes via their plugin
    - Track node status changes (ONLINE / DEGRADED / ERROR / OFFLINE)
    - Notify listeners when nodes change

    Status is always set here — never by plugins directly.
    """

    def __init__(self):
        # node_id -> Node (in-memory cache)
        self._nodes: dict[str, Node] = {}
        # node_id -> list of status change callbacks
        self._listeners: list[Callable] = []
        # node_id -> last typed TelemetryFrame (for DeviceProxy typed access)
        self._last_frames: dict[str, TelemetryFrame] = {}
        # node_id -> running telemetry stream task
        self._telemetry_tasks: dict[str, asyncio.Task] = {}
        # node_id -> running liveness monitor task
        self._liveness_tasks: dict[str, asyncio.Task] = {}

    # ── Lifecycle ─────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Initialize the registry — call once on app startup."""
        await init_db()
        await self._load_nodes_from_db()
        logger.info(f"Node registry initialized with {len(self._nodes)} nodes")

    async def shutdown(self) -> None:
        """Disconnect all nodes cleanly on shutdown."""
        logger.info("Shutting down node registry...")
        for node in list(self._nodes.values()):
            await self._disconnect_node(node)

    # ── Node CRUD ─────────────────────────────────────────────────

    async def add_node(self, node_create: NodeCreate) -> Node:
        """
        Add a new node, save it to the database,
        and attempt to connect via its plugin.
        """
        if not plugin_registry.is_registered(node_create.plugin_id):
            raise ValueError(f"Plugin not found: {node_create.plugin_id}")

        new_host = node_create.config.get("host")
        new_port = node_create.config.get("port")
        if new_host:
            for existing in self._nodes.values():
                if (
                    existing.config.get("host") == new_host
                    and existing.config.get("port") == new_port
                ):
                    raise ValueError(
                        f"A device is already connected to {new_host}:{new_port} "
                        f"({existing.name})"
                    )

        node = Node(
            name=node_create.name,
            plugin_id=node_create.plugin_id,
            config=node_create.config,
            status=NodeStatus.CONNECTING
        )

        await self._save_node_to_db(node)
        self._nodes[node.id] = node
        self._notify_listeners(node)
        asyncio.create_task(self._connect_node(node))

        logger.info(f"Added node: {node.name} ({node.id})")
        return node

    async def remove_node(self, node_id: str) -> bool:
        """Remove a node, disconnect it, and delete from database."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        await self._disconnect_node(node)
        del self._nodes[node_id]
        self._last_frames.pop(node_id, None)
        await self._delete_node_from_db(node_id)

        logger.info(f"Removed node: {node.name} ({node_id})")
        return True

    def get_node(self, node_id: str) -> Optional[Node]:
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[Node]:
        return list(self._nodes.values())

    def get_online_nodes(self) -> list[Node]:
        return [n for n in self._nodes.values() if n.status == NodeStatus.ONLINE]

    def get_last_frame(self, node_id: str) -> Optional[TelemetryFrame]:
        """Return the most recent typed TelemetryFrame for a node."""
        return self._last_frames.get(node_id)

    # ── Connection Management ─────────────────────────────────────

    async def _connect_node(self, node: Node, reconnect: bool = False) -> None:
        """Attempt to connect a node via its plugin."""
        plugin_class = plugin_registry.get_plugin_class(node.plugin_id)
        if not plugin_class:
            logger.error(f"No plugin class for: {node.plugin_id}")
            await self._update_status(node, NodeStatus.ERROR)
            return

        plugin_instance = plugin_class()
        plugin_registry.register_instance(node.id, plugin_instance)

        context = NodePluginContext(
            node_id=node.id,
            emit_event_fn=self._emit_plugin_event,
            command_completed_fn=self._handle_command_completed,
        )

        try:
            node.status = NodeStatus.CONNECTING
            self._notify_listeners(node)

            if reconnect:
                success, reason = await plugin_instance.on_reconnect(
                    node, node.config, context
                )
            else:
                success, reason = await plugin_instance.connect(
                    node, node.config, context
                )

            if not success:
                logger.error(f"Plugin connect() failed for {node.name}: {reason}")
                await self._update_status(node, NodeStatus.ERROR)
                await telemetry_bus.publish_event(
                    title="Connection Failed",
                    message=f"{node.name} could not connect: {reason}",
                    severity=EventSeverity.WARNING,
                    node_id=node.id
                )
                return

            await self._update_status(node, NodeStatus.ONLINE)
            node.last_seen = datetime.now(timezone.utc)
            logger.info(f"Connected node: {node.name}")

            telemetry_bus.create_node_queue(node.id)

            await telemetry_bus.publish_event(
                title="Node Connected",
                message=f"{node.name} is now online",
                severity=EventSeverity.INFO,
                node_id=node.id
            )

            self._telemetry_tasks[node.id] = asyncio.create_task(
                self._run_telemetry_stream(node, plugin_instance)
            )
            self._liveness_tasks[node.id] = asyncio.create_task(
                self._liveness_monitor(node, plugin_instance)
            )

        except Exception as e:
            logger.error(f"Error connecting node {node.name}: {e}")
            await self._update_status(node, NodeStatus.ERROR)

    async def _disconnect_node(self, node: Node) -> None:
        """Disconnect a node via its plugin."""
        # Cancel background tasks first so they don't race with disconnect.
        for task_dict in (self._telemetry_tasks, self._liveness_tasks):
            task = task_dict.pop(node.id, None)
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        plugin_instance = plugin_registry.get_instance(node.id)
        if plugin_instance:
            try:
                await plugin_instance.disconnect(node)
            except Exception as e:
                logger.error(f"Error disconnecting {node.name}: {e}")
            plugin_registry.remove_instance(node.id)

        telemetry_bus.remove_node_queue(node.id)
        self._last_frames.pop(node.id, None)
        await self._update_status(node, NodeStatus.OFFLINE)

    async def reconnect_node(self, node_id: str) -> bool:
        """Manually trigger a reconnection attempt."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        await self._disconnect_node(node)
        asyncio.create_task(self._connect_node(node, reconnect=True))
        return True

    # ── Telemetry ─────────────────────────────────────────────────

    async def _run_telemetry_stream(self, node: Node, plugin_instance) -> None:
        """
        Run the telemetry stream for a node in the background.

        Uses a per-frame timeout so a frozen generator (plugin's async loop
        stuck on an await) is detected here rather than requiring the plugin
        to self-exit. Status decisions are always made in this method — never
        inside the plugin.
        """
        stream = plugin_instance.telemetry_stream(node)
        try:
            while True:
                try:
                    frame = await asyncio.wait_for(
                        stream.__anext__(), timeout=FRAME_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        f"{node.name}: telemetry stream frozen — "
                        f"no frame for {FRAME_TIMEOUT}s"
                    )
                    await self._update_status(node, NodeStatus.DEGRADED)
                    break
                except StopAsyncIteration:
                    # Plugin's generator returned — stream ended cleanly.
                    logger.info(f"{node.name}: telemetry stream ended")
                    await self._update_status(node, NodeStatus.DEGRADED)
                    break

                node.last_seen = datetime.now(timezone.utc)

                # Update node state from typed fields
                if frame.position:
                    node.position = frame.position
                if frame.battery is not None:
                    node.battery_percent = frame.battery.percentage
                if frame.signal_strength is not None:
                    node.signal_strength = frame.signal_strength

                # Flatten to dict for REST API and legacy reads
                node.telemetry = frame.to_values_dict()

                # Store typed frame for DeviceProxy access
                self._last_frames[node.id] = frame

                await telemetry_bus.publish_telemetry(frame)
                self._notify_listeners(node)

        except asyncio.CancelledError:
            pass  # cancelled by _disconnect_node or _liveness_monitor — expected
        except Exception as e:
            logger.error(f"Telemetry stream error for {node.name}: {e}")
            await self._update_status(node, NodeStatus.DEGRADED)
        finally:
            self._telemetry_tasks.pop(node.id, None)
            await stream.aclose()

    async def _liveness_monitor(self, node: Node, plugin_instance) -> None:
        """
        Poll plugin.is_connected() every LIVENESS_CHECK_INTERVAL seconds.

        If the plugin reports the connection is dead, cancel the telemetry
        task and set the node to DEGRADED. This is faster than the failsafe
        heartbeat timeout and works even when a plugin keeps yielding stale
        data (which would otherwise keep last_seen current and fool the
        failsafe into thinking the node is healthy).

        This runs for every node regardless of plugin type — the default
        is_connected() returns True so the failsafe heartbeat remains the
        fallback for plugins that don't override it.
        """
        # Brief delay so the connection can fully settle before first check.
        await asyncio.sleep(LIVENESS_CHECK_INTERVAL)
        try:
            while node.id in self._telemetry_tasks:
                try:
                    alive = await asyncio.wait_for(
                        plugin_instance.is_connected(node), timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"{node.name}: is_connected() timed out — treating as dead")
                    alive = False
                except Exception as e:
                    logger.warning(f"{node.name}: is_connected() raised: {e}")
                    alive = False

                if not alive:
                    logger.warning(
                        f"{node.name}: plugin reports connection lost — "
                        f"cancelling telemetry stream"
                    )
                    task = self._telemetry_tasks.pop(node.id, None)
                    if task and not task.done():
                        task.cancel()
                    await self._update_status(node, NodeStatus.DEGRADED)
                    return

                await asyncio.sleep(LIVENESS_CHECK_INTERVAL)
        except asyncio.CancelledError:
            pass  # cancelled by _disconnect_node — expected
        finally:
            self._liveness_tasks.pop(node.id, None)

    # ── Plugin Context Callbacks ───────────────────────────────────

    async def _emit_plugin_event(
        self, title: str, message: str, severity, node_id: str
    ) -> None:
        """Callback used by NodePluginContext.emit_event()."""
        await telemetry_bus.publish_event(
            title=title, message=message, severity=severity, node_id=node_id
        )

    async def _handle_command_completed(
        self, command_id: str, success: bool, message: str
    ) -> None:
        """Callback used by NodePluginContext.command_completed()."""
        logger.info(
            f"Command {command_id} completed: success={success} msg={message}"
        )

    # ── Status Management ─────────────────────────────────────────

    async def _update_status(self, node: Node, status: NodeStatus) -> None:
        node.status = status
        self._notify_listeners(node)

    def add_listener(self, callback: Callable) -> None:
        self._listeners.append(callback)

    def _notify_listeners(self, node: Node) -> None:
        for callback in self._listeners:
            try:
                callback(node)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    # ── Database Operations ───────────────────────────────────────

    async def _save_node_to_db(self, node: Node) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                INSERT OR REPLACE INTO nodes
                (id, name, plugin_id, config, home_lat,
                home_lon, home_alt, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                node.id,
                node.name,
                node.plugin_id,
                json.dumps(node.config),
                node.home_position.lat if node.home_position else 0.0,
                node.home_position.lon if node.home_position else 0.0,
                node.home_position.alt if node.home_position else 0.0,
                datetime.now(timezone.utc).isoformat()
            ))
            await db.commit()

    async def _delete_node_from_db(self, node_id: str) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
            await db.commit()

    async def _load_nodes_from_db(self) -> None:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM nodes") as cursor:
                rows = await cursor.fetchall()

        for row in rows:
            node = Node(
                id=row["id"],
                name=row["name"],
                plugin_id=row["plugin_id"],
                config=json.loads(row["config"]),
                status=NodeStatus.OFFLINE,
                home_position=Position(
                    lat=row["home_lat"],
                    lon=row["home_lon"],
                    alt=row["home_alt"]
                )
            )
            self._nodes[node.id] = node
            logger.info(f"Loaded node from database: {node.name}")
            asyncio.create_task(self._connect_node(node))


# Global singleton instance
node_registry = NodeRegistry()
