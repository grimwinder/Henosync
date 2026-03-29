import asyncio
import logging
from typing import Optional, Any
from datetime import datetime, timezone
from ..models import (
    DeviceCategory, DeviceCapability,
    CapabilityRequirement, EventSeverity
)
from ..plugin_system.control_interfaces import (
    ControlPlugin, OperationState, OperationStatus
)
from .device_proxy import DeviceProxy
from .fleet_context import FleetContext
from .zone_manager import zone_manager
from .event_bus import event_bus
from .telemetry_bus import telemetry_bus

logger = logging.getLogger(__name__)


class ActiveOperation:
    """Tracks a running control plugin operation."""

    def __init__(
        self,
        plugin: ControlPlugin,
        context: FleetContext,
        task: asyncio.Task
    ):
        self.plugin = plugin
        self.context = context
        self.task = task
        self.started_at = datetime.now(timezone.utc)
        self.plugin_id = plugin.PLUGIN_ID


class OperationManager:
    """
    Manages all running control plugin operations.

    Responsibilities:
    - Start and stop control plugin operations
    - Match devices to control plugins by capability
    - Handle operation priority and device conflicts
    - Graceful degradation when devices go offline
    - Device recruitment and release
    - Emergency stop all operations
    """

    def __init__(self):
        # plugin_id -> ActiveOperation
        self._operations: dict[str, ActiveOperation] = {}
        # device_id -> plugin_id (which operation owns it)
        self._device_assignments: dict[str, str] = {}
        # plugin_id -> ControlPlugin class
        self._registered_plugins: dict[str, type[ControlPlugin]] = {}

    # ── Plugin Registration ────────────────────────────────────

    def register_control_plugin(
        self,
        plugin_class: type[ControlPlugin]
    ) -> None:
        """Register a control plugin class."""
        self._registered_plugins[plugin_class.PLUGIN_ID] = plugin_class
        logger.info(
            f"Control plugin registered: {plugin_class.PLUGIN_ID}"
        )

    def get_registered_plugins(self) -> list[dict]:
        """Get all registered control plugins with metadata."""
        result = []
        for plugin_id, cls in self._registered_plugins.items():
            instance = cls()
            ui = instance.get_ui_contribution()
            result.append({
                "id": plugin_id,
                "name": cls.PLUGIN_NAME,
                "version": cls.PLUGIN_VERSION,
                "author": cls.PLUGIN_AUTHOR,
                "operation_name": cls.OPERATION_NAME,
                "description": cls.OPERATION_DESCRIPTION,
                "required_capabilities": [
                    r.capability for r in cls.REQUIRED_CAPABILITIES
                ],
                "supported_categories": cls.SUPPORTED_CATEGORIES,
                "priority": cls.PRIORITY,
                "ui": ui.model_dump()
            })
        return result

    # ── Operation Lifecycle ────────────────────────────────────

    async def start_operation(
        self,
        plugin_id: str,
        config: dict[str, Any] = {}
    ) -> tuple[bool, str]:
        """
        Start a control plugin operation.

        Returns (success, message).
        """
        if plugin_id in self._operations:
            return False, f"Operation already running: {plugin_id}"

        plugin_class = self._registered_plugins.get(plugin_id)
        if not plugin_class:
            return False, f"Control plugin not found: {plugin_id}"

        # Match devices to this plugin
        matched_devices = await self._match_devices(plugin_class)

        if not matched_devices and plugin_class.REQUIRED_CAPABILITIES:
            return False, (
                f"No devices available matching requirements for "
                f"{plugin_class.PLUGIN_NAME}"
            )

        # Create plugin instance
        plugin_instance = plugin_class()

        # Register with event bus
        event_bus.register_plugin(
            plugin_id,
            plugin_instance.on_message
        )

        # Create fleet context
        context = FleetContext(
            plugin_id=plugin_id,
            initial_devices=matched_devices,
            zone_manager=zone_manager,
            event_bus=event_bus
        )

        # Assign devices to this operation
        for device in matched_devices:
            self._device_assignments[device.id] = plugin_id

        # Start operation as background task
        task = asyncio.create_task(
            self._run_operation(plugin_instance, context, config)
        )

        self._operations[plugin_id] = ActiveOperation(
            plugin_instance, context, task
        )

        device_names = [d.name for d in matched_devices]
        await telemetry_bus.publish_event(
            title="Operation Started",
            message=(
                f"{plugin_class.OPERATION_NAME} started "
                f"with {len(matched_devices)} device(s): "
                f"{', '.join(device_names)}"
            ),
            severity=EventSeverity.INFO
        )

        logger.info(
            f"Operation started: {plugin_id} "
            f"with {len(matched_devices)} devices"
        )
        return True, "Operation started"

    async def stop_operation(
        self,
        plugin_id: str
    ) -> tuple[bool, str]:
        """Stop a running operation."""
        operation = self._operations.get(plugin_id)
        if not operation:
            return False, f"No running operation: {plugin_id}"

        logger.info(f"Stopping operation: {plugin_id}")

        # Give plugin 3 seconds to stop cleanly
        try:
            await asyncio.wait_for(
                operation.plugin.stop(),
                timeout=3.0
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Operation {plugin_id} did not stop within 3s — forcing"
            )

        # Cancel the task
        if not operation.task.done():
            operation.task.cancel()
            try:
                await operation.task
            except asyncio.CancelledError:
                pass

        # Release all devices
        for device_id, assigned_plugin in list(
            self._device_assignments.items()
        ):
            if assigned_plugin == plugin_id:
                del self._device_assignments[device_id]

        # Unregister from event bus
        event_bus.unregister_plugin(plugin_id)

        del self._operations[plugin_id]

        await telemetry_bus.publish_event(
            title="Operation Stopped",
            message=f"{operation.plugin.OPERATION_NAME} stopped",
            severity=EventSeverity.INFO
        )

        return True, "Operation stopped"

    async def stop_all_operations(self) -> None:
        """Stop all running operations. Called by emergency stop."""
        logger.critical("Stopping all control plugin operations")
        for plugin_id in list(self._operations.keys()):
            await self.stop_operation(plugin_id)

    async def _run_operation(
        self,
        plugin: ControlPlugin,
        context: FleetContext,
        config: dict
    ) -> None:
        """Run a control plugin operation with error handling."""
        try:
            await plugin.start(context)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(
                f"Operation {plugin.PLUGIN_ID} failed: {e}"
            )
            await telemetry_bus.publish_event(
                title="Operation Failed",
                message=f"{plugin.OPERATION_NAME} failed: {e}",
                severity=EventSeverity.CRITICAL
            )

    # ── Status ─────────────────────────────────────────────────

    def get_all_operation_statuses(self) -> list[dict]:
        """Get status of all running operations."""
        statuses = []
        for plugin_id, operation in self._operations.items():
            try:
                status = operation.plugin.get_status()
                statuses.append({
                    "plugin_id": plugin_id,
                    "operation_name": operation.plugin.OPERATION_NAME,
                    "started_at": operation.started_at.isoformat(),
                    "status": status.model_dump()
                })
            except Exception as e:
                logger.error(f"Status error for {plugin_id}: {e}")
        return statuses

    # ── Device Management ──────────────────────────────────────

    async def _match_devices(
        self,
        plugin_class: type[ControlPlugin]
    ) -> list[DeviceProxy]:
        """
        Find all available devices matching plugin requirements.
        Applies capability negotiation.
        """
        from .node_registry import node_registry

        matched = []
        for node in node_registry.get_online_nodes():
            proxy = DeviceProxy(node)

            # Category filter
            if (
                plugin_class.SUPPORTED_CATEGORIES and
                proxy.category not in plugin_class.SUPPORTED_CATEGORIES
            ):
                continue

            # Capability negotiation
            all_met = True
            for req in plugin_class.REQUIRED_CAPABILITIES:
                if req.required and not proxy.meets_requirement(req):
                    all_met = False
                    break

            if not all_met:
                continue

            # Check not already assigned to higher priority op
            if await self._can_assign_device(
                node.id, plugin_class.PRIORITY
            ):
                matched.append(proxy)

        return matched

    async def _can_assign_device(
        self,
        device_id: str,
        requesting_priority: int
    ) -> bool:
        """
        Check if a device can be assigned to an operation.
        Higher priority operations win device conflicts.
        """
        current_plugin_id = self._device_assignments.get(device_id)
        if not current_plugin_id:
            return True

        # Check priority of current owner
        current_op = self._operations.get(current_plugin_id)
        if not current_op:
            return True

        current_priority = current_op.plugin.PRIORITY
        return requesting_priority > current_priority

    async def try_recruit_device(
        self,
        requesting_plugin_id: str,
        device_id: str
    ) -> Optional[DeviceProxy]:
        """
        Try to recruit a device for an operation.
        Called by FleetContext.recruit_device().
        """
        from .node_registry import node_registry

        requesting_op = self._operations.get(requesting_plugin_id)
        if not requesting_op:
            return None

        requesting_priority = requesting_op.plugin.PRIORITY

        if not await self._can_assign_device(
            device_id, requesting_priority
        ):
            logger.warning(
                f"Device {device_id} unavailable — "
                f"held by higher priority operation"
            )
            return None

        # Preempt lower priority operation if needed
        current_plugin_id = self._device_assignments.get(device_id)
        if current_plugin_id:
            current_op = self._operations.get(current_plugin_id)
            if current_op:
                current_op.context._remove_device(device_id)
                await current_op.plugin.on_device_left(
                    current_op.context.get_device(device_id)
                )

        node = node_registry.get_node(device_id)
        if not node:
            return None

        proxy = DeviceProxy(node)
        self._device_assignments[device_id] = requesting_plugin_id
        return proxy

    async def release_device(
        self,
        plugin_id: str,
        device_id: str
    ) -> None:
        """Release a device from an operation."""
        if self._device_assignments.get(device_id) == plugin_id:
            del self._device_assignments[device_id]

    async def is_device_available(self, device_id: str) -> bool:
        """Check if a device is available for recruitment."""
        return device_id not in self._device_assignments

    # ── Graceful Degradation ───────────────────────────────────

    async def on_node_lost(self, node_id: str) -> None:
        """
        Called by failsafe manager when a node goes offline.
        Notifies all affected operations for graceful degradation.
        """
        plugin_id = self._device_assignments.get(node_id)
        if not plugin_id:
            return

        operation = self._operations.get(plugin_id)
        if not operation:
            return

        proxy = operation.context.get_device(node_id)
        if not proxy:
            return

        logger.warning(
            f"Device lost mid-operation: {proxy.name} "
            f"in operation {plugin_id}"
        )

        # Remove from context
        operation.context._remove_device(node_id)
        del self._device_assignments[node_id]

        # Give plugin chance to adapt — graceful degradation
        try:
            await asyncio.wait_for(
                operation.plugin.on_device_left(proxy),
                timeout=5.0
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Plugin {plugin_id} did not respond to "
                f"device_left within 5s"
            )
        except Exception as e:
            logger.error(
                f"Plugin {plugin_id} on_device_left error: {e}"
            )


# Global singleton
operation_manager = OperationManager()