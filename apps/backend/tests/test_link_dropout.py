"""
Link dropout (Test 2): a robot running its onboard controller keeps driving
while rosbridge is down. Henosync must keep waiting for the path (not time it
out), pick progress back up from the new plugin instance a reconnect creates,
log the failsafe link-lost/restored events, and reconnect automatically while
keeping the node DEGRADED (so vicon_manager keeps tracking it).
"""

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest
from henosync_sdk import (
    CapabilitySpec,
    CommandResult,
    DeviceCapability,
    DeviceSpecs,
    Node,
    NodePlugin,
    NodeStatus,
    TelemetryFrame,
)

from henosync.core.node_registry import NodeRegistry
from henosync.core.telemetry_bus import telemetry_bus
from henosync.plugin_system.registry import plugin_registry

REPO = Path(__file__).resolve().parents[3]


def _load_jackal():
    spec = importlib.util.spec_from_file_location(
        "jackal_plugin_under_test", REPO / "plugins/device/jackal/plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


jackal = _load_jackal()


def _onboard_node() -> Node:
    node = Node(name="Jackal", plugin_id="jackal", config={"onboard_timeout_s": 0.6})
    node.specs = DeviceSpecs(
        capabilities=[CapabilitySpec(capability=DeviceCapability.ONBOARD_CTRL)],
        coordinate_frame="local",
    )
    return node


def _connected_instance(node: Node, sent: list):
    """A JackalPlugin as connect() would leave it, with publishing captured."""
    plugin = jackal.JackalPlugin()
    state = jackal._NodeState()
    state.connected = True
    state.waypoint_pub = object()
    plugin._nodes[node.id] = state
    plugin._publish_waypoint = lambda _state, data: sent.append(json.loads(data))
    return plugin


def _progress(plugin, node, path_id, completed, total, done=False):
    plugin._on_progress(node.id, {"data": json.dumps({
        "path_id": path_id, "completed": completed, "total": total,
        "done": done, "stopped": False,
    })})


@pytest.fixture
def fast_timing(monkeypatch):
    monkeypatch.setattr(jackal.JackalPlugin, "LINK_LOST_S", 0.3)
    monkeypatch.setattr(jackal.JackalPlugin, "PROGRESS_ACK_TIMEOUT_S", 0.5)


@pytest.mark.asyncio
async def test_path_survives_dropout_and_reconnect(fast_timing):
    node = _onboard_node()
    sent: list = []
    old = _connected_instance(node, sent)
    path = [{"x": 0.0, "y": 0.0}, {"x": 1.0, "y": 0.0}, {"x": 1.0, "y": 1.0}]

    task = asyncio.create_task(old.cmd_follow_path(node, path))
    await asyncio.sleep(0.05)
    assert sent[0]["path"] == path
    path_id = sent[0]["path_id"]
    _progress(old, node, path_id, 1, 3)

    # Link drops: old instance torn down, no progress for longer than the
    # 0.6 s waypoint timeout — must keep waiting, not fail.
    await old.disconnect(node)
    await asyncio.sleep(1.0)
    assert not task.done()

    # Reconnect creates a new instance; the robot finished meanwhile.
    new = _connected_instance(node, sent)
    _progress(new, node, path_id, 3, 3, done=True)

    result = await asyncio.wait_for(task, 1.0)
    assert result.success
    assert result.data["completed"] == 3
    assert node.id not in jackal._PATHS


@pytest.mark.asyncio
async def test_waypoint_timeout_while_link_up(fast_timing):
    node = _onboard_node()
    sent: list = []
    plugin = _connected_instance(node, sent)

    task = asyncio.create_task(plugin.cmd_follow_path(node, [{"x": 1.0, "y": 0.0}]))
    await asyncio.sleep(0.05)
    path_id = sent[0]["path_id"]
    for _ in range(6):  # robot reports in but never reaches the waypoint
        _progress(plugin, node, path_id, 0, 1)
        await asyncio.sleep(0.2)

    result = await asyncio.wait_for(task, 1.0)
    assert not result.success
    assert "timeout" in result.message
    assert sent[-1] == {"stop": True}


@pytest.mark.asyncio
async def test_controller_not_running(fast_timing):
    node = _onboard_node()
    sent: list = []
    plugin = _connected_instance(node, sent)

    result = await asyncio.wait_for(
        plugin.cmd_follow_path(node, [{"x": 1.0, "y": 0.0}]), 2.0
    )
    assert not result.success
    assert "not responding" in result.message


@pytest.mark.asyncio
async def test_no_onboard_falls_back():
    node = Node(name="Jackal", plugin_id="jackal")
    plugin = jackal.JackalPlugin()
    plugin._nodes[node.id] = jackal._NodeState()
    result = await plugin.cmd_follow_path(node, [{"x": 1.0, "y": 0.0}])
    assert "not implemented" in result.message


# ── node_registry: failsafe events + auto-reconnect ───────────────────────────


class _FlakyPlugin(NodePlugin):
    PLUGIN_ID = "flaky-test"
    connect_results: list[bool] = []

    async def connect(self, node, config, context):
        ok = self.connect_results.pop(0)
        return ok, "" if ok else "unreachable"

    async def disconnect(self, node):
        pass

    async def telemetry_stream(self, node):
        while True:
            yield TelemetryFrame(node_id=node.id)
            await asyncio.sleep(0.05)

    async def get_safe_state(self, node):
        return CommandResult(success=True)


@pytest.mark.asyncio
async def test_link_lost_events_and_auto_reconnect(monkeypatch):
    registry_module = sys.modules["henosync.core.node_registry"]
    monkeypatch.setattr(registry_module, "AUTO_RECONNECT_INTERVAL", 0.1)
    monkeypatch.setattr(registry_module, "LIVENESS_CHECK_INTERVAL", 10.0)

    events = []

    async def on_event(event):
        events.append(event)

    telemetry_bus.subscribe_events(on_event)
    plugin_registry._plugins["flaky-test"] = _FlakyPlugin

    registry = NodeRegistry()
    node = _onboard_node()
    node.plugin_id = "flaky-test"
    node.status = NodeStatus.ONLINE
    registry._nodes[node.id] = node
    statuses = []  # status transitions (listeners also fire on every telemetry frame)
    registry.add_listener(
        lambda n: statuses.append(n.status) if not statuses or statuses[-1] != n.status else None
    )

    # First retry fails (stays DEGRADED, no event), second succeeds.
    _FlakyPlugin.connect_results = [False, True]
    await registry._update_status(node, NodeStatus.DEGRADED)
    await asyncio.sleep(0.5)

    try:
        assert node.status == NodeStatus.ONLINE
        assert statuses == [NodeStatus.DEGRADED, NodeStatus.ONLINE]
        titles = [e.title for e in events]
        assert titles[0] == "Link Lost — Failsafe"
        assert "onboard controller" in events[0].message
        assert "Link Restored" in titles
        assert "Connection Failed" not in titles
        assert node.id not in registry._reconnect_tasks
    finally:
        await registry._disconnect_node(node)
        plugin_registry._plugins.pop("flaky-test", None)
        telemetry_bus.unsubscribe_events(on_event)
