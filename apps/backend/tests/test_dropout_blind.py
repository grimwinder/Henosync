"""
Operator link dropout (Test 2): Henosync goes blind to the robot — no VICON
position while the link is dropped — and learns the path it took from the
robot's own log once it reconnects.
"""

import asyncio

import pytest

from henosync.core import run_recorder as run_recorder_module
from henosync.core import vicon_manager as vicon_module
from henosync.core.node_registry import NodeRegistry, node_registry
from henosync.core.telemetry_bus import telemetry_bus
from henosync.models import Node, NodeStatus


class _FakeViconClient:
    def GetFrame(self):  # noqa: N802 — mirrors the VICON SDK
        return True

    def GetSubjectNames(self):  # noqa: N802 — mirrors the VICON SDK
        return ["seen", "hidden"]

    def GetSubjectRootSegmentName(self, name):  # noqa: N802 — mirrors the VICON SDK
        return name

    def GetSegmentGlobalTranslation(self, name, segment):  # noqa: N802 — mirrors the VICON SDK
        return (1500.0, -500.0, 0.0), False

    def GetSegmentGlobalRotationEulerXYZ(self, name, segment):  # noqa: N802 — mirrors the VICON SDK
        return (0.0, 0.0, 0.5), False


def _vicon_node(name: str) -> Node:
    node = Node(
        name=name, plugin_id="jackal",
        config={"position_source": "vicon", "vicon_object_name": name},
    )
    node.status = NodeStatus.ONLINE
    return node


@pytest.mark.asyncio
async def test_vicon_skips_robot_while_link_dropped(monkeypatch):
    seen, hidden = _vicon_node("seen"), _vicon_node("hidden")
    hidden.link_blocked = True
    monkeypatch.setattr(node_registry, "_nodes", {seen.id: seen, hidden.id: hidden})

    frames = []

    async def on_frame(frame):
        frames.append(frame.node_id)

    manager = vicon_module.VICONManager()
    manager._saved_host = "vicon-pc"
    manager._clients["vicon-pc"] = _FakeViconClient()
    manager._running = True
    telemetry_bus.subscribe_telemetry(on_frame)
    task = asyncio.create_task(manager._run())
    try:
        await asyncio.sleep(0.2)
        assert seen.telemetry.get("vicon_x") == 1.5
        assert seen.id in frames

        assert "vicon_x" not in hidden.telemetry
        assert hidden.id not in frames

        hidden.link_blocked = False  # Restore Link
        await asyncio.sleep(0.2)
        assert hidden.telemetry.get("vicon_x") == 1.5
    finally:
        manager._running = False
        await task
        telemetry_bus.unsubscribe_telemetry(on_frame)


@pytest.mark.asyncio
async def test_robot_log_offline_samples_sent_to_map(monkeypatch):
    monkeypatch.setattr(
        run_recorder_module.run_recorder, "record_robot_log", lambda *a: None
    )
    frames = []

    async def on_frame(frame):
        frames.append(frame)

    def sample(x, link, pose_ok=True):
        return {"kind": "sample", "x": x, "y": -x, "link": link, "pose_ok": pose_ok}

    records = [
        sample(0.0, True),
        {"kind": "link_lost"},
        sample(1.0, False), sample(2.0, False),
        sample(9.0, False, pose_ok=False),  # stale pose — not drawn
        {"kind": "link_restored"},
        sample(3.0, True),
        sample(4.0, False), sample(5.0, False),  # second dropout
    ]
    telemetry_bus.subscribe_telemetry(on_frame)
    try:
        NodeRegistry()._handle_robot_log("run-1", "node-1", records)
        await asyncio.sleep(0.05)
    finally:
        telemetry_bus.unsubscribe_telemetry(on_frame)

    assert len(frames) == 1
    assert frames[0].node_id == "node-1"
    assert frames[0].custom["offline_path"] == [
        [[1.0, -1.0], [2.0, -2.0]],
        [[4.0, -4.0], [5.0, -5.0]],
    ]


@pytest.mark.asyncio
async def test_robot_log_while_connected_sends_nothing(monkeypatch):
    monkeypatch.setattr(
        run_recorder_module.run_recorder, "record_robot_log", lambda *a: None
    )
    frames = []

    async def on_frame(frame):
        frames.append(frame)

    telemetry_bus.subscribe_telemetry(on_frame)
    try:
        NodeRegistry()._handle_robot_log(
            "run-1", "node-1",
            [{"kind": "sample", "x": 1.0, "y": 1.0, "link": True, "pose_ok": True}],
        )
        await asyncio.sleep(0.05)
    finally:
        telemetry_bus.unsubscribe_telemetry(on_frame)
    assert frames == []
