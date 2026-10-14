"""
UE Sim Area — send two angles, a radius, and agent count to the Unreal Engine simulator.

The operator picks 1–3 UE Sim devices and enters angle_1/angle_2 in degrees,
a radius, and environment type. nag is auto-computed from the number of selected
devices. One TCP JSON packet is sent via the first device's set_area command.

Henosync only sets the mission up; all partitioning is done in the sim
(mission abstraction). Packet keys map to coverage_fns.Agents(...):
angle_1/angle_2 -> ang_bounds, radius -> R, nag/envi_type 1:1.
See NOTES.md in this folder for the design discussion and open questions.
"""

import asyncio
import json as _json
import logging
from math import pi, radians

from henosync_sdk import (
    ControlPlugin,
    DeviceCategory,
    EventSeverity,
    OperationState,
    OperationStatus,
    UIContribution,
)

logger = logging.getLogger(__name__)


class UESimAreaPlugin(ControlPlugin):
    PLUGIN_ID = "ue-sim-area"
    PLUGIN_NAME = "UE Sim Area"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    OPERATION_NAME = "UE Sim Area"
    OPERATION_DESCRIPTION = "Send two angles and a radius to the Unreal Engine simulator."

    REQUIRED_CAPABILITIES = []
    SUPPORTED_CATEGORIES = [DeviceCategory.AGV]

    PRIORITY = 1

    def __init__(self) -> None:
        super().__init__()
        self._state: OperationState = OperationState.IDLE
        self._status_text: str = ""

    async def start(self, context) -> None:
        self._state = OperationState.RUNNING

        # nag = number of device slots in the step (always 3); "Any available robot"
        # stores "" which is falsy so we can't count by value — just use slot count.
        nag = 3

        # coverage_fns.Agents expects ang_bounds in radians normalised to [0, 2π).
        # Whole circle: enter 0° and 359.9°, NOT 0° and 360°.
        angle_1 = radians(float(self._config.get("angle_1", 0.0))) % (2 * pi)
        angle_2 = radians(float(self._config.get("angle_2", 0.0))) % (2 * pi)
        radius = float(self._config.get("radius") or 0.0)
        if radius <= 0:
            await self._fail(context, f"Radius must be greater than 0 (got {radius})")
            return

        envi_type = self._config.get("envi_type") or "Circular"

        sim_host = self._config.get("sim_host") or "192.168.0.136"
        sim_port = int(self._config.get("sim_port") or 7000)

        # Send one TCP connection per agent, each to its own port (sim_port + ag_id - 1).
        for i in range(nag):
            port = sim_port + i
            packet = (_json.dumps({
                "angle_1": angle_1,
                "angle_2": angle_2,
                "radius": radius,
                "ag_id": i + 1,
                "nag": nag,
                "envi_type": envi_type,
            }) + "\n").encode()
            try:
                reader, writer = await asyncio.wait_for(
                    asyncio.open_connection(sim_host, port), timeout=5.0
                )
                writer.write(packet)
                await writer.drain()
                writer.close()
                await writer.wait_closed()
            except Exception as e:
                await self._fail(context, f"TCP send ag_id={i+1} to {sim_host}:{port} failed: {type(e).__name__}: {e}")
                return

        self._status_text = (
            f"Sent {nag} agent(s) ({envi_type}), angles ({angle_1:.4f}, {angle_2:.4f} rad), "
            f"radius {radius} → {sim_host}:{sim_port}"
        )
        logger.info("UESimArea: %s", self._status_text)
        self._state = OperationState.COMPLETED

    async def _fail(self, context, message: str) -> None:
        self._status_text = message
        self._state = OperationState.FAILED
        await context.send_alert("UE Sim Area failed", message, EventSeverity.WARNING)

    async def stop(self) -> None:
        self._stop_requested = True

    def get_status(self) -> OperationStatus:
        return OperationStatus(state=self._state, status_text=self._status_text)

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution(
            display_name="UE Sim Area",
            description="Send two angles and a radius to the Unreal Engine simulator.",
            icon="map",
            config_schema={
                "node_id_1": {
                    "type": "device_select",
                    "label": "Device 1",
                    "required": True,
                    "description": "First UE Sim device (required).",
                },
                "node_id_2": {
                    "type": "device_select",
                    "label": "Device 2",
                    "required": False,
                    "description": "Second UE Sim device (optional).",
                },
                "node_id_3": {
                    "type": "device_select",
                    "label": "Device 3",
                    "required": False,
                    "description": "Third UE Sim device (optional).",
                },
                "angle_1": {
                    "type": "number",
                    "label": "Angle 1 (°)",
                    "required": True,
                    "default": 0,
                },
                "angle_2": {
                    "type": "number",
                    "label": "Angle 2 (°)",
                    "required": True,
                    "default": 0,
                    "description": "Sector runs counter-clockwise from Angle 1 to Angle 2. For the whole circle enter 0 and 359.9 (not 360).",
                },
                "radius": {
                    "type": "number",
                    "label": "Radius (sim units, assumed metres)",
                    "required": True,
                    "default": 50,
                    "min": 0.01,
                    "description": "Size of the circular area in the sim.",
                },
                "envi_type": {
                    "type": "select",
                    "label": "Environment Type",
                    "required": True,
                    "default": "Circular",
                    "options": [
                        {"label": "Circular", "value": "Circular"},
                    ],
                },
                "sim_host": {
                    "type": "string",
                    "label": "Sim Receiver IP",
                    "required": False,
                    "default": "192.168.0.136",
                    "placeholder": "e.g. 192.168.0.136",
                    "description": "IP of the machine running sim_receiver.py",
                },
                "sim_port": {
                    "type": "number",
                    "label": "Sim Receiver Port",
                    "required": False,
                    "default": 7000,
                    "min": 1,
                    "max": 65535,
                },
            },
        )
