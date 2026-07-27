"""
Auto Navigate — autonomous navigation control plugin.

Executes a sequence of navigation steps against one or more devices.
Each step targets a map marker or zone and runs to completion before
the next step begins.

Step types
----------
MOVE_TO_MARKER   Navigate to a specific map marker position.
MOVE_TO_ZONE     Navigate to the centroid of a zone.
AREA_COVERAGE    Sweep a zone with a lawnmower pattern at a set spacing.
PERIMETER_PATROL Follow the boundary of a zone for a set number of laps.

TODO: implement each _execute_* method. The scaffolding, step sequencing,
stop handling, and status reporting are all in place.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from henosync_sdk import (
    CapabilityRequirement,
    ControlPlugin,
    DeviceCapability,
    DeviceCategory,
    OperationState,
    OperationStatus,
    UIContribution,
)

logger = logging.getLogger(__name__)


# ── Step types ─────────────────────────────────────────────────────────────────

class StepType(str, Enum):
    MOVE_TO_MARKER   = "move_to_marker"
    MOVE_TO_ZONE     = "move_to_zone"
    AREA_COVERAGE    = "area_coverage"
    PERIMETER_PATROL = "perimeter_patrol"


@dataclass
class NavigationStep:
    """One item in the operation's step sequence."""
    step_type: StepType

    # Target — set one depending on step type
    marker_id: Optional[str] = None   # MOVE_TO_MARKER
    zone_id:   Optional[str] = None   # MOVE_TO_ZONE, AREA_COVERAGE, PERIMETER_PATROL

    # Common parameters
    speed_ms: float = 1.0             # travel speed in m/s

    # AREA_COVERAGE parameters
    coverage_spacing_m: float = 5.0   # distance between sweep lanes in metres
    coverage_angle_deg: float = 0.0   # sweep direction (0 = east, 90 = north)

    # PERIMETER_PATROL parameters
    patrol_laps: int = 1              # number of times to loop the boundary


# ── Plugin ─────────────────────────────────────────────────────────────────────

class AutoNavigatePlugin(ControlPlugin):
    """
    Autonomous navigation control plugin.

    Reads a list of NavigationStep objects from self._config["steps"],
    executes them in sequence on each assigned device, then completes.
    """

    PLUGIN_ID           = "auto-navigate"
    PLUGIN_NAME         = "Auto Navigate"
    PLUGIN_VERSION      = "0.1.0"
    PLUGIN_AUTHOR       = "Henosync Team — Monash University"
    OPERATION_NAME      = "Auto Navigate"
    OPERATION_DESCRIPTION = "Sequential autonomous navigation: move, coverage, patrol"

    REQUIRED_CAPABILITIES: list[CapabilityRequirement] = [
        CapabilityRequirement(capability=DeviceCapability.GPS, required=True),
        CapabilityRequirement(capability=DeviceCapability.MOVE_2D, required=True),
    ]

    SUPPORTED_CATEGORIES: list[DeviceCategory] = [
        DeviceCategory.AGV,
        DeviceCategory.DRONE,
    ]

    PRIORITY: int = 10

    def __init__(self) -> None:
        super().__init__()
        self._state: OperationState = OperationState.IDLE
        self._status_text: str = ""
        self._current_step: int = 0
        self._total_steps: int = 0

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    async def start(self, context) -> None:
        self._state = OperationState.RUNNING
        self._current_step = 0

        steps = self._parse_steps()
        self._total_steps = len(steps)

        if not steps:
            self._status_text = "No steps configured"
            self._state = OperationState.COMPLETED
            return

        if not context.devices:
            self._status_text = "No devices assigned"
            self._state = OperationState.COMPLETED
            return

        logger.info(
            "%s: starting %d step(s) on %d device(s)",
            self.PLUGIN_ID, len(steps), len(context.devices)
        )

        try:
            for i, step in enumerate(steps):
                if self._stop_requested:
                    break

                self._current_step = i + 1
                self._status_text = (
                    f"Step {self._current_step}/{self._total_steps} — "
                    f"{step.step_type.value}"
                )
                logger.info("%s: %s", self.PLUGIN_ID, self._status_text)

                for device in context.devices:
                    if self._stop_requested:
                        break
                    await self._execute_step(step, device, context)

        except asyncio.CancelledError:
            pass
        finally:
            self._state = OperationState.COMPLETED
            self._status_text = (
                "Stopped" if self._stop_requested else "Complete"
            )
            logger.info("%s: %s", self.PLUGIN_ID, self._status_text)

    async def stop(self) -> None:
        self._stop_requested = True
        self._state = OperationState.STOPPING

    def get_status(self) -> OperationStatus:
        return OperationStatus(
            state=self._state,
            status_text=self._status_text,
            progress=(
                self._current_step / self._total_steps
                if self._total_steps > 0 else 0.0
            ),
        )

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution(
            display_name=self.OPERATION_NAME,
            description=self.OPERATION_DESCRIPTION,
            icon="navigation",
            config_schema={
                "step_type": {
                    "type": "select",
                    "label": "Step Type",
                    "required": True,
                    "options": [
                        {"label": "Move to Marker",   "value": StepType.MOVE_TO_MARKER},
                        {"label": "Move to Zone",     "value": StepType.MOVE_TO_ZONE},
                        {"label": "Area Coverage",    "value": StepType.AREA_COVERAGE},
                        {"label": "Perimeter Patrol", "value": StepType.PERIMETER_PATROL},
                    ],
                },
                "target_id": {
                    "type": "string",
                    "label": "Marker or Zone ID",
                    "required": True,
                    "placeholder": "From the map panel",
                },
                "speed_ms": {
                    "type": "number",
                    "label": "Speed (m/s)",
                    "required": False,
                    "default": 1.0,
                    "min": 0.1,
                    "max": 10.0,
                },
                "coverage_spacing_m": {
                    "type": "number",
                    "label": "Coverage Spacing (m)",
                    "required": False,
                    "default": 5.0,
                    "description": "Distance between sweep lanes — Area Coverage only",
                },
                "patrol_laps": {
                    "type": "number",
                    "label": "Patrol Laps",
                    "required": False,
                    "default": 1,
                    "description": "Number of boundary loops — Perimeter Patrol only",
                },
            },
        )

    async def on_device_joined(self, device) -> None:
        logger.info("%s: device joined — %s", self.PLUGIN_ID, device.name)

    async def on_device_left(self, device) -> None:
        logger.warning("%s: device lost — %s", self.PLUGIN_ID, device.name)
        await self.stop()

    # ── Step dispatch ──────────────────────────────────────────────────────────

    async def _execute_step(self, step: NavigationStep, device, context) -> None:
        if step.step_type == StepType.MOVE_TO_MARKER:
            await self._execute_move_to_marker(step, device, context)
        elif step.step_type == StepType.MOVE_TO_ZONE:
            await self._execute_move_to_zone(step, device, context)
        elif step.step_type == StepType.AREA_COVERAGE:
            await self._execute_area_coverage(step, device, context)
        elif step.step_type == StepType.PERIMETER_PATROL:
            await self._execute_perimeter_patrol(step, device, context)

    async def _execute_move_to_marker(self, step: NavigationStep, device, context) -> None:
        """
        Navigate to the GPS position of a map marker.

        TODO:
        - Look up marker by step.marker_id via context.zone_manager or marker API
        - Call device.move_to(lat, lon) and await completion
        - Handle device.is_at_destination() or a timeout
        """
        logger.info(
            "%s: MOVE_TO_MARKER — marker=%s speed=%.1f m/s",
            self.PLUGIN_ID, step.marker_id, step.speed_ms
        )
        # TODO: implement
        await asyncio.sleep(0)

    async def _execute_move_to_zone(self, step: NavigationStep, device, context) -> None:
        """
        Navigate to the centroid of a zone.

        TODO:
        - Look up zone by step.zone_id via context.zone_manager
        - Compute zone centroid (average of polygon vertices or circle centre)
        - Call device.move_to(lat, lon) and await completion
        """
        logger.info(
            "%s: MOVE_TO_ZONE — zone=%s speed=%.1f m/s",
            self.PLUGIN_ID, step.zone_id, step.speed_ms
        )
        # TODO: implement
        await asyncio.sleep(0)

    async def _execute_area_coverage(self, step: NavigationStep, device, context) -> None:
        """
        Sweep a zone with a lawnmower (boustrophedon) pattern.

        TODO:
        - Look up zone polygon via context.zone_manager
        - Generate parallel sweep lines across the polygon at step.coverage_spacing_m
          in the direction of step.coverage_angle_deg
        - Clip lines to polygon boundary
        - Send device.move_to() for each waypoint in the sweep path
        - Check self._stop_requested between waypoints
        """
        logger.info(
            "%s: AREA_COVERAGE — zone=%s spacing=%.1f m angle=%.0f°",
            self.PLUGIN_ID, step.zone_id, step.coverage_spacing_m, step.coverage_angle_deg
        )
        # TODO: implement
        await asyncio.sleep(0)

    async def _execute_perimeter_patrol(self, step: NavigationStep, device, context) -> None:
        """
        Follow the boundary of a zone for a set number of laps.

        TODO:
        - Look up zone polygon via context.zone_manager
        - Extract ordered boundary vertices
        - For each lap: send device.move_to() for each vertex in sequence
        - Check self._stop_requested between waypoints
        """
        logger.info(
            "%s: PERIMETER_PATROL — zone=%s laps=%d speed=%.1f m/s",
            self.PLUGIN_ID, step.zone_id, step.patrol_laps, step.speed_ms
        )
        # TODO: implement
        await asyncio.sleep(0)

    # ── Config parsing ─────────────────────────────────────────────────────────

    def _parse_steps(self) -> list[NavigationStep]:
        """
        Build the step list from operator config.

        Currently reads a single step from self._config.
        TODO: extend to support a list of steps when the UI supports it.
        """
        cfg = self._config or {}
        raw_type = cfg.get("step_type")
        if not raw_type:
            return []

        try:
            step_type = StepType(raw_type)
        except ValueError:
            logger.error("%s: unknown step_type %r", self.PLUGIN_ID, raw_type)
            return []

        target_id = cfg.get("target_id", "")
        step = NavigationStep(
            step_type=step_type,
            speed_ms=float(cfg.get("speed_ms", 1.0)),
            coverage_spacing_m=float(cfg.get("coverage_spacing_m", 5.0)),
            patrol_laps=int(cfg.get("patrol_laps", 1)),
        )

        if step_type == StepType.MOVE_TO_MARKER:
            step.marker_id = target_id
        else:
            step.zone_id = target_id

        return [step]
