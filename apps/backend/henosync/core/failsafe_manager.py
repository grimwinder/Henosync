import asyncio
import logging
from datetime import datetime, timezone
from ..models import NodeStatus, EventSeverity
from ..plugin_system.registry import plugin_registry
from .telemetry_bus import telemetry_bus

logger = logging.getLogger(__name__)

# Default heartbeat timeout in seconds
# A node is considered lost if no telemetry is received within this window
HEARTBEAT_TIMEOUT = 5.0

# How often the failsafe manager checks heartbeats
POLL_INTERVAL = 1.0


class FailsafeManager:
    """
    Background safety monitor for all connected nodes.

    Responsibilities:
    - Monitor heartbeat timestamps for all online nodes
    - Detect connection loss within the timeout window
    - Invoke plugin safe state on connection loss
    - Pause active missions when a node is lost
    - Emit CRITICAL alerts to the operator
    - Monitor battery levels and trigger low battery failsafe

    The failsafe manager is the last line of defence.
    It runs independently of the mission engine and cannot
    be paused, disabled, or overridden by plugins.
    """

    def __init__(self):
        self._running = False
        self._monitor_task: asyncio.Task | None = None
        # node_id -> True if failsafe already triggered
        # prevents repeated triggering for the same dropout
        self._triggered: dict[str, bool] = {}

    # ── Lifecycle ─────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the failsafe monitor background task."""
        if self._running:
            return
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("Failsafe manager started")

    async def stop(self) -> None:
        """Stop the failsafe monitor."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("Failsafe manager stopped")

    # ── Monitor Loop ──────────────────────────────────────────────

    async def _monitor_loop(self) -> None:
        """
        Main monitoring loop.
        Runs every POLL_INTERVAL seconds checking all node heartbeats.
        """
        while self._running:
            try:
                await self._check_all_nodes()
            except Exception as e:
                logger.error(f"Failsafe monitor error: {e}")

            await asyncio.sleep(POLL_INTERVAL)

    async def _check_all_nodes(self) -> None:
        """Check heartbeats and battery for all online nodes."""
        # Import here to avoid circular import
        from .node_registry import node_registry

        now = datetime.now(timezone.utc)

        for node in node_registry.get_all_nodes():
            # Only monitor nodes that should be connected
            if node.status not in (
                NodeStatus.ONLINE,
                NodeStatus.DEGRADED
            ):
                # Reset triggered flag if node is offline/error
                # so failsafe can re-trigger if it reconnects and drops again
                self._triggered.pop(node.id, None)
                continue

            # ── Heartbeat Check ───────────────────────────────────
            if node.last_seen is None:
                continue

            elapsed = (now - node.last_seen).total_seconds()

            if elapsed > HEARTBEAT_TIMEOUT:
                if not self._triggered.get(node.id):
                    self._triggered[node.id] = True
                    await self._on_node_lost(node)
                continue

            # Node is alive — check if it was previously lost
            # and has now recovered
            if self._triggered.get(node.id):
                self._triggered[node.id] = False
                await self._on_node_recovered(node)

            # ── Battery Check ─────────────────────────────────────
            if node.battery_percent is not None:
                mission_failsafe = await self._get_active_failsafe()
                if mission_failsafe:
                    threshold = mission_failsafe.low_battery_threshold
                    if node.battery_percent <= threshold:
                        await self._on_low_battery(node, threshold)

    # ── Failsafe Handlers ─────────────────────────────────────────

    async def _on_node_lost(self, node) -> None:
        """
        Handle a lost node.
        Called when a node's heartbeat times out.
        """
        logger.critical(
            f"NODE LOST: {node.name} ({node.id}) — "
            f"no heartbeat for {HEARTBEAT_TIMEOUT}s"
        )

        # 1. Invoke plugin safe state immediately
        plugin_instance = plugin_registry.get_instance(node.id)
        if plugin_instance:
            try:
                result = await plugin_instance.get_safe_state(node)
                logger.info(
                    f"Safe state invoked for {node.name}: "
                    f"{result.message}"
                )
            except Exception as e:
                logger.error(
                    f"Safe state failed for {node.name}: {e}"
                )

        # 2. Update node status to ERROR
        from .node_registry import node_registry
        node.status = NodeStatus.ERROR

        # 3. Emit CRITICAL event to operator
        await telemetry_bus.publish_event(
            title="Node Lost",
            message=f"{node.name} has stopped responding. "
                    f"Safe state invoked. "
                    f"Mission paused — operator input required.",
            severity=EventSeverity.CRITICAL,
            node_id=node.id
        )

        # 4. Pause active mission if one is running
        await self._pause_active_mission(node.name)

    async def _on_node_recovered(self, node) -> None:
        """
        Handle a node that has come back online after being lost.
        """
        logger.info(f"Node recovered: {node.name} ({node.id})")

        await telemetry_bus.publish_event(
            title="Node Recovered",
            message=f"{node.name} is responding again. "
                    f"Check mission status before resuming.",
            severity=EventSeverity.WARNING,
            node_id=node.id
        )

    async def _on_low_battery(self, node, threshold: float) -> None:
        """
        Handle a node with critically low battery.
        Only triggers once per node per low-battery event.
        """
        # Use a separate triggered key for battery
        battery_key = f"{node.id}_battery"
        if self._triggered.get(battery_key):
            return

        self._triggered[battery_key] = True

        logger.warning(
            f"LOW BATTERY: {node.name} at "
            f"{node.battery_percent:.1f}% "
            f"(threshold: {threshold}%)"
        )

        # Get mission failsafe action
        mission_failsafe = await self._get_active_failsafe()
        if not mission_failsafe:
            # No active mission — just warn
            await telemetry_bus.publish_event(
                title="Low Battery",
                message=f"{node.name} battery at "
                        f"{node.battery_percent:.1f}%",
                severity=EventSeverity.WARNING,
                node_id=node.id
            )
            return

        from ..models import FailsafeAction
        action = mission_failsafe.on_low_battery

        await telemetry_bus.publish_event(
            title="Low Battery — Failsafe Triggered",
            message=f"{node.name} battery at "
                    f"{node.battery_percent:.1f}%. "
                    f"Failsafe action: {action.value}",
            severity=EventSeverity.CRITICAL,
            node_id=node.id
        )

        if action == FailsafeAction.RETURN_HOME:
            await self._send_return_home(node)
        elif action == FailsafeAction.ABORT:
            await self._abort_active_mission()
        elif action == FailsafeAction.PAUSE:
            await self._pause_active_mission(node.name)

    # ── Emergency Stop ────────────────────────────────────────────

    async def emergency_stop_all(self) -> None:
        """
        Invoke get_safe_state on ALL connected nodes immediately.
        Called by operator pressing Emergency Stop in the GUI.
        This cannot be cancelled or overridden.
        """
        from .node_registry import node_registry

        logger.critical("EMERGENCY STOP ALL — operator triggered")

        await telemetry_bus.publish_event(
            title="Emergency Stop",
            message="Emergency stop triggered by operator. "
                    "Safe state invoked on all nodes.",
            severity=EventSeverity.CRITICAL
        )

        # Abort active mission first
        await self._abort_active_mission()

        # Invoke safe state on all nodes concurrently
        nodes = node_registry.get_online_nodes()
        tasks = []
        for node in nodes:
            plugin_instance = plugin_registry.get_instance(node.id)
            if plugin_instance:
                tasks.append(
                    self._safe_invoke_safe_state(node, plugin_instance)
                )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        logger.critical(
            f"Emergency stop complete — "
            f"safe state invoked on {len(tasks)} nodes"
        )

    async def _safe_invoke_safe_state(self, node, plugin_instance) -> None:
        """Invoke get_safe_state with error protection."""
        try:
            result = await plugin_instance.get_safe_state(node)
            logger.info(
                f"Emergency safe state: {node.name} — {result.message}"
            )
        except Exception as e:
            logger.error(
                f"Emergency safe state failed for {node.name}: {e}"
            )

    # ── Helpers ───────────────────────────────────────────────────

    async def _pause_active_mission(self, node_name: str) -> None:
        """Pause the active mission if one is running."""
        from .mission_engine import mission_engine
        from ..models import MissionStatus
        if mission_engine._status == MissionStatus.EXECUTING:
            await mission_engine.pause()
            logger.info(
                f"Mission paused due to node issue: {node_name}"
            )

    async def _abort_active_mission(self) -> None:
        """Abort the active mission if one is running."""
        from .mission_engine import mission_engine
        from ..models import MissionStatus
        if mission_engine._status in (
            MissionStatus.EXECUTING,
            MissionStatus.PAUSED
        ):
            await mission_engine.abort()
            logger.info("Mission aborted by failsafe manager")

    async def _send_return_home(self, node) -> None:
        """Send return home command to a node."""
        plugin_instance = plugin_registry.get_instance(node.id)
        if not plugin_instance:
            return
        try:
            result = await plugin_instance.send_command(
                node,
                "return_home",
                {}
            )
            logger.info(
                f"Return home sent to {node.name}: {result.message}"
            )
        except Exception as e:
            logger.error(
                f"Return home failed for {node.name}: {e}"
            )

    async def _get_active_failsafe(self):
        """Get the failsafe config from the active mission if any."""
        from .mission_engine import mission_engine
        from ..models import MissionStatus
        if (
            mission_engine._active_mission
            and mission_engine._status == MissionStatus.EXECUTING
        ):
            return mission_engine._active_mission.failsafe
        return None


# Global singleton
failsafe_manager = FailsafeManager()