"""
Henosync Control Plugin Template
==================================
Copy this folder, rename it, and implement the four methods below.

A control plugin defines an autonomous operation that coordinates
one or more devices. It never talks to hardware directly — all device
interaction goes through the DeviceProxy objects in context.devices.

Steps:
1. Update manifest.json with your operation's details
2. Rename MyOperationPlugin and set PLUGIN_ID to match manifest id
3. Declare REQUIRED_CAPABILITIES and SUPPORTED_CATEGORIES
4. Implement start() — your main operation loop
5. Implement stop() — signal start() to exit and clean up
6. Implement get_status() — return current state (no awaits)
7. Implement get_ui_contribution() — describe operator config fields
"""

import asyncio
import sys
import os
import logging
from typing import Any

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../apps/backend"))

from henosync.plugin_system.control_interfaces import (
    ControlPlugin, OperationStatus, OperationState, UIContribution,
)
from henosync.models import CapabilityRequirement, DeviceCategory, DeviceCapability

logger = logging.getLogger(__name__)


class MyOperationPlugin(ControlPlugin):
    """
    Replace MyOperationPlugin with your operation's name.
    Replace all TODO comments with your implementation.
    """

    PLUGIN_ID = "my-operation"        # must match manifest id
    PLUGIN_NAME = "My Operation"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Your Name"
    OPERATION_NAME = "My Operation"
    OPERATION_DESCRIPTION = "TODO: describe what this operation does"

    # Devices this operation requires. Empty = accepts any device.
    # Set required=True for mandatory capabilities, False for optional.
    REQUIRED_CAPABILITIES: list[CapabilityRequirement] = [
        # TODO: declare what your operation needs, e.g.:
        # CapabilityRequirement(capability=DeviceCapability.GPS, required=True),
    ]

    # Limit to specific robot categories. Empty = accepts any category.
    SUPPORTED_CATEGORIES: list[DeviceCategory] = [
        # TODO: e.g. DeviceCategory.AGV, DeviceCategory.DRONE
    ]

    # Higher = wins device conflicts against lower priority operations.
    PRIORITY: int = 0

    def __init__(self) -> None:
        super().__init__()
        # Internal status — updated by start(), read by get_status().
        self._state: OperationState = OperationState.IDLE
        self._status_text: str = ""

    async def start(self, context) -> None:
        """
        Main operation loop. Runs as a background task.
        Check self._stop_requested to know when to exit.
        Access operator config via self._config.
        Access matched devices via context.devices.
        """
        self._state = OperationState.RUNNING
        self._stop_requested = False

        # Read operator config set in get_ui_contribution()
        # example_param = self._config.get("example_param", "default")

        logger.info(
            "%s: started with %d device(s)",
            self.PLUGIN_ID, len(context.devices)
        )

        try:
            while not self._stop_requested:
                for device in context.devices:
                    # TODO: implement your operation logic here.
                    # Use device.move_to(), device.stop(), device.get_gps_data(), etc.
                    # Use context.send_alert() to notify the operator.
                    pass

                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            pass
        finally:
            self._state = OperationState.COMPLETED
            self._status_text = "Finished"
            logger.info("%s: stopped", self.PLUGIN_ID)

    async def stop(self) -> None:
        """
        Signal the operation to stop. Must complete within 3 seconds.
        Put devices in a safe state here if needed.
        """
        self._stop_requested = True
        self._state = OperationState.STOPPING

    def get_status(self) -> OperationStatus:
        """
        Return current status. Called frequently — must be non-blocking.
        Read from internal state updated by start(), never await here.
        """
        return OperationStatus(
            state=self._state,
            status_text=self._status_text,
        )

    def get_ui_contribution(self) -> UIContribution:
        """
        Describe what config fields the operator sets before starting.
        These appear in the Mission Planner step configuration panel.
        """
        return UIContribution(
            display_name=self.OPERATION_NAME,
            description=self.OPERATION_DESCRIPTION,
            icon="cpu",
            config_schema={
                # TODO: add operator config fields, e.g.:
                # "example_param": {
                #     "type": "string",
                #     "label": "Example Parameter",
                #     "required": False,
                #     "default": "value",
                # }
            },
        )

    # ── Optional event handlers ───────────────────────────────────

    async def on_device_joined(self, device) -> None:
        """Called when a new matching device comes online mid-operation."""
        logger.info("%s: device joined — %s", self.PLUGIN_ID, device.name)

    async def on_device_left(self, device) -> None:
        """
        Called when a device goes offline mid-operation.
        Adapt your algorithm here, or stop cleanly if you can't continue.
        """
        logger.warning("%s: device lost — %s", self.PLUGIN_ID, device.name)
        # Example: stop if no devices remain
        # if not context.devices:
        #     await self.stop()
