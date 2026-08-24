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
import math

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

POLL_INTERVAL_S = 0.5


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(min(1.0, a)))


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

        arrival_radius_m = float(self._config.get("arrival_radius_m", 2.0))
        timeout_s = float(self._config.get("timeout_s", 60.0))

        self._status_text = f"Moving {device.name} → {marker.name}"
        logger.info("AutoNavigate: %s → %s (%.6f, %.6f)", device.name, marker.name, marker.lat, marker.lon)

        # ── Send move command ──────────────────────────────────
        result = await device.move_to(marker.lat, marker.lon, 0.0)
        if not result.success:
            self._status_text = f"Move command failed: {result.message}"
            self._state = OperationState.FAILED
            await context.send_alert("Auto Navigate failed", result.message, EventSeverity.WARNING)
            return

        # ── Wait for arrival ───────────────────────────────────
        elapsed = 0.0
        initial_dist: float | None = None

        while not self._stop_requested:
            pos = device.position
            if pos and pos.lat != 0.0:
                dist = _haversine_m(pos.lat, pos.lon, marker.lat, marker.lon)
                if initial_dist is None:
                    initial_dist = dist or 1.0
                self._progress_percent = max(0.0, min(100.0, (1.0 - dist / initial_dist) * 100))
                self._status_text = f"Moving to {marker.name} — {dist:.1f} m remaining"

                if dist <= arrival_radius_m:
                    break
            else:
                self._status_text = f"Moving to {marker.name} — waiting for position fix"

            await asyncio.sleep(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S

            if elapsed >= timeout_s:
                self._status_text = f"Timed out after {timeout_s:.0f}s"
                self._state = OperationState.FAILED
                await context.send_alert(
                    "Auto Navigate timeout",
                    f"{device.name} did not reach {marker.name} within {timeout_s:.0f}s.",
                    EventSeverity.WARNING,
                )
                return

        if self._stop_requested:
            await device.stop()
            self._status_text = "Stopped"
        else:
            self._status_text = f"Arrived at {marker.name}"
            self._progress_percent = 100.0
            logger.info("AutoNavigate: arrived at %s", marker.name)

        self._state = OperationState.COMPLETED

    async def stop(self) -> None:
        self._stop_requested = True
        self._state = OperationState.STOPPING

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
