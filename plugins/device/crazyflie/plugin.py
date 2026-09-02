"""
Crazyflie 2.x device plugin for Henosync.

Connects via cflib (Crazyradio PA USB dongle) — no ROS2 required.
Positioning is handled entirely by henosync core (vicon_manager).
Battery telemetry via cflib LogConfig (pm.vbat).

Milestone 1: connect, battery telemetry, VICON position on map.
"""

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from henosync_sdk import (
    BatteryData,
    CapabilitySpec,
    CommandResult,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    LocalOrigin,
    Node,
    NodePlugin,
    NodePluginContext,
    TelemetryFrame,
)

logger = logging.getLogger(__name__)

# ── cflib import (optional — import errors surfaced at connect time) ──────────

try:
    import cflib.crtp
    from cflib.crazyflie import Crazyflie
    from cflib.crazyflie.log import LogConfig
    from cflib.crazyflie.syncCrazyflie import SyncCrazyflie
    _CFLIB_AVAILABLE = True
except ImportError:
    _CFLIB_AVAILABLE = False

# ── One-time driver initialisation ───────────────────────────────────────────

_drivers_lock = threading.Lock()
_drivers_init = False


def _ensure_drivers() -> None:
    global _drivers_init
    with _drivers_lock:
        if not _drivers_init:
            cflib.crtp.init_drivers()
            _drivers_init = True


# ── Battery constants: Crazyflie 2.x 1S LiPo ─────────────────────────────────

_BATTERY_FULL_V = 4.2
_BATTERY_EMPTY_V = 3.0


def _voltage_to_percent(v: float) -> float:
    return max(0.0, min(100.0,
        (v - _BATTERY_EMPTY_V) / (_BATTERY_FULL_V - _BATTERY_EMPTY_V) * 100.0
    ))


# ── Per-node state ────────────────────────────────────────────────────────────

@dataclass
class _NodeState:
    cf: Any = None                  # Crazyflie instance
    connected: bool = False
    battery_v: float = 0.0
    battery_percent: float = 0.0
    log_config: Any = None          # LogConfig for pm.vbat


# ── Plugin ────────────────────────────────────────────────────────────────────

class CrazyfliePlugin(NodePlugin):
    PLUGIN_ID = "crazyflie"
    PLUGIN_NAME = "Crazyflie 2.x"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    PLUGIN_DESCRIPTION = "Crazyflie 2.x quadrotor via cflib (Crazyradio PA)"

    TELEMETRY_RATE_HZ: float = 2.0
    _CACHE_DIR = Path.home() / ".henosync" / "cflib_cache"

    def __init__(self):
        super().__init__()
        # node_id → _NodeState
        self._nodes: dict[str, _NodeState] = {}

    # ── connect / disconnect ───────────────────────────────────────────────────

    async def connect(
        self, node: Node, config: dict, context: NodePluginContext
    ) -> tuple[bool, str]:
        self._context = context

        if not _CFLIB_AVAILABLE:
            return False, (
                "cflib not installed. Run: pip install cflib"
            )

        uri = config.get("uri", "").strip()
        if not uri:
            return False, "Radio URI is required (e.g. radio://0/80/2M/E7E7E7E7E7)"

        try:
            _ensure_drivers()
        except Exception as e:
            return False, f"Failed to initialise Crazyradio drivers: {e}"

        # VICON positioning: set local_origin so vicon_manager and DeviceProxy
        # can convert between GPS and local coordinates.
        node.local_origin = LocalOrigin(
            lat=float(config.get("home_lat") or 0),
            lon=float(config.get("home_lon") or 0),
        )

        node.specs = DeviceSpecs(
            category=DeviceCategory.DRONE,
            capabilities=[
                CapabilitySpec(capability=DeviceCapability.GPS),
                CapabilitySpec(capability=DeviceCapability.BATTERY),
            ],
            coordinate_frame="local",
        )

        state = _NodeState()
        self._nodes[node.id] = state

        loop = asyncio.get_running_loop()
        connected_event = asyncio.Event()
        failed_event = asyncio.Event()

        def _on_connected(link_uri: str) -> None:
            logger.info("Crazyflie connected: %s", link_uri)
            state.connected = True
            loop.call_soon_threadsafe(connected_event.set)

        def _on_connection_failed(link_uri: str, msg: str) -> None:
            logger.warning("Crazyflie connection failed (%s): %s", link_uri, msg)
            loop.call_soon_threadsafe(failed_event.set)

        def _on_disconnected(link_uri: str) -> None:
            logger.info("Crazyflie disconnected: %s", link_uri)
            state.connected = False

        cf = Crazyflie(rw_cache=str(self._CACHE_DIR))
        cf.connected.add_callback(_on_connected)
        cf.connection_failed.add_callback(_on_connection_failed)
        cf.disconnected.add_callback(_on_disconnected)
        state.cf = cf

        # Open link in executor (cflib blocks the calling thread)
        await loop.run_in_executor(None, cf.open_link, uri)

        # Wait up to 10s for connection or failure
        t_connected = asyncio.create_task(connected_event.wait())
        t_failed = asyncio.create_task(failed_event.wait())
        done, pending = await asyncio.wait(
            [t_connected, t_failed],
            timeout=10.0,
            return_when=asyncio.FIRST_COMPLETED,
        )
        for t in pending:
            t.cancel()

        if not state.connected:
            self._nodes.pop(node.id, None)
            try:
                await loop.run_in_executor(None, cf.close_link)
            except Exception:
                pass
            return False, f"Could not connect to {uri} within 10 s"

        # Start battery log
        self._start_battery_log(node.id, state)

        return True, ""

    async def disconnect(self, node: Node) -> None:
        state = self._nodes.pop(node.id, None)
        if not state:
            return

        state.connected = False

        if state.log_config:
            try:
                state.log_config.stop()
            except Exception:
                pass

        if state.cf:
            loop = asyncio.get_running_loop()
            try:
                await loop.run_in_executor(None, state.cf.close_link)
            except Exception:
                pass

    # ── Battery logging ───────────────────────────────────────────────────────

    def _start_battery_log(self, node_id: str, state: _NodeState) -> None:
        try:
            log_config = LogConfig(name="battery", period_in_ms=500)
            log_config.add_variable("pm.vbat", "float")

            def _on_log(timestamp: int, data: dict, logconf: Any) -> None:
                s = self._nodes.get(node_id)
                if s:
                    v = data.get("pm.vbat", 0.0)
                    s.battery_v = v
                    s.battery_percent = _voltage_to_percent(v)

            def _on_error(logconf: Any, msg: str) -> None:
                logger.warning("Crazyflie log error (%s): %s", node_id[:8], msg)

            log_config.data_received_cb.add_callback(_on_log)
            log_config.error_cb.add_callback(_on_error)
            state.cf.log.add_config(log_config)
            log_config.start()
            state.log_config = log_config
        except Exception as e:
            logger.warning("Could not start battery log for %s: %s", node_id[:8], e)

    # ── is_connected ──────────────────────────────────────────────────────────

    async def is_connected(self, node: Node) -> bool:
        state = self._nodes.get(node.id)
        if not state or not state.cf:
            return False
        return state.cf.is_connected()

    # ── telemetry_stream ──────────────────────────────────────────────────────

    async def telemetry_stream(self, node: Node):
        seq = 0
        while node.id in self._nodes:
            state = self._nodes[node.id]
            yield TelemetryFrame(
                node_id=node.id,
                sequence_number=seq,
                battery=BatteryData(
                    percentage=state.battery_percent,
                    voltage=state.battery_v if state.battery_v > 0 else None,
                ),
                # Position is published separately by vicon_manager
                status_text=(
                    "Online" if node.position is not None
                    else "Connected — waiting for VICON"
                ),
            )
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    # ── get_safe_state ────────────────────────────────────────────────────────

    async def get_safe_state(self, node: Node) -> CommandResult:
        # Telemetry-only milestone — no active movement to stop.
        return CommandResult(success=True, message="No active movement")
