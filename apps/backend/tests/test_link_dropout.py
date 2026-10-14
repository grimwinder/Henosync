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


@pytest.mark.asyncio
async def test_operator_drop_holds_link_down_until_restore(monkeypatch):
    registry_module = sys.modules["henosync.core.node_registry"]
    monkeypatch.setattr(registry_module, "AUTO_RECONNECT_INTERVAL", 0.05)
    monkeypatch.setattr(registry_module, "LIVENESS_CHECK_INTERVAL", 10.0)

    events = []

    async def on_event(event):
        events.append(event.title)

    telemetry_bus.subscribe_events(on_event)
    plugin_registry._plugins["flaky-test"] = _FlakyPlugin
    registry = NodeRegistry()
    node = _onboard_node()
    node.plugin_id = "flaky-test"
    node.status = NodeStatus.ONLINE
    registry._nodes[node.id] = node
    _FlakyPlugin.connect_results = [True]

    try:
        await registry.drop_link(node.id)
        assert node.status == NodeStatus.DEGRADED and node.link_blocked
        await asyncio.sleep(0.4)  # several auto-reconnect intervals
        assert node.status == NodeStatus.DEGRADED, "auto-reconnect must wait for restore"
        assert _FlakyPlugin.connect_results == [True]

        await registry.restore_link(node.id)
        assert node.status == NodeStatus.ONLINE and not node.link_blocked
        assert events[:2] == ["Link Dropout Simulated", "Link Lost — Failsafe"]
        assert "Link Restore Requested" in events and "Link Restored" in events
        with pytest.raises(ValueError):
            await registry.restore_link(node.id)  # nothing to restore
    finally:
        await registry._disconnect_node(node)
        plugin_registry._plugins.pop("flaky-test", None)
        telemetry_bus.unsubscribe_events(on_event)


# -- Robot log: the real henosync_controller.py talking to the Jackal plugin --


class _Clock:
    def __init__(self):
        self.now = 1000.0

    def monotonic(self):
        return self.now

    def time(self):
        return self.now + 1_700_000_000.0


def _load_controller(tmp_path, clock):
    """henosync_controller.py with rclpy and the ROS message types stubbed out."""
    import types
    from types import SimpleNamespace

    class Msg:
        def __init__(self):
            self.data = None
            self.x = self.y = self.theta = 0.0
            self.linear = SimpleNamespace(x=0.0, y=0.0, z=0.0)
            self.angular = SimpleNamespace(x=0.0, y=0.0, z=0.0)

    class Pub:
        def __init__(self):
            self.sent = []

        def publish(self, msg):
            self.sent.append(msg)

    class StubNode:
        def __init__(self, name):
            self.subs, self.pubs = {}, {}

        def create_subscription(self, _type, topic, cb, _qos):
            self.subs[topic] = cb

        def create_publisher(self, _type, topic, _qos):
            self.pubs[topic] = Pub()
            return self.pubs[topic]

        def create_timer(self, _period, _cb):
            return None

        def get_logger(self):
            import logging
            return logging.getLogger("henosync_controller")

    stubs = {
        "rclpy": types.ModuleType("rclpy"),
        "rclpy.node": types.ModuleType("rclpy.node"),
        "geometry_msgs": types.ModuleType("geometry_msgs"),
        "geometry_msgs.msg": types.ModuleType("geometry_msgs.msg"),
        "std_msgs": types.ModuleType("std_msgs"),
        "std_msgs.msg": types.ModuleType("std_msgs.msg"),
    }
    stubs["rclpy.node"].Node = StubNode
    for name in ("Pose2D", "Twist", "TwistStamped"):
        setattr(stubs["geometry_msgs.msg"], name, Msg)
    for name in ("Bool", "String"):
        setattr(stubs["std_msgs.msg"], name, Msg)
    saved = {k: sys.modules.get(k) for k in stubs}
    sys.modules.update(stubs)
    try:
        spec = importlib.util.spec_from_file_location(
            "henosync_controller_under_test", REPO / "tools/robot/henosync_controller.py"
        )
        ctrl = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ctrl)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    ctrl.LOG_DIR = str(tmp_path / "henosync_logs")
    ctrl.time = clock
    return ctrl, Msg


@pytest.fixture
def clean_robot_log():
    jackal._LOG_CURSORS.clear()
    yield
    jackal._LOG_CURSORS.clear()
    jackal._PATHS.clear()


@pytest.mark.asyncio
async def test_robot_log_survives_dropout_and_holds_step_open(
    fast_timing, clean_robot_log, tmp_path
):
    clock = _Clock()
    ctrl_mod, msg_type = _load_controller(tmp_path, clock)
    robot = ctrl_mod.HenosyncController("j100", "/j100/cmd_vel", "/j100/henosync/onboard_pose", True)

    node = _onboard_node()
    stored: list[dict] = []
    acks: list[str] = []
    waypoints: list = []

    class Ctx:
        def active_run_id(self):
            return "run-1"

        def record_robot_log(self, run_id, records):
            assert run_id == "run-1"
            stored.extend(records)

    def instance():
        p = _connected_instance(node, waypoints)
        p._context = Ctx()
        p._loop = asyncio.get_running_loop()
        p._nodes[node.id].robot_log_ack_pub = object()
        p._publish_string = lambda _topic, data: acks.append(data)
        return p

    def msg(data):
        m = msg_type()
        m.data = data
        return m

    def ticks(n=1, dt=0.1):
        for _ in range(n):
            clock.now += dt
            robot._control_tick()

    def pose(x, y):
        m = msg_type()
        m.x, m.y, m.theta = x, y, 0.0
        robot.subs["/j100/henosync/onboard_pose"](m)

    async def exchange(plugin, progress=True, log=True):
        """One round of robot -> Henosync -> robot traffic over a live link."""
        if progress:
            robot._publish_progress()
            for m in robot.pubs["/j100/henosync/progress"].sent:
                plugin._on_progress(node.id, {"data": m.data})
            robot.pubs["/j100/henosync/progress"].sent.clear()
        if log:
            robot._send_log()
            for m in robot.pubs["/j100/henosync/robot_log"].sent:
                plugin._on_robot_log(node.id, {"data": m.data})
            robot.pubs["/j100/henosync/robot_log"].sent.clear()
            await asyncio.sleep(0.01)  # let the call_soon_threadsafe ingest run
            for a in acks:
                robot.subs["/j100/henosync/robot_log_ack"](msg(a))
            acks.clear()

    old = instance()
    robot.subs["/j100/henosync/heartbeat"](msg("{}"))
    pose(0.0, 0.0)

    path = [{"x": 1.0, "y": 0.0}, {"x": 2.0, "y": 0.0}]
    task = asyncio.create_task(old.cmd_follow_path(node, path))
    await asyncio.sleep(0.05)
    robot.subs["/j100/henosync/waypoint"](msg(json.dumps(waypoints[0])))
    ticks(5)
    await exchange(old)
    assert not robot._unacked, "records sent while the link is up are acknowledged"

    # -- Link drops: no heartbeat, nothing crosses rosbridge --
    await old.disconnect(node)
    ticks(25)  # 2.5 s > LINK_TIMEOUT_S
    for x in (0.5, 1.0, 1.5, 2.0):  # the robot drives both waypoints on its own
        pose(x, 0.0)
        ticks(5)
    assert not robot._active, "path finished while disconnected"
    offline = list(robot._unacked)
    kinds = [r["kind"] for r in offline]
    assert "link_lost" in kinds and kinds.count("waypoint") == 2 and "path_done" in kinds
    assert any(r["kind"] == "sample" and r["v"] > 0 and r["link"] is False for r in offline)
    await asyncio.sleep(0.5)
    assert not task.done(), "Henosync keeps waiting through the dropout"

    # -- Reconnect: new plugin instance; progress says done before the log lands --
    new = instance()
    robot.subs["/j100/henosync/heartbeat"](msg("{}"))
    await exchange(new, progress=True, log=False)
    await asyncio.sleep(0.5)
    assert not task.done(), "the step waits for the robot's log of the path"

    await exchange(new, progress=False, log=True)
    result = await asyncio.wait_for(task, 2.0)
    assert result.success and result.message == "Arrived"
    assert not robot._unacked

    seqs = [r["seq"] for r in stored]
    assert seqs == list(range(1, len(seqs) + 1)), "every record exactly once, in order"
    got = [r["kind"] for r in stored]
    assert got.index("link_lost") < got.index("path_done") < got.index("link_restored")
    late = [r for r in stored if r["kind"] == "path_done"][0]
    assert late["link"] is False and "recv" in late and "sent" in late

    # A duplicate re-send after reconnect is ignored.
    new._ingest_robot_log(node.id, {"boot": robot._boot, "records": offline}, 0.0)
    assert len(stored) == len(seqs)
    # The robot also kept everything on disk.
    robot._log_file.close()
    disk = list((tmp_path / "henosync_logs").glob("*.jsonl"))
    assert sum(1 for f in disk for _ in f.open()) == len(seqs)


def test_robot_log_gap_waits_for_resend(clean_robot_log):
    node = _onboard_node()
    stored: list = []
    plugin = jackal.JackalPlugin()

    class Ctx:
        def active_run_id(self):
            return "run-1"

        def record_robot_log(self, run_id, records):
            stored.extend(r["seq"] for r in records)

    plugin._context = Ctx()

    def rec(n):
        return {"seq": n, "t": float(n), "kind": "sample", "run_id": "run-1"}

    plugin._ingest_robot_log(node.id, {"boot": "b1", "records": [rec(1), rec(2)]}, 0.0)
    plugin._ingest_robot_log(node.id, {"boot": "b1", "records": [rec(4)]}, 0.0)  # 3 lost
    assert stored == [1, 2]
    plugin._ingest_robot_log(node.id, {"boot": "b1", "records": [rec(3), rec(4)]}, 0.0)
    assert stored == [1, 2, 3, 4]
    # Controller restarted: a new boot id starts a new sequence.
    plugin._ingest_robot_log(node.id, {"boot": "b2", "records": [rec(1)]}, 0.0)
    assert stored == [1, 2, 3, 4, 1]
