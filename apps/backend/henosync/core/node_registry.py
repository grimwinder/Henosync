import json
import logging
import asyncio
import aiosqlite
from datetime import datetime, timezone
from typing import Optional, Callable
from ..models import Node, NodeStatus, NodeCreate, Position
from ..storage.database import DB_PATH, init_db
from ..plugin_system.registry import plugin_registry


logger = logging.getLogger(__name__)


class NodeRegistry:
    """
    Single source of truth for all nodes in the system.

    Responsibilities:
    - Add, remove, and retrieve nodes
    - Persist nodes to SQLite
    - Connect nodes via their plugin
    - Track node status changes
    - Notify listeners when nodes change
    """

    def __init__(self):
        # node_id -> Node (in-memory cache)
        self._nodes: dict[str, Node] = {}
        # node_id -> list of status change callbacks
        self._listeners: list[Callable] = []

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
        # Validate plugin exists
        if not plugin_registry.is_registered(node_create.plugin_id):
            raise ValueError(
                f"Plugin not found: {node_create.plugin_id}"
            )

        # Create the node object
        node = Node(
            name=node_create.name,
            plugin_id=node_create.plugin_id,
            config=node_create.config,
            status=NodeStatus.CONNECTING
        )

        # Save to database
        await self._save_node_to_db(node)

        # Add to memory
        self._nodes[node.id] = node
        self._notify_listeners(node)

        # Attempt connection in background
        asyncio.create_task(self._connect_node(node))

        logger.info(f"Added node: {node.name} ({node.id})")
        return node

    async def remove_node(self, node_id: str) -> bool:
        """Remove a node, disconnect it, and delete from database."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        # Disconnect first
        await self._disconnect_node(node)

        # Remove from memory
        del self._nodes[node_id]

        # Remove from database
        await self._delete_node_from_db(node_id)

        logger.info(f"Removed node: {node.name} ({node_id})")
        return True

    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by id."""
        return self._nodes.get(node_id)

    def get_all_nodes(self) -> list[Node]:
        """Get all nodes."""
        return list(self._nodes.values())

    def get_online_nodes(self) -> list[Node]:
        """Get all nodes that are currently online."""
        return [
            n for n in self._nodes.values()
            if n.status == NodeStatus.ONLINE
        ]

    # ── Connection Management ─────────────────────────────────────

    async def _connect_node(self, node: Node) -> None:
        """Attempt to connect a node via its plugin."""
        plugin_class = plugin_registry.get_plugin_class(node.plugin_id)
        if not plugin_class:
            logger.error(f"No plugin class for: {node.plugin_id}")
            await self._update_status(node, NodeStatus.ERROR)
            return

        # Create plugin instance for this node
        plugin_instance = plugin_class()
        plugin_registry.register_instance(node.id, plugin_instance)

        try:
            node.status = NodeStatus.CONNECTING
            self._notify_listeners(node)

            success = await plugin_instance.connect(node, node.config)

            if success:
                await self._update_status(node, NodeStatus.ONLINE)
                node.last_seen = datetime.now(timezone.utc)
                logger.info(f"Connected node: {node.name}")

                # Start telemetry stream in background
                asyncio.create_task(
                    self._run_telemetry_stream(node, plugin_instance)
                )
            else:
                await self._update_status(node, NodeStatus.OFFLINE)
                logger.warning(f"Failed to connect node: {node.name}")

        except Exception as e:
            logger.error(f"Error connecting node {node.name}: {e}")
            await self._update_status(node, NodeStatus.ERROR)

    async def _disconnect_node(self, node: Node) -> None:
        """Disconnect a node via its plugin."""
        plugin_instance = plugin_registry.get_instance(node.id)
        if plugin_instance:
            try:
                await plugin_instance.disconnect(node)
            except Exception as e:
                logger.error(f"Error disconnecting {node.name}: {e}")
            plugin_registry.remove_instance(node.id)

        await self._update_status(node, NodeStatus.OFFLINE)

    async def reconnect_node(self, node_id: str) -> bool:
        """Manually trigger a reconnection attempt."""
        node = self._nodes.get(node_id)
        if not node:
            return False

        await self._disconnect_node(node)
        asyncio.create_task(self._connect_node(node))
        return True

    # ── Telemetry ─────────────────────────────────────────────────

    async def _run_telemetry_stream(self, node, plugin_instance) -> None:
        """Run the telemetry stream for a node in the background."""
        try:
            async for frame in plugin_instance.telemetry_stream(node):
                # Update node with latest telemetry values
                node.last_seen = datetime.now(timezone.utc)
                node.telemetry = frame.values

                # Update standard fields if present
                if "battery_percent" in frame.values:
                    node.battery_percent = frame.values["battery_percent"]
                if "signal_strength" in frame.values:
                    node.signal_strength = frame.values["signal_strength"]
                if all(k in frame.values for k in ["lat", "lon"]):
                    node.position = Position(
                        lat=frame.values["lat"],
                        lon=frame.values["lon"],
                        alt=frame.values.get("alt", 0.0)
                    )

                # Notify listeners of updated telemetry
                self._notify_listeners(node)

        except Exception as e:
            logger.error(f"Telemetry stream error for {node.name}: {e}")
            await self._update_status(node, NodeStatus.DEGRADED)

    # ── Status Management ─────────────────────────────────────────

    async def _update_status(
        self,
        node: Node,
        status: NodeStatus
    ) -> None:
        """Update a node's status and notify listeners."""
        node.status = status
        self._notify_listeners(node)

    def add_listener(self, callback: Callable) -> None:
        """
        Register a callback to be called when any node changes.
        Used by the WebSocket server to push updates to the GUI.
        """
        self._listeners.append(callback)

    def _notify_listeners(self, node: Node) -> None:
        """Notify all listeners of a node change."""
        for callback in self._listeners:
            try:
                callback(node)
            except Exception as e:
                logger.error(f"Listener error: {e}")

    # ── Database Operations ───────────────────────────────────────

    async def _save_node_to_db(self, node: Node) -> None:
        """Save a node to the database."""
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
        """Delete a node from the database."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM nodes WHERE id = ?",
                (node_id,)
            )
            await db.commit()

    async def _load_nodes_from_db(self) -> None:
        """Load all saved nodes from database on startup."""
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