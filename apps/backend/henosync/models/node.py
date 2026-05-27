from typing import Any, Optional

from henosync_sdk.models import (
    BatteryData,
    CameraFeed,
    CapabilityRequirement,
    CapabilitySpec,
    CommandEnvelope,
    CommandType,
    DeviceCapability,
    DeviceCategory,
    DeviceSpecs,
    GPSData,
    IMUData,
    LidarPoint,
    LidarScan,
    LocalOrigin,
    Node,
    NodeCapability,
    NodePluginContext,
    NodeStatus,
    Position,
)
from pydantic import BaseModel

# Re-export everything so existing imports from henosync.models still work.
__all__ = [
    "Node", "NodeStatus", "NodeCapability", "Position", "LocalOrigin",
    "DeviceCategory", "DeviceCapability", "DeviceSpecs",
    "CapabilitySpec", "CapabilityRequirement",
    "GPSData", "IMUData", "LidarPoint", "LidarScan", "CameraFeed", "BatteryData",
    "CommandType", "CommandEnvelope", "NodePluginContext",
    "NodeCreate", "NodeUpdate",
]


# ── Backend-only types (API layer) ────────────────────────────────────────────

class NodeCreate(BaseModel):
    name: str
    plugin_id: str
    config: dict[str, Any] = {}


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None
