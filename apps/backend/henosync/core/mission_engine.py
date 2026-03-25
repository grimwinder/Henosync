import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional
from ..models import (
    Mission, MissionStep, MissionStatus, StepStatus,
    StepType, EventSeverity, ConditionOperator
)
from ..storage.mission_store import mission_store
from ..plugin_system.registry import plugin_registry
from .node_registry import node_registry
from .telemetry_bus import telemetry_bus

logger = logging.getLogger(__name__)


class MissionEngine:
    """
    Executes mission plans step by step.

    The engine is a state machine that:
    - Reads steps from a mission plan
    - Dispatches commands to nodes via plugins
    - Evaluates conditions and branches accordingly
    - Handles failures by pausing and alerting operator
    - Resumes from exact step on unpause

    One engine instance handles one active mission at a time.
    """

    def __init__(self):
        self._active_mission: Optional[Mission] = None
        self._current_step_index: int = 0
        self._status: MissionStatus = MissionStatus.DRAFT
        self._execution_task: Optional[asyncio.Task] = None
        self._paused_event: asyncio.Event = asyncio.Event()
        self._paused_event.set()  # Not paused by default
        self._abort_flag: bool = False

    # ── Public Control Methods ────────────────────────────────────

    async def execute(self, mission_id: str) -> bool:
        """
        Start executing a mission.

        Returns True if execution started successfully.
        """
        if self._active_mission:
            logger.warning("A mission is already executing")
            return False

        mission = await mission_store.get(mission_id)
        if not mission:
            logger.error(f"Mission not found: {mission_id}")
            return False

        if not mission.steps:
            logger.error("Mission has no steps")
            return False

        # Validate mission before starting
        errors = await self._validate_mission(mission)
        if errors:
            for error in errors:
                logger.error(f"Mission validation error: {error}")
            await telemetry_bus.publish_event(
                title="Mission Validation Failed",
                message=f"{len(errors)} error(s) found. "
                        f"Check all nodes are online.",
                severity=EventSeverity.WARNING
            )
            return False

        self._active_mission = mission
        self._current_step_index = 0
        self._abort_flag = False
        self._paused_event.set()

        # Update mission status
        await mission_store.update_status(
            mission_id,
            MissionStatus.EXECUTING
        )
        self._status = MissionStatus.EXECUTING

        await telemetry_bus.publish_event(
            title="Mission Started",
            message=f"Executing: {mission.name}",
            severity=EventSeverity.INFO
        )

        # Notify plugins mission is starting
        for step in mission.steps:
            if step.target_node_id:
                instance = plugin_registry.get_instance(
                    step.target_node_id
                )
                if instance:
                    node = node_registry.get_node(step.target_node_id)
                    if node:
                        await instance.on_mission_start(node)

        # Start execution in background task
        self._execution_task = asyncio.create_task(
            self._execute_loop()
        )
        return True

    async def pause(self) -> bool:
        """Pause mission execution after current step completes."""
        if not self._active_mission:
            return False
        if self._status != MissionStatus.EXECUTING:
            return False

        self._paused_event.clear()
        self._status = MissionStatus.PAUSED

        await mission_store.update_status(
            self._active_mission.id,
            MissionStatus.PAUSED
        )

        await telemetry_bus.publish_event(
            title="Mission Paused",
            message=f"Paused at step {self._current_step_index + 1} "
                    f"of {len(self._active_mission.steps)}",
            severity=EventSeverity.WARNING
        )

        logger.info(
            f"Mission paused at step {self._current_step_index}"
        )
        return True

    async def resume(self) -> bool:
        """
        Resume a paused mission from the exact step it was paused on.
        """
        if not self._active_mission:
            return False
        if self._status != MissionStatus.PAUSED:
            return False

        self._status = MissionStatus.EXECUTING
        self._paused_event.set()

        await mission_store.update_status(
            self._active_mission.id,
            MissionStatus.EXECUTING
        )

        await telemetry_bus.publish_event(
            title="Mission Resumed",
            message=f"Resuming from step {self._current_step_index + 1}",
            severity=EventSeverity.INFO
        )

        logger.info(
            f"Mission resumed from step {self._current_step_index}"
        )
        return True

    async def abort(self) -> bool:
        """Abort the active mission immediately."""
        if not self._active_mission:
            return False

        self._abort_flag = True
        self._paused_event.set()  # Unblock if paused

        if self._execution_task:
            self._execution_task.cancel()
            try:
                await self._execution_task
            except asyncio.CancelledError:
                pass

        await self._on_mission_end(MissionStatus.ABORTED)
        return True

    def get_status(self) -> dict:
        """Get current mission engine status."""
        return {
            "status": self._status.value,
            "mission_id": (
                self._active_mission.id
                if self._active_mission else None
            ),
            "mission_name": (
                self._active_mission.name
                if self._active_mission else None
            ),
            "current_step": self._current_step_index,
            "total_steps": (
                len(self._active_mission.steps)
                if self._active_mission else 0
            )
        }

    # ── Execution Loop ────────────────────────────────────────────

    async def _execute_loop(self) -> None:
        """Main execution loop — runs until mission ends."""
        mission = self._active_mission
        steps = mission.steps

        try:
            while self._current_step_index < len(steps):
                if self._abort_flag:
                    break

                # Wait if paused — resumes from exact same step
                await self._paused_event.wait()

                if self._abort_flag:
                    break

                step = steps[self._current_step_index]
                logger.info(
                    f"Executing step {self._current_step_index + 1}"
                    f"/{len(steps)}: {step.step_type} — {step.label}"
                )

                # Mark step as active
                step.status = StepStatus.ACTIVE
                await telemetry_bus.publish_event(
                    title="Step Started",
                    message=f"Step {self._current_step_index + 1}: "
                            f"{step.label or step.step_type}",
                    severity=EventSeverity.INFO
                )

                # Execute the step
                success = await self._execute_step(step)

                if self._abort_flag:
                    break

                if success:
                    step.status = StepStatus.COMPLETED
                    self._current_step_index += 1
                else:
                    step.status = StepStatus.FAILED
                    await self._on_step_failed(step)
                    # Pause and wait for operator
                    # v2: make this configurable
                    await self.pause()
                    return

            # All steps completed
            if not self._abort_flag:
                await self._on_mission_end(MissionStatus.COMPLETED)

        except asyncio.CancelledError:
            logger.info("Mission execution task cancelled")
        except Exception as e:
            logger.error(f"Mission engine error: {e}")
            await self._on_mission_end(MissionStatus.FAILED)

    async def _execute_step(self, step: MissionStep) -> bool:
        """Execute a single mission step."""
        try:
            if step.step_type == StepType.MOVE:
                return await self._execute_move(step)

            elif step.step_type == StepType.ACTION:
                return await self._execute_action(step)

            elif step.step_type == StepType.WAIT:
                return await self._execute_wait(step)

            elif step.step_type == StepType.CONDITION:
                return await self._execute_condition(step)

            elif step.step_type == StepType.PARALLEL:
                return await self._execute_parallel(step)

            else:
                logger.warning(f"Unknown step type: {step.step_type}")
                return False

        except Exception as e:
            logger.error(f"Step execution error: {e}")
            return False

    # ── Step Executors ────────────────────────────────────────────

    async def _execute_move(self, step: MissionStep) -> bool:
        """Execute a MOVE step — navigate node to a position."""
        node_id = step.target_node_id
        if not node_id:
            logger.error("MOVE step has no target node")
            return False

        instance = plugin_registry.get_instance(node_id)
        node = node_registry.get_node(node_id)
        if not instance or not node:
            logger.error(f"Node not available: {node_id}")
            return False

        result = await instance.send_command(
            node,
            "move_to",
            step.parameters
        )

        if not result.success:
            logger.error(f"MOVE failed: {result.message}")

        return result.success

    async def _execute_action(self, step: MissionStep) -> bool:
        """Execute an ACTION step — run a capability on a node."""
        node_id = step.target_node_id
        capability = step.parameters.get("capability")

        if not node_id or not capability:
            logger.error("ACTION step missing node_id or capability")
            return False

        instance = plugin_registry.get_instance(node_id)
        node = node_registry.get_node(node_id)
        if not instance or not node:
            logger.error(f"Node not available: {node_id}")
            return False

        result = await instance.send_command(
            node,
            capability,
            step.parameters
        )

        if not result.success:
            logger.error(f"ACTION failed: {result.message}")

        return result.success

    async def _execute_wait(self, step: MissionStep) -> bool:
        """Execute a WAIT step — pause for a duration."""
        duration = step.parameters.get("duration_seconds", 1)
        logger.info(f"Waiting {duration} seconds...")

        try:
            await asyncio.sleep(duration)
            return True
        except asyncio.CancelledError:
            return False

    async def _execute_condition(self, step: MissionStep) -> bool:
        """
        Execute a CONDITION step — evaluate telemetry and branch.
        Updates current_step_index to the correct branch.
        """
        condition = step.condition
        if not condition:
            logger.error("CONDITION step has no condition defined")
            return False

        node = node_registry.get_node(condition.node_id)
        if not node:
            logger.error(
                f"Condition node not found: {condition.node_id}"
            )
            return False

        # Get current telemetry value
        actual_value = node.telemetry.get(condition.telemetry_key)
        if actual_value is None:
            logger.warning(
                f"Telemetry key not found: {condition.telemetry_key}"
            )
            return False

        # Evaluate condition
        result = self._evaluate_condition(
            float(actual_value),
            condition.operator,
            condition.value
        )

        logger.info(
            f"Condition: {condition.telemetry_key} "
            f"{condition.operator} {condition.value} "
            f"= {result} (actual: {actual_value})"
        )

        # Branch to correct step
        if result and step.then_step_id:
            self._jump_to_step(step.then_step_id)
        elif not result and step.else_step_id:
            self._jump_to_step(step.else_step_id)

        return True

    async def _execute_parallel(self, step: MissionStep) -> bool:
        """
        Execute a PARALLEL step — run multiple steps simultaneously.
        Waits for all parallel steps to complete.
        """
        if not step.parallel_step_ids:
            logger.warning("PARALLEL step has no parallel step ids")
            return True

        mission = self._active_mission
        parallel_steps = [
            s for s in mission.steps
            if s.id in step.parallel_step_ids
        ]

        # Execute all parallel steps concurrently
        tasks = [
            self._execute_step(s)
            for s in parallel_steps
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All must succeed
        return all(
            r is True
            for r in results
            if not isinstance(r, Exception)
        )

    # ── Helpers ───────────────────────────────────────────────────

    def _evaluate_condition(
        self,
        actual: float,
        operator: ConditionOperator,
        threshold: float
    ) -> bool:
        """Evaluate a condition against a telemetry value."""
        if operator == ConditionOperator.GREATER_THAN:
            return actual > threshold
        elif operator == ConditionOperator.LESS_THAN:
            return actual < threshold
        elif operator == ConditionOperator.EQUALS:
            return actual == threshold
        elif operator == ConditionOperator.NOT_EQUALS:
            return actual != threshold
        return False

    def _jump_to_step(self, step_id: str) -> None:
        """Jump execution to a specific step by id."""
        mission = self._active_mission
        for i, step in enumerate(mission.steps):
            if step.id == step_id:
                # Set to i-1 because loop will increment
                self._current_step_index = i - 1
                return
        logger.warning(f"Step id not found for jump: {step_id}")

    async def _validate_mission(
        self,
        mission: Mission
    ) -> list[str]:
        """
        Validate a mission before execution.
        Returns list of error strings — empty means valid.
        """
        errors = []

        for i, step in enumerate(mission.steps):
            step_label = f"Step {i + 1} ({step.step_type})"

            # Check target node exists and is online
            if step.target_node_id:
                node = node_registry.get_node(step.target_node_id)
                if not node:
                    errors.append(
                        f"{step_label}: Node not found "
                        f"({step.target_node_id})"
                    )
                    continue

                from ..models import NodeStatus
                if node.status != NodeStatus.ONLINE:
                    errors.append(
                        f"{step_label}: Node '{node.name}' "
                        f"is not online (status: {node.status})"
                    )

        return errors

    async def _on_step_failed(self, step: MissionStep) -> None:
        """Handle a failed step."""
        await telemetry_bus.publish_event(
            title="Step Failed",
            message=f"Step {self._current_step_index + 1} failed: "
                    f"{step.label or step.step_type}. "
                    f"Mission paused — operator input required.",
            severity=EventSeverity.CRITICAL,
            node_id=step.target_node_id
        )
        logger.error(
            f"Step {self._current_step_index + 1} failed — "
            f"mission paused for operator input"
        )

    async def _on_mission_end(self, status: MissionStatus) -> None:
        """Clean up after mission ends."""
        mission = self._active_mission
        if not mission:
            return

        self._status = status
        await mission_store.update_status(mission.id, status)

        # Notify plugins mission ended
        for step in mission.steps:
            if step.target_node_id:
                instance = plugin_registry.get_instance(
                    step.target_node_id
                )
                if instance:
                    node = node_registry.get_node(step.target_node_id)
                    if node:
                        await instance.on_mission_end(node)

        severity = (
            EventSeverity.INFO
            if status == MissionStatus.COMPLETED
            else EventSeverity.WARNING
        )

        await telemetry_bus.publish_event(
            title=f"Mission {status.value.capitalize()}",
            message=f"{mission.name} — {status.value}",
            severity=severity
        )

        logger.info(f"Mission ended: {status.value}")

        # Reset engine state
        self._active_mission = None
        self._current_step_index = 0
        self._execution_task = None
        self._abort_flag = False
        self._paused_event.set()


# Global singleton
mission_engine = MissionEngine()