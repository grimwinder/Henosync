import asyncio
import random
import sys
import os
from datetime import datetime, timezone
from typing import AsyncGenerator, Any

# Add backend to path so imports resolve correctly
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../apps/backend'))

from henosync.plugin_system.interfaces import NodePlugin
from henosync.models import (
    Node, TelemetryFrame, CommandResult,
    DeviceSpecs, DeviceCategory, CapabilitySpec, DeviceCapability,
)


class SimDummyPlugin(NodePlugin):
    """
    Simulation plugin — mimics a real node without any hardware.
    Use this for testing missions and developing the UI.
    """

    PLUGIN_ID = "sim-dummy"
    PLUGIN_NAME = "Simulation Node"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team"
    PLUGIN_DESCRIPTION = "Simulated node for testing"

    def __init__(self):
        self._running: dict[str, bool] = {}
        self._battery: dict[str, float] = {}
        self._position: dict[str, dict] = {}

    async def connect(self, node: Node, config: dict[str, Any]) -> bool:
        self._running[node.id] = True
        self._battery[node.id] = 100.0
        self._position[node.id] = {
            "lat": config.get("home_lat", -37.8136),
            "lon": config.get("home_lon", 144.9631),
            "alt": 0.0
        }

        # Build device specs from selected capabilities
        selected_caps = config.get("selected_capabilities", [])
        cap_specs = []
        for cap_id in selected_caps:
            try:
                cap_specs.append(CapabilitySpec(capability=DeviceCapability(cap_id)))
            except ValueError:
                pass  # ignore unknown capability ids

        node.specs = DeviceSpecs(
            category=DeviceCategory.DRONE,
            capabilities=cap_specs,
            has_gps="gps" in selected_caps,
            coordinate_frame="gps",
        )

        print(f"[sim-dummy] Connected node: {node.name} with caps: {selected_caps}")
        return True

    async def disconnect(self, node: Node) -> None:
        self._running[node.id] = False
        print(f"[sim-dummy] Disconnected node: {node.name}")

    async def send_command(
        self,
        node: Node,
        capability: str,
        params: dict[str, Any]
    ) -> CommandResult:
        if capability == "move_to":
            await asyncio.sleep(2.0)
            self._position[node.id] = {
                "lat": params.get("lat", 0),
                "lon": params.get("lon", 0),
                "alt": params.get("alt", 0)
            }
            return CommandResult(success=True, message="Moved to position")

        elif capability == "wait":
            duration = params.get("duration_seconds", 1)
            await asyncio.sleep(duration)
            return CommandResult(success=True, message=f"Waited {duration}s")

        elif capability == "return_home":
            await asyncio.sleep(3.0)
            return CommandResult(success=True, message="Returned to home")

        return CommandResult(
            success=False,
            message=f"Unknown capability: {capability}"
        )

    async def telemetry_stream(
        self,
        node: Node
    ) -> AsyncGenerator[TelemetryFrame, None]:
        seq = 0
        while self._running.get(node.id, False):
            self._battery[node.id] = max(
                0,
                self._battery[node.id] - 0.01
            )
            pos = self._position.get(node.id, {})

            yield TelemetryFrame(
                node_id=node.id,
                timestamp=datetime.now(timezone.utc),
                sequence_number=seq,
                values={
                    "battery_percent": round(self._battery[node.id], 1),
                    "signal_strength": round(random.uniform(70, 100), 1),
                    "lat": pos.get("lat", 0),
                    "lon": pos.get("lon", 0),
                    "alt": pos.get("alt", 0),
                    "status_text": "Simulating"
                }
            )
            seq += 1
            await asyncio.sleep(1.0)

    async def get_safe_state(self, node: Node) -> CommandResult:
        self._running[node.id] = False
        return CommandResult(success=True, message="Simulation stopped safely")