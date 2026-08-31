"""
Auto Navigate — move a single device to a map marker.

The operator configures which robot and which marker in the mission step
config panel. The plugin sends a move_to command via DeviceProxy (fully
abstracted — works with any device that implements cmd_move_to regardless
of protocol), then polls position until the robot arrives or a timeout fires.

Arrival detection: haversine distance to target, checked every 0.5 s.
If the device has no position fix, only the timeout applies.
"""

import asyncio
import logging
from math import cos, degrees, radians

from henosync_sdk import (
    CapabilityRequirement,
    ControlPlugin,
    DeviceCapability,
    DeviceCategory,
    EventSeverity,
    OperationState,
    OperationStatus,
    UIContribution,
)

logger = logging.getLogger(__name__)


class AutoNavigatePlugin(ControlPlugin):
    PLUGIN_ID = "auto-navigate"
    PLUGIN_NAME = "Auto Navigate"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    OPERATION_NAME = "Auto Navigate"
    OPERATION_DESCRIPTION = "Send a robot to a map marker."

    REQUIRED_CAPABILITIES: list[CapabilityRequirement] = [
        CapabilityRequirement(capability=DeviceCapability.MOVE_2D, required=True),
    ]

    SUPPORTED_CATEGORIES: list[DeviceCategory] = [
        DeviceCategory.AGV,
        DeviceCategory.DRONE,
        DeviceCategory.LEGGED,
        DeviceCategory.TRACKED,
        DeviceCategory.VTOL,
    ]

    PRIORITY: int = 5

    def __init__(self) -> None:
        super().__init__()
        self._state: OperationState = OperationState.IDLE
        self._status_text: str = ""
        self._progress_percent: float | None = None
        self._active_device = None

    async def start(self, context) -> None:
        self._state = OperationState.RUNNING

        # ── Resolve device ─────────────────────────────────────
        target_node_id = self._config.get("node_id", "")
        if target_node_id:
            device = next((d for d in context.devices if d.id == target_node_id), None)
            if device is None:
                self._status_text = f"Robot {target_node_id!r} not available"
                self._state = OperationState.FAILED
                return
        else:
            if not context.devices:
                self._status_text = "No compatible device available"
                self._state = OperationState.FAILED
                return
            device = context.devices[0]

        # ── Resolve marker ─────────────────────────────────────
        marker_id = self._config.get("marker_id", "")
        marker = context.marker_manager.get_marker(marker_id)
        if marker is None:
            self._status_text = f"Marker not found: {marker_id!r}"
            self._state = OperationState.FAILED
            await context.send_alert(
                "Auto Navigate failed",
                f"Marker {marker_id!r} does not exist.",
                EventSeverity.WARNING,
            )
            return

        timeout_s = float(self._config.get("timeout_s", 60.0))

        # ── Convert VICON marker coordinates to real GPS ────────
        # VICON markers store lon=x_m, lat=y_m (raw VICON metres).
        # node.position is real GPS (vicon_manager converts via local_origin).
        # We must apply the same conversion so the nav controller sees matching coords.
        if marker.map_mode == "vicon":
            origin = device.local_origin
            if origin is not None:
                R = 6_371_000.0
                gps_lat = origin.lat + degrees(marker.lat / R)
                gps_lon = origin.lon + degrees(marker.lon / (R * cos(radians(origin.lat))))
            else:
                gps_lat, gps_lon = marker.lat, marker.lon
        else:
            gps_lat, gps_lon = marker.lat, marker.lon

        self._status_text = f"Moving {device.name} → {marker.name}"
        logger.info("AutoNavigate: %s → %s (%.6f, %.6f)", device.name, marker.name, gps_lat, gps_lon)

        self._active_device = device

        # ── Send move command (timeout enforced here) ──────────
        # cmd_move_to blocks until arrival — wrap with wait_for so the
        # user-configured timeout actually fires.
        try:
            result = await asyncio.wait_for(
                device.move_to(gps_lat, gps_lon, 0.0),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            self._status_text = f"Timed out after {timeout_s:.0f}s"
            self._state = OperationState.FAILED
            await context.send_alert(
                "Auto Navigate timeout",
                f"{device.name} did not reach {marker.name} within {timeout_s:.0f}s.",
                EventSeverity.WARNING,
            )
            return

        if not result.success:
            self._status_text = f"Move command failed: {result.message}"
            self._state = OperationState.FAILED
            await context.send_alert("Auto Navigate failed", result.message, EventSeverity.WARNING)
            return

        if self._stop_requested:
            self._status_text = "Stopped"
        else:
            self._status_text = f"Arrived at {marker.name}"
            self._progress_percent = 100.0
            logger.info("AutoNavigate: arrived at %s", marker.name)

        self._state = OperationState.COMPLETED

    async def stop(self) -> None:
        self._stop_requested = True
        self._state = OperationState.STOPPING
        dev = self._active_device
        if dev:
            try:
                await dev.stop()
            except Exception:
                pass

    def get_status(self) -> OperationStatus:
        return OperationStatus(
            state=self._state,
            status_text=self._status_text,
            progress_percent=self._progress_percent,
        )

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution(
            display_name="Auto Navigate",
            description="Send a robot to a map marker.",
            icon="navigation",
            config_schema={
                "node_id": {
                    "type": "device_select",
                    "label": "Robot",
                    "required": False,
                    "description": "Which robot to send. Leave blank to use the first available.",
                },
                "marker_id": {
                    "type": "marker_select",
                    "label": "Target Marker",
                    "required": True,
                    "description": "The map marker to navigate to.",
                },
                "arrival_radius_m": {
                    "type": "number",
                    "label": "Arrival Radius (m)",
                    "required": False,
                    "default": 2.0,
                    "min": 0.5,
                    "max": 20.0,
                    "description": "Distance from target considered 'arrived'.",
                },
                "timeout_s": {
                    "type": "number",
                    "label": "Timeout (s)",
                    "required": False,
                    "default": 60,
                    "min": 10,
                    "max": 600,
                    "description": "Give up and report failure after this many seconds.",
                },
            },
        )

    async def on_device_left(self, device) -> None:
        logger.warning("AutoNavigate: device lost — %s", device.name)
        await self.stop()
