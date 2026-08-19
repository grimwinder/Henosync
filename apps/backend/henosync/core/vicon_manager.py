"""
vicon_manager — Core VICON DataStream positioning for all nodes.

One TCP connection to the VICON PC serves every node configured with
position_source="vicon". The connection is configured independently of
devices and persisted in vicon_connections (DB). Device plugins set
node.local_origin in setup_node() and the manager handles the rest.
"""

import asyncio
import logging
import socket
import time
from datetime import datetime, timezone
from math import cos, radians
from typing import Any

import aiosqlite

from ..models import EventSeverity, NodeStatus, Position, TelemetryFrame
from ..storage.database import DB_PATH
from .telemetry_bus import telemetry_bus

logger = logging.getLogger(__name__)

try:
    from vicon_dssdk import ViconDataStream as _DataStream
    _VICON_AVAILABLE = True
except ImportError:
    _VICON_AVAILABLE = False

_POLL_HZ = 20.0
_RETRY_INTERVAL = 5.0
_FIX_TIMEOUT = 10.0


class VICONManager:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        self._saved_host: str | None = None
        self._saved_port: int = 801
        # host → DataStream.Client
        self._clients: dict[str, Any] = {}
        # host → monotonic time of last failure (for retry backoff)
        self._last_failure: dict[str, float] = {}
        # node_id → monotonic time when first seen as VICON-configured
        self._first_seen: dict[str, float] = {}
        # node_id → True once no-fix warning has fired
        self._fix_warned: dict[str, bool] = {}
        # node_id → sequence counter for position frames
        self._sequences: dict[str, int] = {}
        self._sdk_warning_logged: bool = False
        self._cached_subjects: list[str] = []

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def saved_connection(self) -> tuple[str, int] | None:
        if self._saved_host:
            return (self._saved_host, self._saved_port)
        return None

    @property
    def is_connected(self) -> bool:
        return len(self._clients) > 0

    # ── Lifecycle ───────────────────────────────────────────────────────────────

    async def start(self) -> None:
        await self._load_saved()
        self._running = True
        self._task = asyncio.ensure_future(self._run())
        logger.info("VICON manager started")

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        loop = asyncio.get_running_loop()
        for client in self._clients.values():
            try:
                await loop.run_in_executor(None, client.Disconnect)
            except Exception:
                pass
        self._clients.clear()
        logger.info("VICON manager stopped")

    # ── Public API ──────────────────────────────────────────────────────────────

    async def connect(self, host: str, port: int = 801) -> None:
        """Persist a VICON connection to DB; the run loop connects immediately."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO vicon_connections (id, host, port) "
                "VALUES ('default', ?, ?)",
                (host, port),
            )
            await db.commit()
        old_host = self._saved_host
        if old_host and old_host != host and old_host in self._clients:
            loop = asyncio.get_running_loop()
            client = self._clients.pop(old_host)
            try:
                await loop.run_in_executor(None, client.Disconnect)
            except Exception:
                pass
        self._saved_host = host
        self._saved_port = port
        self._last_failure.pop(host, None)
        logger.info("vicon_manager: saved connection → %s:%d", host, port)

    async def disconnect(self) -> None:
        """Disconnect from VICON and remove the saved connection from DB."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM vicon_connections WHERE id = 'default'")
            await db.commit()
        host = self._saved_host
        self._saved_host = None
        if host:
            self._last_failure.pop(host, None)
            loop = asyncio.get_running_loop()
            client = self._clients.pop(host, None)
            if client:
                try:
                    await loop.run_in_executor(None, client.Disconnect)
                except Exception:
                    pass
        self._first_seen.clear()
        self._fix_warned.clear()
        self._cached_subjects = []
        logger.info("vicon_manager: disconnected and cleared saved connection")

    async def get_subject_names(self) -> list[str]:
        """Return subject names from the most recently polled frame."""
        return list(self._cached_subjects)

    # ── Main loop ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        from .node_registry import node_registry

        loop = asyncio.get_running_loop()

        while self._running:
            if not self._saved_host:
                await asyncio.sleep(2.0)
                continue

            host = self._saved_host
            port = self._saved_port

            vicon_nodes = [
                node for node in node_registry.get_all_nodes()
                if (
                    node.config.get("position_source") == "vicon"
                    and node.status in (NodeStatus.ONLINE, NodeStatus.DEGRADED)
                )
            ]

            # Connect if not already connected (with retry backoff)
            if host not in self._clients:
                now = time.monotonic()
                if now - self._last_failure.get(host, 0.0) >= _RETRY_INTERVAL:
                    await self._connect_host(host, port, loop)

            # Poll one frame and update positions
            client = self._clients.get(host)
            if client:
                try:
                    got_frame = await loop.run_in_executor(None, client.GetFrame)
                    if got_frame:
                        # Update subject cache from this frame
                        try:
                            self._cached_subjects = list(client.GetSubjectNames())
                        except Exception:
                            pass
                        for node in vicon_nodes:
                            await self._update_node(client, node)
                except Exception as e:
                    logger.warning("vicon_manager [%s]: %s", host, e)
                    self._clients.pop(host, None)
                    self._cached_subjects = []
                    self._last_failure[host] = time.monotonic()

            if vicon_nodes:
                await self._check_no_fix(vicon_nodes)

            await asyncio.sleep(1.0 / _POLL_HZ)

    # ── Connection ──────────────────────────────────────────────────────────────

    async def _load_saved(self) -> None:
        try:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute(
                    "SELECT host, port FROM vicon_connections WHERE id = 'default'"
                ) as cursor:
                    row = await cursor.fetchone()
                    if row:
                        self._saved_host = row[0]
                        self._saved_port = row[1]
                        logger.info(
                            "vicon_manager: loaded saved connection → %s:%d",
                            self._saved_host, self._saved_port,
                        )
        except Exception as e:
            logger.warning("vicon_manager: could not load saved connection: %s", e)

    async def _connect_host(self, host: str, port: int, loop) -> None:
        if not _VICON_AVAILABLE:
            if not self._sdk_warning_logged:
                self._sdk_warning_logged = True
                logger.error(
                    "vicon_manager: vicon-dssdk not installed. "
                    "Install from the Vicon DataStream SDK directory."
                )
            self._last_failure[host] = time.monotonic() + 86400
            return

        # TCP reachability check before calling the DataStream SDK.
        # The SDK's C++ destructor crashes the process on failed connections
        # (STATUS_STACK_BUFFER_OVERRUN), so we must never call Connect() on an
        # unreachable host.
        reachable = await loop.run_in_executor(
            None, lambda: _tcp_reachable(host, port)
        )
        if not reachable:
            self._last_failure[host] = time.monotonic()
            logger.warning("vicon_manager: %s:%d unreachable", host, port)
            return

        try:
            client = await loop.run_in_executor(
                None, lambda: self._connect_client(host, port)
            )
            self._clients[host] = client
            self._last_failure.pop(host, None)
            logger.info("vicon_manager: connected to %s:%d", host, port)
        except Exception as e:
            self._last_failure[host] = time.monotonic()
            logger.error("vicon_manager: cannot connect to %s:%d: %s", host, port, e)

    @staticmethod
    def _connect_client(host: str, port: int) -> Any:
        client = _DataStream.Client()
        addr = f"{host}:{port}" if port != 801 else host
        client.Connect(addr)  # raises DataStreamException on failure
        client.EnableSegmentData()
        client.SetStreamMode(_DataStream.Client.StreamMode.EClientPull)
        return client

    # ── Position update ─────────────────────────────────────────────────────────

    async def _update_node(self, client: Any, node: Any) -> None:
        object_name = node.config.get("vicon_object_name", "")
        if not object_name:
            return

        try:
            segment_name = client.GetSubjectRootSegmentName(object_name)
            translation, occluded = client.GetSegmentGlobalTranslation(
                object_name, segment_name
            )
        except Exception:
            return
        if occluded:
            return

        try:
            rotation, _ = client.GetSegmentGlobalRotationEulerXYZ(
                object_name, segment_name
            )
            yaw = rotation[2]
        except Exception:
            yaw = 0.0

        x_m = translation[0] / 1000.0
        y_m = translation[1] / 1000.0
        z_m = translation[2] / 1000.0

        home_lat = float(node.config.get("home_lat") or 0)
        home_lon = float(node.config.get("home_lon") or 0)
        lat, lon = _local_to_gps(x_m, y_m, home_lat, home_lon)

        position = Position(lat=lat, lon=lon, alt=z_m, heading=yaw)
        node.position = position
        node.last_seen = datetime.now(timezone.utc)

        self._fix_warned.pop(node.id, None)

        seq = self._sequences.get(node.id, 0)
        self._sequences[node.id] = seq + 1

        frame = TelemetryFrame(node_id=node.id, sequence_number=seq, position=position)
        await telemetry_bus.publish_telemetry(frame)

    # ── No-fix warning ──────────────────────────────────────────────────────────

    async def _check_no_fix(self, vicon_nodes: list) -> None:
        now = time.monotonic()
        for node in vicon_nodes:
            if node.id not in self._first_seen:
                self._first_seen[node.id] = now
            if (
                node.position is None
                and not self._fix_warned.get(node.id)
                and now - self._first_seen[node.id] > _FIX_TIMEOUT
            ):
                self._fix_warned[node.id] = True
                await telemetry_bus.publish_event(
                    title="No VICON position",
                    message=(
                        f"{node.name}: no position received after {_FIX_TIMEOUT:.0f}s. "
                        "Check VICON Tracker is running and the object name matches."
                    ),
                    severity=EventSeverity.WARNING,
                    node_id=node.id,
                )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _tcp_reachable(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if a TCP connection to host:port succeeds within timeout."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ── Coordinate conversion ───────────────────────────────────────────────────────

def _local_to_gps(
    x_m: float, y_m: float, home_lat: float, home_lon: float
) -> tuple[float, float]:
    """Equirectangular: X=East, Y=North from arena origin. Accurate <1km."""
    R = 6_371_000.0
    PI = 3.141592653589793
    lat = home_lat + (y_m / R) * (180.0 / PI)
    lon = home_lon + (x_m / (R * cos(radians(home_lat)))) * (180.0 / PI)
    return lat, lon


vicon_manager = VICONManager()
