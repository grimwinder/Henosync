"""
vicon_manager — Core VICON DataStream positioning for all nodes.

One TCP connection per VICON PC serves every node configured with
position_source="vicon". Device plugins are completely unaware of VICON.

The manager polls VICON frames, converts local-frame (mm) to WGS84,
writes node.position directly, and publishes a position-only TelemetryFrame
so the frontend map updates in real time.
"""

import asyncio
import logging
from datetime import datetime, timezone
from math import cos, radians
from typing import Any

from ..models import EventSeverity, NodeStatus, Position, TelemetryFrame
from .telemetry_bus import telemetry_bus

logger = logging.getLogger(__name__)

try:
    from vicon_dssdk import DataStream as _DataStream
    _VICON_AVAILABLE = True
except ImportError:
    _VICON_AVAILABLE = False

_POLL_HZ = 20.0            # position updates sent to frontend
_RETRY_INTERVAL = 5.0      # seconds between reconnection attempts after failure
_FIX_TIMEOUT = 10.0        # seconds before emitting a no-fix warning


class VICONManager:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._running = False
        # vicon_host → DataStream.Client
        self._clients: dict[str, Any] = {}
        # vicon_host → monotonic time of last failure (for retry backoff)
        self._last_failure: dict[str, float] = {}
        # node_id → monotonic time when first seen as VICON-configured
        self._first_seen: dict[str, float] = {}
        # node_id → True once no-fix warning has fired
        self._fix_warned: dict[str, bool] = {}
        # node_id → sequence counter for position frames
        self._sequences: dict[str, int] = {}
        # suppress repeated "SDK not installed" log
        self._sdk_warning_logged: bool = False

    async def start(self) -> None:
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

    # ── Main loop ──────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        # Import here to avoid circular import at module load time
        from .node_registry import node_registry

        loop = asyncio.get_running_loop()

        while self._running:
            vicon_nodes = [
                node for node in node_registry.get_all_nodes()
                if (
                    node.config.get("position_source") == "vicon"
                    and node.status in (NodeStatus.ONLINE, NodeStatus.DEGRADED)
                )
            ]

            if not vicon_nodes:
                await asyncio.sleep(2.0)
                continue

            # Group by vicon_host — one connection per VICON PC
            by_host: dict[str, list] = {}
            for node in vicon_nodes:
                host = node.config.get("vicon_host", "localhost")
                by_host.setdefault(host, []).append(node)

            # Connect to any host we haven't seen yet (respecting retry backoff)
            import time
            now = time.monotonic()
            for host in by_host:
                if host not in self._clients:
                    last_fail = self._last_failure.get(host, 0.0)
                    if now - last_fail >= _RETRY_INTERVAL:
                        await self._connect(host, loop)

            # Poll each connected host
            for host, nodes in by_host.items():
                client = self._clients.get(host)
                if not client:
                    continue
                try:
                    result = await loop.run_in_executor(None, client.GetFrame)
                    if result.Result != _DataStream.Result.Success:
                        continue
                    for node in nodes:
                        await self._update_node(client, node)
                except Exception as e:
                    logger.warning("vicon_manager [%s]: %s", host, e)
                    self._clients.pop(host, None)
                    self._last_failure[host] = time.monotonic()

            # No-fix warnings for nodes that never received a position
            await self._check_no_fix(vicon_nodes)

            await asyncio.sleep(1.0 / _POLL_HZ)

    # ── Connection ─────────────────────────────────────────────────────────────

    async def _connect(self, host: str, loop) -> None:
        if not _VICON_AVAILABLE:
            if not self._sdk_warning_logged:
                self._sdk_warning_logged = True
                logger.error(
                    "vicon_manager: vicon-dssdk not installed — run: pip install vicon-dssdk"
                )
            import time
            # Block retries so the loop stays quiet until the backend restarts.
            self._last_failure[host] = time.monotonic() + 86400
            return
        try:
            client = await loop.run_in_executor(
                None, lambda: self._connect_client(host)
            )
            self._clients[host] = client
            self._last_failure.pop(host, None)
            logger.info("vicon_manager: connected to %s", host)
        except Exception as e:
            import time
            self._last_failure[host] = time.monotonic()
            logger.error("vicon_manager: cannot connect to %s: %s", host, e)

    @staticmethod
    def _connect_client(host: str) -> Any:
        client = _DataStream.Client()
        result = client.Connect(host)
        if result.Result != _DataStream.Result.Success:
            raise ConnectionError(
                f"VICON DataStream connect failed for {host}. "
                "Is VICON Tracker running and reachable?"
            )
        client.EnableSegmentData()
        client.SetStreamMode(_DataStream.StreamMode.ClientPull)
        return client

    # ── Position update ────────────────────────────────────────────────────────

    async def _update_node(self, client: Any, node: Any) -> None:
        object_name = node.config.get("vicon_object_name", "")
        if not object_name:
            return

        trans = client.GetSegmentGlobalTranslation(object_name, object_name)
        if trans.Result != _DataStream.Result.Success or trans.Occluded:
            return

        rot = client.GetSegmentGlobalRotationEulerXYZ(object_name, object_name)

        x_m = trans.Translation[0] / 1000.0  # VICON returns mm
        y_m = trans.Translation[1] / 1000.0
        z_m = trans.Translation[2] / 1000.0
        yaw = rot.Rotation[2] if rot.Result == _DataStream.Result.Success else 0.0

        home_lat = float(node.config.get("home_lat") or 0)
        home_lon = float(node.config.get("home_lon") or 0)
        lat, lon = _local_to_gps(x_m, y_m, home_lat, home_lon)

        position = Position(lat=lat, lon=lon, alt=z_m, heading=yaw)
        node.position = position
        node.last_seen = datetime.now(timezone.utc)

        # Reset no-fix warning once we have a fix
        self._fix_warned.pop(node.id, None)

        seq = self._sequences.get(node.id, 0)
        self._sequences[node.id] = seq + 1

        frame = TelemetryFrame(node_id=node.id, sequence_number=seq, position=position)
        await telemetry_bus.publish_telemetry(frame)

    # ── No-fix warning ─────────────────────────────────────────────────────────

    async def _check_no_fix(self, vicon_nodes: list) -> None:
        import time
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
                        "Check VICON Tracker is running, the object name matches, "
                        "and vicon_host is correct."
                    ),
                    severity=EventSeverity.WARNING,
                    node_id=node.id,
                )


# ── Coordinate conversion ──────────────────────────────────────────────────────

def _local_to_gps(
    x_m: float, y_m: float, home_lat: float, home_lon: float
) -> tuple[float, float]:
    """Equirectangular: X=East, Y=North from arena origin. Accurate <1km."""
    R = 6_371_000.0
    PI = 3.141592653589793
    lat = home_lat + (y_m / R) * (180.0 / PI)
    lon = home_lon + (x_m / (R * cos(radians(home_lat)))) * (180.0 / PI)
    return lat, lon


# Global singleton
vicon_manager = VICONManager()
