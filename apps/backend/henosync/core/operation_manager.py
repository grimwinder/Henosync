import asyncio
import logging
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
            existing = self._operations[plugin_id]
            if existing.task.done():
                # Previous run finished but was never explicitly stopped — clean up.
                for dev_id, pid in list(self._device_assignments.items()):
                    if pid == plugin_id:
                        del self._device_assignments[dev_id]
                event_bus.unregister_plugin(plugin_id)
                del self._operations[plugin_id]
                logger.info("Cleaned up completed operation: %s", plugin_id)
            else:
                return False, f"Operation already running: {plugin_id}"

        plugin_class = self._registered_plugins.get(plugin_id)
        if not plugin_class:
            return False, f"Control plugin not found: {plugin_id}"

        # Match devices to this plugin
        requested = self._requested_device_ids(config)
        matched_devices, problems = await self._match_devices(
            plugin_class, requested
        )

        if problems:
            return False, (
                f"Cannot start {plugin_class.OPERATION_NAME}: "
                + "; ".join(problems)
            )

        if not matched_devices and plugin_class.REQUIRED_CAPABILITIES:
            return False, (
                f"No devices available matching requirements for "
                f"{plugin_class.PLUGIN_NAME}"
            )

        # Explicitly requested devices held by a lower-priority operation are
        # taken over — tell that operation first so it stops driving them.
        for device in matched_devices:
            await self._preempt_device(device.id, plugin_class.OPERATION_NAME)

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
            marker_manager=marker_manager,
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

    async def send_operator_input(
        self,
        plugin_id: str,
        input_key: str,
        value: Any
    ) -> tuple[bool, str]:
        """Forward operator input (e.g. keyboard) to a running operation."""
        operation = self._operations.get(plugin_id)
        if not operation:
            return False, f"No running operation: {plugin_id}"

        await operation.plugin.on_operator_input(input_key, value)
        return True, "Input delivered"

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

    @staticmethod
    def _requested_device_ids(config: dict[str, Any]) -> set[str]:
        """
        Devices the operator explicitly picked for this operation.

        Convention for control plugin config: "node_id" selects one device,
        "node_ids" selects several. Neither set means "any free matching
        device".
        """
        ids: set[str] = set()
        if config.get("node_id"):
            ids.add(config["node_id"])
        node_ids = config.get("node_ids") or []
        if isinstance(node_ids, str):
            node_ids = [node_ids]
        ids.update(i for i in node_ids if i)
        return ids

    def _active_owner(self, device_id: str) -> Optional[str]:
        """
        plugin_id of the running operation that holds this device, or None.
        Assignments left behind by an operation that already finished are
        released here, so a completed step never blocks the next one.
        """
        plugin_id = self._device_assignments.get(device_id)
        if plugin_id is None:
            return None
        operation = self._operations.get(plugin_id)
        if operation is None or operation.task.done():
            del self._device_assignments[device_id]
            return None
        return plugin_id

    async def _match_devices(
        self,
        plugin_class: type[ControlPlugin],
        requested: set[str] = frozenset(),
    ) -> tuple[list[DeviceProxy], list[str]]:
        """
        Find devices for a new operation. Applies capability negotiation.

        No explicit selection: every free matching device — devices held by
        another running operation are never taken.
        Explicit selection: exactly the requested devices. A requested device
        held by a lower-priority operation is matched (and preempted by the
        caller); anything else that prevents using a requested device is
        returned as a problem so the start fails with a clear reason.

        Returns (matched devices, problems).
        """
        from .node_registry import node_registry

        matched: list[DeviceProxy] = []
        problems: list[str] = []
        online_ids: set[str] = set()

        for node in node_registry.get_online_nodes():
            online_ids.add(node.id)
            if requested and node.id not in requested:
                continue

            proxy = DeviceProxy(node)

            # Category filter + capability negotiation
            category_ok = (
                not plugin_class.SUPPORTED_CATEGORIES
                or proxy.category in plugin_class.SUPPORTED_CATEGORIES
            )
            caps_ok = all(
                proxy.meets_requirement(req)
                for req in plugin_class.REQUIRED_CAPABILITIES
                if req.required
            )
            if not (category_ok and caps_ok):
                if requested:
                    problems.append(
                        f"{node.name} does not support "
                        f"{plugin_class.OPERATION_NAME}"
                    )
                continue

            owner = self._active_owner(node.id)
            if owner is None:
                matched.append(proxy)
                continue

            owner_op = self._operations[owner]
            if requested and plugin_class.PRIORITY > owner_op.plugin.PRIORITY:
                matched.append(proxy)
            elif requested:
                problems.append(
                    f"{node.name} is in use by {owner_op.plugin.OPERATION_NAME}"
                )

        for device_id in requested - online_ids:
            node = node_registry.get_node(device_id)
            name = node.name if node else device_id
            problems.append(f"{name} is not online")

        return matched, problems

    async def _preempt_device(self, device_id: str, new_owner_name: str) -> None:
        """
        Take a device away from the operation currently holding it (if any),
        telling that operation via on_device_left() so it stops driving it.
        """
        owner = self._active_owner(device_id)
        if owner is None:
            return

        operation = self._operations[owner]
        proxy = operation.context.get_device(device_id)
        operation.context._remove_device(device_id)
        del self._device_assignments[device_id]

        if proxy is not None:
            try:
                await asyncio.wait_for(
                    operation.plugin.on_device_left(proxy), timeout=5.0
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Plugin {owner} did not respond to device_left within 5s"
                )
            except Exception as e:
                logger.error(f"Plugin {owner} on_device_left error: {e}")

        name = proxy.name if proxy else device_id
        await telemetry_bus.publish_event(
            title="Robot Reassigned",
            message=(
                f"{name} moved from {operation.plugin.OPERATION_NAME} "
                f"to {new_owner_name}"
            ),
            severity=EventSeverity.WARNING,
        )

    async def _can_assign_device(
        self,
        device_id: str,
        requesting_priority: int
    ) -> bool:
        """
        Check if a device can be assigned to an operation.
        Higher priority operations win device conflicts.
        """
        current_plugin_id = self._active_owner(device_id)
        if not current_plugin_id:
            return True

        current_priority = self._operations[current_plugin_id].plugin.PRIORITY
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
