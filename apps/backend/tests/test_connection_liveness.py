"""
Dropout detection and reconnection behaviour (Results use cases 2 and 6).

Documents what node_registry guarantees, using a fake device plugin:
- a dead link is detected and the node goes DEGRADED
- there is NO automatic reconnection (deliberate design choice)
- a manual reconnect brings the node back ONLINE
"""

import asyncio
import sys

import pytest
from henosync_sdk import CommandResult, Node, NodePlugin, TelemetryFrame

from henosync.core.node_registry import node_registry
from henosync.models import NodeStatus
from henosync.plugin_system.registry import plugin_registry

LIVENESS_INTERVAL = 0.05

# henosync.core re-exports the singleton under the module's name, so fetch
# the module itself to patch its constant.
node_registry_module = sys.modules["henosync.core.node_registry"]


class FakeLinkPlugin(NodePlugin):
    PLUGIN_ID = "fake-link"
    TELEMETRY_RATE_HZ = 50.0

    # Shared across instances so the test can cut the "link" for whichever
    # instance node_registry created.
    link_up = True
    connects = 0

    def __init__(self) -> None:
        super().__init__()
        self._nodes: set[str] = set()

    async def connect(self, node, config, context):
        FakeLinkPlugin.connects += 1
        if not FakeLinkPlugin.link_up:
            return False, "link down"
        self._nodes.add(node.id)
        return True, ""

    async def disconnect(self, node):
        self._nodes.discard(node.id)

    async def is_connected(self, node) -> bool:
        return FakeLinkPlugin.link_up

    async def telemetry_stream(self, node):
        seq = 0
        while node.id in self._nodes:
            yield TelemetryFrame(node_id=node.id, sequence_number=seq, status_text="ok")
            seq += 1
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    async def get_safe_state(self, node):
        return CommandResult(success=True, message="stopped")


async def _wait_for_status(node: Node, status: NodeStatus, timeout: float) -> float:
    """Seconds until node reaches status; raises on timeout."""
    loop = asyncio.get_running_loop()
    start = loop.time()
    while node.status != status:
        if loop.time() - start > timeout:
            raise AssertionError(f"{node.name} still {node.status}, expected {status}")
        await asyncio.sleep(0.01)
    return loop.time() - start


@pytest.fixture
def fake_node(monkeypatch):
    monkeypatch.setattr(node_registry_module, "LIVENESS_CHECK_INTERVAL", LIVENESS_INTERVAL)
    plugin_registry.register(FakeLinkPlugin.PLUGIN_ID, FakeLinkPlugin, {"id": "fake-link"})
    FakeLinkPlugin.link_up = True
    FakeLinkPlugin.connects = 0

    node = Node(name="FakeBot", plugin_id=FakeLinkPlugin.PLUGIN_ID)
    node_registry._nodes[node.id] = node
    yield node

    node_registry._nodes.pop(node.id, None)
    plugin_registry._plugins.pop(FakeLinkPlugin.PLUGIN_ID, None)
    plugin_registry._manifests.pop(FakeLinkPlugin.PLUGIN_ID, None)


@pytest.mark.asyncio
async def test_dead_link_detected_then_stays_down_until_manual_reconnect(fake_node):
    await node_registry._connect_node(fake_node)
    assert fake_node.status == NodeStatus.ONLINE

    # Cut the link: detected within ~one liveness interval.
    FakeLinkPlugin.link_up = False
    detect_s = await _wait_for_status(fake_node, NodeStatus.DEGRADED, timeout=1.0)
    assert detect_s < LIVENESS_INTERVAL * 4

    # Restore the link: nothing reconnects on its own.
    FakeLinkPlugin.link_up = True
    connects_before = FakeLinkPlugin.connects
    await asyncio.sleep(LIVENESS_INTERVAL * 10)
    assert fake_node.status == NodeStatus.DEGRADED
    assert FakeLinkPlugin.connects == connects_before

    # Manual reconnect (the Reconnect button / POST /api/nodes/{id}/reconnect).
    assert await node_registry.reconnect_node(fake_node.id)
    await _wait_for_status(fake_node, NodeStatus.ONLINE, timeout=1.0)

    await node_registry._disconnect_node(fake_node)


@pytest.mark.asyncio
async def test_manual_reconnect_while_link_still_down_reports_error(fake_node):
    await node_registry._connect_node(fake_node)
    FakeLinkPlugin.link_up = False
    await _wait_for_status(fake_node, NodeStatus.DEGRADED, timeout=1.0)

    assert await node_registry.reconnect_node(fake_node.id)
    await _wait_for_status(fake_node, NodeStatus.ERROR, timeout=1.0)
