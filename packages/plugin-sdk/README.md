# henosync-plugin-sdk

Plugin development SDK for the Henosync open source robot fleet mission planner.

## Installation

```bash
pip install -e packages/plugin-sdk
```

## Quick Start

```python
import asyncio
from henosync_sdk import (
    NodePlugin, Node, TelemetryFrame, CommandResult,
    DeviceSpecs, DeviceCategory, DeviceCapability, CapabilitySpec,
)

class MyRobotPlugin(NodePlugin):
    PLUGIN_ID = "my-robot"
    PLUGIN_NAME = "My Robot"
    TELEMETRY_RATE_HZ = 1.0  # optional, default is 1.0

    async def connect(self, node: Node, config: dict) -> tuple[bool, str]:
        # Return (True, "") on success, (False, "reason") on failure
        node.specs = DeviceSpecs(
            category=DeviceCategory.AGV,
            capabilities=[CapabilitySpec(id="move_to", label="Move To", params=["lat", "lon", "alt"])],
        )
        return True, ""

    async def disconnect(self, node: Node) -> None:
        pass

    async def send_command(self, node: Node, capability: str, params: dict) -> CommandResult:
        return CommandResult(success=True)

    async def telemetry_stream(self, node: Node):
        while True:
            yield TelemetryFrame(node_id=node.id, values={
                "lat": 0.0,
                "lon": 0.0,
                "battery_percent": 100.0,
            })
            await asyncio.sleep(1.0 / self.TELEMETRY_RATE_HZ)

    async def get_safe_state(self, node: Node) -> CommandResult:
        # Stop the robot and return success/failure
        return CommandResult(success=True, message="Safe")
```

## Optional hooks

```python
    async def on_reconnect(self, node: Node, config: dict) -> tuple[bool, str]:
        # Called on manual reconnect instead of connect(); defaults to calling connect()
        return await self.connect(node, config)

    async def get_video_stream_url(self, node: Node) -> str | None:
        return None

    async def validate_config(self, config: dict) -> tuple[bool, str]:
        return True, ""

    async def on_mission_start(self, node: Node) -> None:
        pass

    async def on_mission_end(self, node: Node) -> None:
        pass
```

## Documentation

See `plugins/template/plugin.py` in the Henosync repository for a complete working example.
