# henosync-plugin-sdk

Plugin development SDK for the Henosync open source robot fleet mission planner.

## Installation

```bash
pip install henosync-plugin-sdk
```

## Quick Start

```python
from henosync_sdk import NodePlugin, Node, TelemetryFrame, CommandResult

class MyRobotPlugin(NodePlugin):
    PLUGIN_ID = "my-robot"
    PLUGIN_NAME = "My Robot"

    async def connect(self, node, config):
        # Connect to your robot here
        return True

    async def disconnect(self, node):
        pass

    async def send_command(self, node, capability, params):
        return CommandResult(success=True)

    async def telemetry_stream(self, node):
        while True:
            yield TelemetryFrame(node_id=node.id, values={})
            await asyncio.sleep(1.0)

    async def get_safe_state(self, node):
        return CommandResult(success=True, message="Safe")
```

## Documentation

Full plugin developer guide available at:
https://github.com/henosync/henosync/docs
