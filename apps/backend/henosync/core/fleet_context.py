import asyncio
import logging
from typing import Optional, Any, TYPE_CHECKING
from ..models import (
    DeviceCategory, DeviceCapability,
    CapabilityRequirement, EventSeverity
)
from .device_proxy import DeviceProxy

if TYPE_CHECKING:
    from .zone_manager import ZoneManager
    from .event_bus import EventBus

logger = logging.getLogger(__name__)


class FleetContext:
    """
    Everything a control plugin needs to run an operation.

    Injected by the Operation Manager when a control plugin starts.
    Provides:
    - Matched devices as DeviceProxy objects
    - Dynamic device recruitment/release
    - Zone management
    - Inter-plugin messaging
    - Operator communication
    - Graceful degradation support
    """

    def __init__(
        self,
        plugin_id: str,
        initial_devices: list[DeviceProxy],
        zone_manager: "ZoneManager",
        event_bus: "EventBus"
    ):
        self._plugin_id = plugin_id
        self._devices: dict[str, DeviceProxy] = {
            d.id: d for d in initial_devices
        }
        self._zone_manager = zone_manager
        self._event_bus = event_bus

    # ── Device Access ──────────────────────────────────────────

    @property
    def devices(self) -> list[DeviceProxy]:
        """All devices currently assigned to this operation."""
        return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[DeviceProxy]:
        """Get a specific device by ID."""
        return self._devices.get(device_id)

    def get_devices_with_capability(
        self,
        capability: DeviceCapability
    ) -> list[DeviceProxy]:
        """Get all assigned devices that have a specific capability."""
        return [
            d for d in self._devices.values()
            if d.has_capability(capability)
        ]

    def get_devices_by_category(
        self,
        category: DeviceCategory
    ) -> list[DeviceProxy]:
        """Get all assigned devices of a specific category."""
        return [
            d for d in self._devices.values()
            if d.category == category
        ]

    # ── Dynamic Device Management ──────────────────────────────

    async def recruit_device(
        self,
        device_id: str
    ) -> Optional[DeviceProxy]:
        """
        Recruit an additional device into this operation.

        The operation manager checks if the device is available
        and not reserved by a higher-priority operation.

        Returns the DeviceProxy if successful, None if unavailable.
        """
        from .node_registry import node_registry
        from .operation_manager import operation_manager

        node = node_registry.get_node(device_id)
        if not node:
            logger.warning(f"Recruit failed — node not found: {device_id}")
            return None

        # Check if operation manager allows recruitment
        proxy = await operation_manager.try_recruit_device(
            self._plugin_id, device_id
        )
        if proxy:
            self._devices[device_id] = proxy
            logger.info(
                f"Plugin {self._plugin_id} recruited: {proxy.name}"
            )
        return proxy

    async def release_device(self, device_id: str) -> None:
        """
        Release a device back to the available pool.
        Call this when your algorithm no longer needs a device.
        """
        from .operation_manager import operation_manager

        if device_id in self._devices:
            del self._devices[device_id]
            await operation_manager.release_device(
                self._plugin_id, device_id
            )
            logger.info(
                f"Plugin {self._plugin_id} released device: {device_id}"
            )

    async def get_available_devices(
        self,
        capabilities: list[DeviceCapability] = [],
        categories: list[DeviceCategory] = []
    ) -> list[DeviceProxy]:
        """
        Query all available (unassigned) devices matching filters.

        Use this to find devices to recruit dynamically.
        Does not recruit them — call recruit_device() to assign.

        Args:
            capabilities: Filter by required capabilities
            categories:   Filter by device category
        """
        from .operation_manager import operation_manager
        from .node_registry import node_registry

        available = []
        for node in node_registry.get_online_nodes():
            # Skip if already assigned to this operation
            if node.id in self._devices:
                continue

            proxy = DeviceProxy(node)

            # Apply category filter
            if categories and proxy.category not in categories:
                continue

            # Apply capability filter
            if capabilities:
                if not all(
                    proxy.has_capability(cap)
                    for cap in capabilities
                ):
                    continue

            # Check if available (not reserved by higher priority op)
            if await operation_manager.is_device_available(node.id):
                available.append(proxy)

        return available

    # ── Zone Management ────────────────────────────────────────

    @property
    def zone_manager(self) -> "ZoneManager":
        """Access the zone manager for creating/querying zones."""
        return self._zone_manager

    # ── Inter-Plugin Communication ─────────────────────────────

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all other running control plugins."""
        await self._event_bus.broadcast(self._plugin_id, message)

    async def send_to_plugin(
        self,
        target_plugin_id: str,
        message: dict[str, Any]
    ) -> None:
        """Send a message to a specific control plugin."""
        await self._event_bus.send(
            self._plugin_id, target_plugin_id, message
        )

    # ── Operator Communication ─────────────────────────────────

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: EventSeverity = EventSeverity.INFO
    ) -> None:
        """Send an alert to the operator via the notification system."""
        from .telemetry_bus import telemetry_bus
        await telemetry_bus.publish_event(
            title=f"[{self._plugin_id}] {title}",
            message=message,
            severity=severity
        )

    async def request_operator_input(
        self,
        prompt: str,
        options: list[str]
    ) -> str:
        """
        Request input from the operator.
        Pauses until operator responds via the GUI.
        Returns the selected option string.
        """
        from .telemetry_bus import telemetry_bus
        await telemetry_bus.publish_event(
            title="Operator Input Required",
            message=f"[{self._plugin_id}] {prompt}",
            severity=EventSeverity.WARNING
        )
        # TODO Phase 5: implement proper operator input flow
        # For now return first option as default
        return options[0] if options else ""

    # ── Internal ───────────────────────────────────────────────

    def _add_device(self, proxy: DeviceProxy) -> None:
        """Called by operation manager when device joins."""
        self._devices[proxy.id] = proxy

    def _remove_device(self, device_id: str) -> None:
        """Called by operation manager when device leaves."""
        self._devices.pop(device_id, None)