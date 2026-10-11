"""
A robot whose own link has died must trip the failsafe even while VICON
can still see it. VICON updates position only — never the heartbeat.
"""

from datetime import datetime, timedelta, timezone

import pytest
from henosync_sdk import Node

from henosync.core.failsafe_manager import HEARTBEAT_TIMEOUT, failsafe_manager
from henosync.core.node_registry import node_registry
from henosync.core.vicon_manager import vicon_manager
from henosync.models import NodeStatus


class _FakeViconClient:
    """Minimal stand-in for the VICON DataStream SDK client."""

    def GetSubjectRootSegmentName(self, name):  # noqa: N802 — SDK naming
        return name

    def GetSegmentGlobalTranslation(self, name, segment):  # noqa: N802
        return (1500.0, -2500.0, 0.0), False  # millimetres, not occluded

    def GetSegmentGlobalRotationEulerXYZ(self, name, segment):  # noqa: N802
        return (0.0, 0.0, 0.5), False


def _vicon_node(last_seen: datetime) -> Node:
    return Node(
        name="Jackal",
        plugin_id="jackal",
        status=NodeStatus.DEGRADED,  # rosbridge already reported dead
        config={"position_source": "vicon", "vicon_object_name": "jackal"},
        last_seen=last_seen,
    )


@pytest.mark.asyncio
async def test_vicon_update_moves_robot_but_not_heartbeat():
    stale = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT + 5)
    node = _vicon_node(stale)

    await vicon_manager._update_node(_FakeViconClient(), node)

    assert node.telemetry["vicon_x"] == pytest.approx(1.5)
    assert node.telemetry["vicon_y"] == pytest.approx(-2.5)
    assert node.last_seen == stale  # heartbeat untouched


@pytest.mark.asyncio
async def test_failsafe_fires_while_vicon_still_sees_robot(monkeypatch):
    stale = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT + 5)
    node = _vicon_node(stale)

    lost: list[str] = []

    async def fake_on_node_lost(n):
        lost.append(n.id)

    monkeypatch.setattr(failsafe_manager, "_on_node_lost", fake_on_node_lost)
    monkeypatch.setattr(node_registry, "_nodes", {node.id: node})
    failsafe_manager._triggered.clear()

    await vicon_manager._update_node(_FakeViconClient(), node)  # VICON still live
    await failsafe_manager._check_all_nodes()

    assert lost == [node.id]
    failsafe_manager._triggered.clear()
