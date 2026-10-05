"""
UE Sim Area — send two angles and a radius to the Unreal Engine simulator.

The operator picks a device (a ue-sim node) and enters angle_1 and angle_2
in degrees, a radius, and the agent ID / agent count / environment type that
the sim's coverage_fns.Agents constructor needs. The angles are converted to
radians and everything is sent once via the device's "set_area" custom
command, which the ue-sim plugin sends as a JSON line over TCP to the sim host.

Henosync only sets the mission up; all partitioning is done in the sim
(mission abstraction). Packet keys map to coverage_fns.Agents(...):
angle_1/angle_2 -> ang_bounds, radius -> R, ag_id/nag/envi_type 1:1.
See NOTES.md in this folder for the design discussion and open questions.

Verified against the sim developer's coverage_fns.py (BilateralInteraction):
  WORKS
    - Single robot (ag_id=1, nag=1), Circular, calling BilateralInteraction
      with a neighbour id + neighbour slice: merges the two slices and keeps
      half (e.g. robot 0-60 deg + neighbour 60-180 deg -> robot 0-90 deg).
    - 3+ agents, Circular: converges to equal slices.
    - Wrap-around sectors (e.g. -90..90 deg is sent as [4.712, 1.571] rad).
  DOES NOT WORK
    - Whole circle as 0..360 deg: 360 wraps to 0 and [0, 0] is a zero-width
      sector. Enter 0..359.9 instead.
    - RegularPolygons: coverage_fns raises UnboundLocalError (A_self) after
      10 interactions, so it is not offered in the dropdown.
    - nag=2: both agents treat each other as "next" neighbour and their
      slices collapse to [0, 0] (algorithm ring logic, not Henosync).
    - Henosync does not send the neighbour inputs BilateralInteraction needs
      (nbr_id, nbr_AoR) - the sim must supply them (open question).
"""

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

        node_id = self._config.get("node_id", "")
        device = next((d for d in context.devices if d.id == node_id), None)
        if device is None:
            await self._fail(context, f"Device {node_id!r} not available")
            return

        # coverage_fns.Agents expects ang_bounds in radians normalised to [0, 2π),
        # running counter-clockwise from angle_1 to angle_2 (angle_2 < angle_1 = wraps through 0).
        # Whole circle: enter 0° and 359.9°, NOT 0° and 360° — 360° wraps to 0 and the
        # algorithm reads [0, 0] as a zero-width sector.
        angle_1 = radians(float(self._config.get("angle_1", 0.0))) % (2 * pi)
        angle_2 = radians(float(self._config.get("angle_2", 0.0))) % (2 * pi)
        radius = float(self._config.get("radius") or 0.0)
        if radius <= 0:
            await self._fail(context, f"Radius must be greater than 0 (got {radius})")
            return

        # Remaining coverage_fns.Agents constructor inputs, entered by the operator.
        ag_id = int(self._config.get("ag_id") or 0)
        nag = int(self._config.get("nag") or 0)
        envi_type = self._config.get("envi_type") or "Circular"
        if nag < 1 or not 1 <= ag_id <= nag:
            await self._fail(context, f"Agent ID must be between 1 and the number of agents (got ID {ag_id}, {nag} agents)")
            return

        result = await device.send_command("set_area", {
            "angle_1": angle_1,
            "angle_2": angle_2,
            "radius": radius,
            "ag_id": ag_id,
            "nag": nag,
            "envi_type": envi_type,
        })
        if not result.success:
            await self._fail(context, f"Sending area failed: {result.message}")
            return

        self._status_text = (
            f"Sent agent {ag_id}/{nag} ({envi_type}), angles ({angle_1:.4f}, {angle_2:.4f} rad), "
            f"radius {radius} to {device.name}"
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
                    "description": "Sector runs counter-clockwise from Angle 1 to Angle 2. For the whole circle enter 0 and 359.9 (not 360).",
                },
                "radius": {
                    "type": "number",
                    "label": "Radius (sim units, assumed metres)",
                    "required": True,
                    "default": 50,
                    "min": 0.01,
                    "description": "Size of the circular area in the sim. Units are assumed to be metres (AirSim/ROS convention) — unverified.",
                },
                "ag_id": {
                    "type": "number",
                    "label": "Agent ID (whole number, 1 to number of agents)",
                    "required": True,
                    "default": 1,
                    "min": 1,
                    "description": "This robot's position in the agent ring. Use 1 for single-robot testing.",
                },
                "nag": {
                    "type": "number",
                    "label": "Number of Agents (whole number, ≥ 1)",
                    "required": True,
                    "default": 1,
                    "min": 1,
                    "description": "Total robots sharing the area. Use 1 for single-robot testing.",
                },
                "envi_type": {
                    "type": "select",
                    "label": "Environment Type (shape of the mission area)",
                    "required": True,
                    "default": "Circular",
                    # RegularPolygons omitted: coverage_fns NbrAgents.update_info raises
                    # UnboundLocalError (A_self) for it after 10 interactions.
                    "options": [
                        {"label": "Circular", "value": "Circular"},
                    ],
                },
            },
        )
