"""
Concurrent operations on different robots — device selection and conflicts.

Uses fake control plugins with the same priorities as the real ones
(area-navigate = 10, auto-navigate = 5) and fake ONLINE nodes, so no
robot or rosbridge is needed.
"""

import asyncio

import pytest
from henosync_sdk import (
    CapabilityRequirement,
    CapabilitySpec,
    ControlPlugin,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    Node,
    OperationState,
    OperationStatus,
    UIContribution,
)

from henosync.core.node_registry import node_registry
from henosync.core.operation_manager import operation_manager
from henosync.models import NodeStatus


class _FakeOperation(ControlPlugin):
    REQUIRED_CAPABILITIES = [CapabilityRequirement(capability=DeviceCapability.MOVE_2D)]
    SUPPORTED_CATEGORIES = [DeviceCategory.AGV]

    def __init__(self) -> None:
        super().__init__()
        self.devices_seen: list[str] = []
        self.devices_left: list[str] = []
        self.finish = asyncio.Event()

    async def start(self, context) -> None:
        self.devices_seen = [d.id for d in context.devices]
        while not self._stop_requested and not self.finish.is_set():
            await asyncio.sleep(0.01)

    async def stop(self) -> None:
        self._stop_requested = True

    def get_status(self) -> OperationStatus:
        return OperationStatus(state=OperationState.RUNNING)

    def get_ui_contribution(self) -> UIContribution:
        return UIContribution()

    async def on_device_left(self, device) -> None:
        self.devices_left.append(device.id)


class FakeArea(_FakeOperation):
    PLUGIN_ID = "fake-area"
    OPERATION_NAME = "Fake Area"
    PRIORITY = 10


class FakeWaypoint(_FakeOperation):
    PLUGIN_ID = "fake-waypoint"
    OPERATION_NAME = "Fake Waypoint"
    PRIORITY = 5


class FakeOtherArea(_FakeOperation):
    PLUGIN_ID = "fake-other-area"
    OPERATION_NAME = "Fake Other Area"
    PRIORITY = 10


def _agv(name: str, status: NodeStatus = NodeStatus.ONLINE) -> Node:
    return Node(
        name=name,
        plugin_id="fake-device",
        status=status,
        specs=DeviceSpecs(
            category=DeviceCategory.AGV,
            capabilities=[CapabilitySpec(capability=DeviceCapability.MOVE_2D)],
        ),
    )


@pytest.fixture
def fleet():
    """Two online AGVs (jackal, turtlebot) registered with fake plugins."""
    saved_nodes = dict(node_registry._nodes)
    node_registry._nodes.clear()
    operation_manager._operations.clear()
    operation_manager._device_assignments.clear()
    for cls in (FakeArea, FakeWaypoint, FakeOtherArea):
        operation_manager.register_control_plugin(cls)

    jackal, turtlebot = _agv("Jackal"), _agv("TurtleBot3")
    node_registry._nodes[jackal.id] = jackal
    node_registry._nodes[turtlebot.id] = turtlebot

    yield jackal, turtlebot

    for cls in (FakeArea, FakeWaypoint, FakeOtherArea):
        operation_manager._registered_plugins.pop(cls.PLUGIN_ID, None)
    node_registry._nodes.clear()
    node_registry._nodes.update(saved_nodes)


async def _start(plugin_id: str, config: dict) -> tuple[bool, str]:
    ok, msg = await operation_manager.start_operation(plugin_id, config)
    await asyncio.sleep(0.05)  # let start() record its devices
    return ok, msg


def _plugin(plugin_id: str) -> _FakeOperation:
    return operation_manager._operations[plugin_id].plugin


async def _stop_all() -> None:
    await operation_manager.stop_all_operations()


@pytest.mark.asyncio
async def test_area_and_waypoint_run_at_the_same_time_on_different_robots(fleet):
    jackal, turtlebot = fleet

    ok_area, msg_area = await _start("fake-area", {"node_ids": [jackal.id]})
    ok_wp, msg_wp = await _start("fake-waypoint", {"node_id": turtlebot.id})

    assert ok_area, msg_area
    assert ok_wp, msg_wp
    assert _plugin("fake-area").devices_seen == [jackal.id]
    assert _plugin("fake-waypoint").devices_seen == [turtlebot.id]
    assert operation_manager._device_assignments == {
        jackal.id: "fake-area",
        turtlebot.id: "fake-waypoint",
    }
    await _stop_all()


@pytest.mark.asyncio
async def test_order_does_not_matter_when_robots_are_selected(fleet):
    jackal, turtlebot = fleet

    ok_wp, _ = await _start("fake-waypoint", {"node_id": turtlebot.id})
    ok_area, msg = await _start("fake-area", {"node_ids": [jackal.id]})

    assert ok_wp and ok_area, msg
    # The higher-priority area op must not have touched the waypoint robot.
    assert _plugin("fake-waypoint").devices_left == []
    assert _plugin("fake-area").devices_seen == [jackal.id]
    await _stop_all()


@pytest.mark.asyncio
async def test_no_selection_only_takes_free_robots(fleet):
    jackal, turtlebot = fleet

    await _start("fake-waypoint", {"node_id": turtlebot.id})
    ok, msg = await _start("fake-area", {})

    assert ok, msg
    assert _plugin("fake-area").devices_seen == [jackal.id]
    assert _plugin("fake-waypoint").devices_left == []
    await _stop_all()


@pytest.mark.asyncio
async def test_selected_robot_held_by_lower_priority_is_handed_over(fleet):
    jackal, turtlebot = fleet

    await _start("fake-waypoint", {"node_id": turtlebot.id})
    waypoint = _plugin("fake-waypoint")
    ok, msg = await _start("fake-area", {"node_ids": [turtlebot.id]})

    assert ok, msg
    assert waypoint.devices_left == [turtlebot.id]  # old owner was told
    assert operation_manager._device_assignments[turtlebot.id] == "fake-area"
    await _stop_all()


@pytest.mark.asyncio
async def test_selected_robot_held_by_equal_priority_is_refused(fleet):
    jackal, _ = fleet

    await _start("fake-area", {"node_ids": [jackal.id]})
    ok, msg = await _start("fake-other-area", {"node_ids": [jackal.id]})

    assert not ok
    assert "Jackal is in use by Fake Area" in msg
    assert operation_manager._device_assignments[jackal.id] == "fake-area"
    await _stop_all()


@pytest.mark.asyncio
async def test_finished_operation_releases_its_robots(fleet):
    jackal, _ = fleet

    await _start("fake-area", {"node_ids": [jackal.id]})
    _plugin("fake-area").finish.set()
    await asyncio.sleep(0.05)

    ok, msg = await _start("fake-other-area", {"node_ids": [jackal.id]})
    assert ok, msg
    assert _plugin("fake-other-area").devices_seen == [jackal.id]
    await _stop_all()


@pytest.mark.asyncio
async def test_selected_robot_offline_is_refused(fleet):
    jackal, _ = fleet
    jackal.status = NodeStatus.OFFLINE

    ok, msg = await _start("fake-area", {"node_ids": [jackal.id]})

    assert not ok
    assert "Jackal is not online" in msg
