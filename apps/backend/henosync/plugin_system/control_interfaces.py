from abc import ABC, abstractmethod
from typing import Any, Optional, TYPE_CHECKING
from enum import Enum
from pydantic import BaseModel
from ..models import DeviceCategory, DeviceCapability, CapabilityRequirement

if TYPE_CHECKING:
    from ..core.fleet_context import FleetContext


class OperationState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPING = "stopping"


class OperationStatus(BaseModel):
    """
    Current status of a control plugin operation.
    Displayed in the Operations Monitor panel.
    """
    state: OperationState = OperationState.IDLE
    status_text: str = ""
    progress_percent: Optional[float] = None
    devices_active: list[str] = []     # device ids currently in use
    devices_available: list[str] = []  # device ids available to recruit
    data: dict[str, Any] = {}          # plugin-specific status data


class UIContribution(BaseModel):
    """
    Describes what UI elements this control plugin
    contributes to the core GUI panels.
    """
    # Parameters the operator sets before starting
    config_schema: dict[str, Any] = {}
    # Display name for the operations panel
    display_name: str = ""
    # Short description shown in the plugin panel
    description: str = ""
    # Icon name from Lucide icon set
    icon: str = "cpu"


class ControlPlugin(ABC):
    """
    Base class for all Henosync control plugins.

    A control plugin contains an autonomous algorithm that
    operates on one or more devices to accomplish a mission.

    Key principles:
    - Control plugins never talk to device plugins directly
    - All device interaction goes through DeviceProxy
    - All device selection goes through FleetContext
    - Operator can always stop any control plugin
    - Plugin must respond to stop() within 3 seconds

    To create a control plugin:
    1. Inherit from ControlPlugin
    2. Declare REQUIRED_CAPABILITIES and SUPPORTED_CATEGORIES
    3. Implement start(), stop(), get_status(), get_ui_contribution()
    4. Use context.devices to access matched devices
    5. Use context.fleet_manager to recruit additional devices
    """

    # ── Plugin Metadata ───────────────────────────────────────
    PLUGIN_ID: str = ""
    PLUGIN_NAME: str = ""
    PLUGIN_VERSION: str = "0.1.0"
    PLUGIN_AUTHOR: str = ""
    OPERATION_NAME: str = ""
    OPERATION_DESCRIPTION: str = ""

    # ── Device Matching ───────────────────────────────────────
    # What this plugin needs to run.
    # Empty REQUIRED_CAPABILITIES = works with any device.
    # Empty SUPPORTED_CATEGORIES = works with any category.
    REQUIRED_CAPABILITIES: list[CapabilityRequirement] = []
    SUPPORTED_CATEGORIES: list[DeviceCategory] = []

    # ── Priority ──────────────────────────────────────────────
    # Higher number = higher priority when competing for devices.
    # Safety operations should have highest priority.
    PRIORITY: int = 0

    # ── Required Methods ──────────────────────────────────────

    @abstractmethod
    async def start(self, context: "FleetContext") -> None:
        """
        Start the control operation.

        Called when operator launches this plugin.
        context provides matched devices and core services.

        This method runs as a background async task.
        It should loop until stop() is called.

        Args:
            context: FleetContext with devices and services

        Example:
            async def start(self, context):
                while not self._stop_requested:
                    for device in context.devices:
                        scan = await device.get_lidar_scan()
                        # process scan...
                    await asyncio.sleep(1.0)
        """

    @abstractmethod
    async def stop(self) -> None:
        """
        Stop the operation cleanly.

        MUST complete within 3 seconds.
        MUST be safe to call at any time, even if start()
        hasn't been called or has already finished.

        Send all devices to safe state here if needed.
        """

    @abstractmethod
    def get_status(self) -> OperationStatus:
        """
        Return current operation status.

        Called frequently by the Operations Monitor.
        MUST be fast and non-blocking — no awaits.
        Read from internal state updated by start().
        """

    @abstractmethod
    def get_ui_contribution(self) -> UIContribution:
        """
        Describe UI elements this plugin contributes.
        Called once when plugin is loaded.
        """

    # ── Optional Event Handlers ───────────────────────────────

    async def on_device_joined(self, device) -> None:
        """
        Called when a new matching device comes online
        while this operation is running.

        Override to dynamically recruit new devices.
        Default: ignore new devices.
        """

    async def on_device_left(self, device) -> None:
        """
        Called when a device goes offline mid-operation.
        This is the graceful degradation hook.

        Override to adapt algorithm to fewer devices.
        Default: log and continue without the device.

        If the operation cannot continue without this device,
        call self._context.send_alert() and stop cleanly.
        """

    async def on_message(
        self,
        sender_plugin_id: str,
        message: dict[str, Any]
    ) -> None:
        """
        Called when another control plugin sends a message.
        Override to handle inter-plugin communication.
        """

    async def on_operator_input(
        self,
        input_key: str,
        value: Any
    ) -> None:
        """
        Called when operator interacts with this plugin's
        UI elements during operation.
        """