"""
Area Patrol — dummy control plugin
====================================
Demonstrates all config field types (string, number, boolean, select)
and the full ControlPlugin lifecycle. Does not move real hardware.
"""

import asyncio
import sys
import os
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from henosync.plugin_system.control_interfaces import (
    ControlPlugin,
    OperationStatus,
    OperationState,
    UIContribution,
)
from henosync.models import DeviceCapability, DeviceCategory, CapabilityRequirement


class AreaPatrolPlugin(ControlPlugin):
    """
    Dummy Area Patrol control plugin.

    Simulates patrolling a defined area with progress updates.
    Use this to test the Plugins page config form and operation lifecycle.
    """

    PLUGIN_ID = "area-patrol"
    PLUGIN_NAME = "Area Patrol"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    OPERATION_NAME = "Area Patrol"
    OPERATION_DESCRIPTION = (
        "Autonomously patrols a defined area using available fleet devices"
    )

    REQUIRED_CAPABILITIES = [
        CapabilityRequirement(capability=DeviceCapability.MOVE_2D, required=True),
        CapabilityRequirement(capability=DeviceCapability.GPS, required=True),
    ]
    SUPPORTED_CATEGORIES = [
        DeviceCategory.AGV,
        DeviceCategory.DRONE,
    ]
    PRIORITY = 5

    def __init__(self):
        self._stop_requested = False
        self._status = OperationStatus()

    # ── Required methods ───────────────────────────────────────────────────────

    async def start(self, context: Any) -> None:
        self._stop_requested = False

        device_ids = [d.id for d in context.devices]
        self._status = OperationStatus(
            state=OperationState.RUNNING,
            status_text="Initialising patrol route…",
            progress_percent=0.0,
            devices_active=device_ids,
        )

        phases = [
            (0,   "Initialising patrol route"),
            (10,  "Devices moving to start position"),
            (25,  "Scanning sector A"),
            (40,  "Scanning sector B"),
            (55,  "Scanning sector C"),
            (70,  "Scanning sector D"),
            (85,  "Completing final sweep"),
            (100, "Patrol complete"),
        ]

        for progress, label in phases:
            if self._stop_requested:
                break
            self._status = OperationStatus(
                state=OperationState.RUNNING,
                status_text=label,
                progress_percent=float(progress),
                devices_active=device_ids,
            )
            await asyncio.sleep(2.5)

        if not self._stop_requested:
            self._status = OperationStatus(
                state=OperationState.COMPLETED,
                status_text="Patrol completed successfully",
                progress_percent=100.0,
            )

    async def stop(self) -> None:
        self._stop_requested = True
        self._status = OperationStatus(
            state=OperationState.STOPPING,
            status_text="Stopping patrol — returning devices to safe state…",
            progress_percent=self._status.progress_percent,
        )

    def get_status(self) -> OperationStatus:
        return self._status

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution(
            display_name="Area Patrol",
            description=(
                "Autonomously patrols a defined area using available fleet devices"
            ),
            icon="map-pin",
            config_schema={
                # ── String field ──────────────────────────────────────────────
                "patrol_name": {
                    "type": "string",
                    "label": "Patrol Name",
                    "required": True,
                    "placeholder": "e.g. North Perimeter Patrol",
                    "description": (
                        "A label for this patrol run, used in logs and alerts."
                    ),
                },
                # ── Select field ──────────────────────────────────────────────
                "search_pattern": {
                    "type": "select",
                    "label": "Search Pattern",
                    "required": True,
                    "default": "grid",
                    "description": (
                        "Movement pattern used to cover the patrol area."
                    ),
                    "options": [
                        {"label": "Grid (row-by-row)", "value": "grid"},
                        {"label": "Spiral (centre-out)", "value": "spiral"},
                        {"label": "Lawnmower", "value": "lawnmower"},
                        {"label": "Random walk", "value": "random"},
                    ],
                },
                # ── Number field ──────────────────────────────────────────────
                "speed_limit_ms": {
                    "type": "number",
                    "label": "Speed Limit (m/s)",
                    "required": False,
                    "default": 2.0,
                    "min": 0.1,
                    "max": 10.0,
                    "description": "Maximum device speed during patrol.",
                },
                # ── Number field ──────────────────────────────────────────────
                "scan_overlap_pct": {
                    "type": "number",
                    "label": "Scan Overlap (%)",
                    "required": False,
                    "default": 20,
                    "min": 0,
                    "max": 80,
                    "description": (
                        "Percentage overlap between adjacent passes "
                        "to ensure complete coverage."
                    ),
                },
                # ── Boolean field ─────────────────────────────────────────────
                "return_to_base": {
                    "type": "boolean",
                    "label": "Return to Base on Completion",
                    "default": True,
                    "description": (
                        "Send all devices back to their home position "
                        "when the patrol finishes."
                    ),
                },
                # ── Boolean field ─────────────────────────────────────────────
                "loop_indefinitely": {
                    "type": "boolean",
                    "label": "Loop Indefinitely",
                    "default": False,
                    "description": (
                        "Repeat the patrol continuously until manually stopped."
                    ),
                },
                # ── Boolean field ─────────────────────────────────────────────
                "alert_on_complete": {
                    "type": "boolean",
                    "label": "Alert on Completion",
                    "default": True,
                    "description": (
                        "Send an operator notification when the patrol finishes."
                    ),
                },
            },
        )

    # ── Optional event handlers ────────────────────────────────────────────────

    async def on_device_left(self, device: Any) -> None:
        """Adapt gracefully if a device goes offline mid-patrol."""
        if device:
            self._status = OperationStatus(
                state=OperationState.RUNNING,
                status_text=f"Device lost: {device.name} — continuing with remaining devices",
                progress_percent=self._status.progress_percent,
            )