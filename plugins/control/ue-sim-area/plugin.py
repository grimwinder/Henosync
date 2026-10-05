"""
UE Sim Area — send two angles and a radius to the Unreal Engine simulator.

The operator picks a device (a ue-sim node) and enters angle_1 and angle_2
in degrees plus a radius. The angles are converted to radians and all three
are sent once via the device's "set_area" custom command, which the ue-sim
plugin sends as a JSON line over TCP to the sim host.
"""

import logging
from math import radians

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

        node_id = self._config.get("node_id", "")
        device = next((d for d in context.devices if d.id == node_id), None)
        if device is None:
            await self._fail(context, f"Device {node_id!r} not available")
            return

        angle_1 = radians(float(self._config.get("angle_1", 0.0)))
        angle_2 = radians(float(self._config.get("angle_2", 0.0)))
        radius = float(self._config.get("radius", 0.0))

        result = await device.send_command("set_area", {"angle_1": angle_1, "angle_2": angle_2, "radius": radius})
        if not result.success:
            await self._fail(context, f"Sending area failed: {result.message}")
            return

        self._status_text = f"Sent angles ({angle_1:.4f}, {angle_2:.4f} rad), radius {radius} to {device.name}"
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
                "node_id": {
                    "type": "device_select",
                    "label": "Device",
                    "required": True,
                    "description": "The UE Sim device to send the area to.",
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
                },
                "radius": {
                    "type": "number",
                    "label": "Radius",
                    "required": True,
                    "default": 0,
                },
            },
        )
