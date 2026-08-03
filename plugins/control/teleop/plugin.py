"""
Teleop — manual arrow-key driving for a single ground vehicle.

Operator input arrives via ControlPlugin.on_operator_input(input_key, value):
    input_key: "up" | "down" | "left" | "right"
    value:     True on keydown, False on keyup

The main loop resends the current drive command at SEND_RATE_HZ so the
device always has a fresh command — if the operation is stopped, the very
last thing sent is always a zero-velocity stop.
"""

import asyncio
import logging

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

SEND_RATE_HZ = 5.0


class TeleopPlugin(ControlPlugin):
    PLUGIN_ID = "teleop"
    PLUGIN_NAME = "Teleop (Arrow Keys)"
    PLUGIN_VERSION = "0.1.0"
    PLUGIN_AUTHOR = "Henosync Team — Monash University"
    OPERATION_NAME = "Teleop"
    OPERATION_DESCRIPTION = "Manually drive a single ground vehicle with the arrow keys."

    REQUIRED_CAPABILITIES = [
        CapabilityRequirement(capability=DeviceCapability.MOVE_2D, required=True),
    ]
    SUPPORTED_CATEGORIES = [DeviceCategory.AGV]

    PRIORITY = 10  # operator manual control wins over autonomous operations

    def __init__(self):
        super().__init__()
        self._device = None
        self._pressed = {"up": False, "down": False, "left": False, "right": False}
        self._linear = 0.0
        self._angular = 0.0

    async def start(self, context) -> None:
        if not context.devices:
            self._stop_requested = True
            return

        self._device = context.devices[0]

        while not self._stop_requested:
            self._linear = (1.0 if self._pressed["up"] else 0.0) - (
                1.0 if self._pressed["down"] else 0.0
            )
            self._angular = (1.0 if self._pressed["right"] else 0.0) - (
                1.0 if self._pressed["left"] else 0.0
            )
            await self._device.send_command(
                "cmd_vel", {"linear": self._linear, "angular": self._angular}
            )
            await asyncio.sleep(1.0 / SEND_RATE_HZ)

    async def stop(self) -> None:
        self._stop_requested = True
        self._pressed = {"up": False, "down": False, "left": False, "right": False}
        self._linear = 0.0
        self._angular = 0.0
        if self._device:
            await self._device.send_command("cmd_vel", {"linear": 0.0, "angular": 0.0})

    def get_status(self) -> OperationStatus:
        if not self._device:
            return OperationStatus(
                state=OperationState.FAILED,
                status_text="No compatible device available",
            )
        return OperationStatus(
            state=OperationState.RUNNING,
            status_text=f"linear={self._linear:+.1f}  angular={self._angular:+.1f}",
            devices_active=[self._device.id],
        )

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution(
            display_name="Teleop (Arrow Keys)",
            description="Drive the assigned vehicle with the arrow keys.",
            icon="gamepad-2",
            config_schema={},
        )

    async def on_operator_input(self, input_key: str, value) -> None:
        if input_key in self._pressed:
            self._pressed[input_key] = bool(value)
