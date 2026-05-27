from abc import ABC, abstractmethod
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from pydantic import BaseModel

from .models import CapabilityRequirement, DeviceCategory

if TYPE_CHECKING:
    from .fleet_context import FleetContext


class OperationState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPING = "stopping"


class OperationStatus(BaseModel):
    state: OperationState = OperationState.IDLE
    status_text: str = ""
    progress_percent: Optional[float] = None
    devices_active: list[str] = []
    devices_available: list[str] = []
    data: dict[str, Any] = {}


class UIContribution(BaseModel):
    config_schema: dict[str, Any] = {}
    display_name: str = ""
    description: str = ""
    icon: str = "cpu"


class ControlPlugin(ABC):
    """
    Base class for all Henosync control plugins.

    A control plugin defines an autonomous operation that coordinates
    one or more devices. It never touches hardware directly — all
    device interaction goes through DeviceProxy via FleetContext.

    Key rules:
    - Never call NodePlugin or plugin_registry directly
    - Always interact with devices via context.devices (DeviceProxy)
    - stop() must complete within 3 seconds
    - get_status() must be non-blocking (no awaits)
    """

    PLUGIN_ID: str = ""
    PLUGIN_NAME: str = ""
    PLUGIN_VERSION: str = "0.1.0"
    PLUGIN_AUTHOR: str = ""
    OPERATION_NAME: str = ""
    OPERATION_DESCRIPTION: str = ""

    REQUIRED_CAPABILITIES: list[CapabilityRequirement] = []
    SUPPORTED_CATEGORIES: list[DeviceCategory] = []

    # Higher = wins device conflicts against lower priority operations.
    PRIORITY: int = 0

    def __init__(self) -> None:
        # Set True by stop() to signal start() to exit its loop.
        self._stop_requested: bool = False
        # Operator config injected by operation_manager before start().
        self._config: dict[str, Any] = {}
        # FleetContext injected by operation_manager before start().
        self._context: Optional["FleetContext"] = None

    @abstractmethod
    async def start(self, context: "FleetContext") -> None:
        """
        Main operation loop. Runs as a background asyncio.Task.
        Loop on self._stop_requested. Read config via self._config.
        """

    @abstractmethod
    async def stop(self) -> None:
        """Stop cleanly. Must complete within 3 seconds."""

    @abstractmethod
    def get_status(self) -> OperationStatus:
        """Return current status. Must be non-blocking — no awaits."""

    @abstractmethod
    def get_ui_contribution(self) -> UIContribution:
        """Describe operator config fields. Called once at plugin load."""

    # ── Optional Event Handlers ───────────────────────────────────────────────

    async def on_device_joined(self, device: Any) -> None:
        """Called when a new matching device comes online mid-operation."""

    async def on_device_left(self, device: Any) -> None:
        """
        Called when a device goes offline mid-operation.
        Adapt algorithm or stop cleanly if unable to continue.
        """

    async def on_message(self, sender_plugin_id: str, message: dict[str, Any]) -> None:
        """Called when another control plugin sends a message."""

    async def on_operator_input(self, input_key: str, value: Any) -> None:
        """Called when operator interacts with this plugin's UI elements."""
