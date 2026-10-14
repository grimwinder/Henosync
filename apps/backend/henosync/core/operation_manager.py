import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from ..models import (
    EventSeverity,
)
from ..plugin_system.control_interfaces import (
    ControlPlugin,
)
from .device_proxy import DeviceProxy
from .event_bus import event_bus
from .fleet_context import FleetContext
from .telemetry_bus import telemetry_bus
from .marker_manager import marker_manager
from .zone_manager import zone_manager

logger = logging.getLogger(__name__)


class ActiveOperation:
    """Tracks a running control plugin operation."""

    def __init__(
        self,
        operation_id: str,
        plugin: ControlPlugin,
        context: FleetContext,
        task: asyncio.Task
    ):
        self.operation_id = operation_id
        self.plugin = plugin
        self.context = context
        self.task = task
        self.started_at = datetime.now(timezone.utc)
        self.plugin_id = plugin.PLUGIN_ID


class OperationManager:
    """
    Manages all running control plugin operations.

    Operations are keyed by a generated operation_id (UUID), allowing the same
    plugin type to run multiple times concurrently on different devices.
    """

    def __init__(self):
        # operation_id -> ActiveOperation
        self._operations: dict[str, ActiveOperation] = {}
        # device_id -> operation_id (which operation owns it)
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
    ) -> tuple[bool, str, str]:
        """
        Start a control plugin operation.

        Returns (success, message, operation_id).
        operation_id is "" on failure.
        """
        # Clean up any finished operations for this plugin first.
        for op_id, op in list(self._operations.items()):
            if op.plugin_id == plugin_id and op.task.done():
                for dev_id, assigned in list(self._device_assignments.items()):
                    if assigned == op_id:
                        del self._device_assignments[dev_id]
                event_bus.unregister_plugin(op_id)
                del self._operations[op_id]
                logger.info("Cleaned up completed operation: %s", op_id)

        plugin_class = self._registered_plugins.get(plugin_id)
        if not plugin_class:
            return False, f"Control plugin not found: {plugin_id}", ""

        # Match devices to this plugin
        matched_devices = await self._match_devices(plugin_class, config)

        if not matched_devices and plugin_class.REQUIRED_CAPABILITIES:
            return False, (
                f"No devices available matching requirements for "
                f"{plugin_class.PLUGIN_NAME}"
            ), ""

        operation_id = str(uuid.uuid4())

        # Create plugin instance
        plugin_instance = plugin_class()

        # Register with event bus (keyed by operation_id for uniqueness)
        event_bus.register_plugin(
            operation_id,
            plugin_instance.on_message
        )

        # Create fleet context
        context = FleetContext(
            operation_id=operation_id,
            plugin_id=plugin_id,
            initial_devices=matched_devices,
            zone_manager=zone_manager,
            marker_manager=marker_manager,
            event_bus=event_bus
        )

        # Assign devices to this operation
        for device in matched_devices:
            self._device_assignments[device.id] = operation_id

        # Start operation as background task
        task = asyncio.create_task(
            self._run_operation(plugin_instance, context, config)
        )

        self._operations[operation_id] = ActiveOperation(
            operation_id, plugin_instance, context, task
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
            f"Operation started: {plugin_id} (id={operation_id}) "
            f"with {len(matched_devices)} devices"
        )
        return True, "Operation started", operation_id

    async def stop_operation(
        self,
        operation_id: str
    ) -> tuple[bool, str]:
        """Stop a running operation by operation_id."""
        operation = self._operations.get(operation_id)
        if not operation:
            return False, f"No running operation: {operation_id}"

        logger.info(f"Stopping operation: {operation_id}")

        # Give plugin 3 seconds to stop cleanly
        try:
            await asyncio.wait_for(
                operation.plugin.stop(),
                timeout=3.0
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Operation {operation_id} did not stop within 3s — forcing"
            )

        # Cancel the task
        if not operation.task.done():
            operation.task.cancel()
            try:
                await operation.task
            except asyncio.CancelledError:
                pass

        # Release all devices
        for device_id, assigned_op in list(self._device_assignments.items()):
            if assigned_op == operation_id:
                del self._device_assignments[device_id]

        # Unregister from event bus
        event_bus.unregister_plugin(operation_id)

        del self._operations[operation_id]

        await telemetry_bus.publish_event(
            title="Operation Stopped",
            message=f"{operation.plugin.OPERATION_NAME} stopped",
            severity=EventSeverity.INFO
        )

        return True, "Operation stopped"

    async def send_operator_input(
        self,
        plugin_id: str,
        input_key: str,
        value: Any
    ) -> tuple[bool, str]:
        """
        Forward operator input to a running operation by plugin_id.

        Finds the first running instance of the given plugin.
        Teleop is the only consumer and only runs once.
        """
        operation = next(
            (op for op in self._operations.values() if op.plugin_id == plugin_id),
            None
        )
        if not operation:
            return False, f"No running operation: {plugin_id}"

        await operation.plugin.on_operator_input(input_key, value)
        return True, "Input delivered"

    async def stop_all_operations(self) -> None:
        """Stop all running operations. Called by emergency stop."""
        logger.critical("Stopping all control plugin operations")
        for operation_id in list(self._operations.keys()):
            await self.stop_operation(operation_id)

    async def _run_operation(
        self,
        plugin: ControlPlugin,
        context: FleetContext,
        config: dict
    ) -> None:
        """Run a control plugin operation with error handling."""
        try:
            plugin._config = config  # make config available inside start()
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
        for operation_id, operation in self._operations.items():
            try:
                status = operation.plugin.get_status()
                statuses.append({
                    "operation_id": operation_id,
                    "plugin_id": operation.plugin_id,
                    "operation_name": operation.plugin.OPERATION_NAME,
                    "started_at": operation.started_at.isoformat(),
                    "status": status.model_dump()
                })
            except Exception as e:
                logger.error(f"Status error for {operation_id}: {e}")
        return statuses

    def get_node_operation(self, node_id: str) -> dict | None:
        """Return the operation status dict for the operation currently using node_id, or None."""
        op_id = self._device_assignments.get(node_id)
        if not op_id:
            return None
        op = self._operations.get(op_id)
        if not op:
            return None
        try:
            status = op.plugin.get_status()
            return {
                "operation_id": op_id,
                "plugin_id": op.plugin_id,
                "operation_name": op.plugin.OPERATION_NAME,
                "status": status.model_dump(),
            }
        except Exception as e:
            logger.error(f"get_node_operation error for {node_id}: {e}")
            return None

    # ── Device Management ──────────────────────────────────────

    async def _match_devices(
        self,
        plugin_class: type[ControlPlugin],
        config: dict[str, Any] = {}
    ) -> list[DeviceProxy]:
        """
        Find all available devices matching plugin requirements.

        If config contains node_id, only that device is matched.
        """
        from .node_registry import node_registry

        requested_id: str = config.get("node_id", "") or ""

        matched = []
        for node in node_registry.get_online_nodes():
            if requested_id and node.id != requested_id:
                continue

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
        current_op_id = self._device_assignments.get(device_id)
        if not current_op_id:
            return True

        current_op = self._operations.get(current_op_id)
        if not current_op or current_op.task.done():
            # Stale assignment — clean it up
            del self._device_assignments[device_id]
            return True

        return requesting_priority > current_op.plugin.PRIORITY

    async def try_recruit_device(
        self,
        requesting_operation_id: str,
        device_id: str
    ) -> Optional[DeviceProxy]:
        """
        Try to recruit a device for an operation.
        Called by FleetContext.recruit_device().
        """
        from .node_registry import node_registry

        requesting_op = self._operations.get(requesting_operation_id)
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
        current_op_id = self._device_assignments.get(device_id)
        if current_op_id:
            current_op = self._operations.get(current_op_id)
            if current_op:
                proxy = current_op.context.get_device(device_id)
                current_op.context._remove_device(device_id)
                if proxy:
                    await current_op.plugin.on_device_left(proxy)

        node = node_registry.get_node(device_id)
        if not node:
            return None

        proxy = DeviceProxy(node)
        self._device_assignments[device_id] = requesting_operation_id
        return proxy

    async def release_device(
        self,
        operation_id: str,
        device_id: str
    ) -> None:
        """Release a device from an operation."""
        if self._device_assignments.get(device_id) == operation_id:
            del self._device_assignments[device_id]

    async def is_device_available(self, device_id: str) -> bool:
        """Check if a device is available for recruitment."""
        op_id = self._device_assignments.get(device_id)
        if not op_id:
            return True
        op = self._operations.get(op_id)
        if not op or op.task.done():
            del self._device_assignments[device_id]
            return True
        return False

    # ── Graceful Degradation ───────────────────────────────────

    async def on_node_lost(self, node_id: str) -> None:
        """
        Called by failsafe manager when a node goes offline.
        Notifies all affected operations for graceful degradation.
        """
        operation_id = self._device_assignments.get(node_id)
        if not operation_id:
            return

        operation = self._operations.get(operation_id)
        if not operation:
            return

        proxy = operation.context.get_device(node_id)
        if not proxy:
            return

        logger.warning(
            f"Device lost mid-operation: {proxy.name} "
            f"in operation {operation_id}"
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
                f"Plugin {operation.plugin_id} did not respond to "
                f"device_left within 5s"
            )
        except Exception as e:
            logger.error(
                f"Plugin {operation.plugin_id} on_device_left error: {e}"
            )


# Global singleton
operation_manager = OperationManager()
