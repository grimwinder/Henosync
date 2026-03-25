from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum
from datetime import datetime
import uuid


class NodeStatus(str, Enum):
    CONNECTING = "connecting"
    ONLINE = "online"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    ERROR = "error"


class Position(BaseModel):
    lat: float = 0.0
    lon: float = 0.0
    alt: float = 0.0


class NodeCapability(BaseModel):
    id: str
    label: str
    params: list[str] = []
    destructive: bool = False


class Node(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    plugin_id: str
    status: NodeStatus = NodeStatus.OFFLINE
    position: Position = Field(default_factory=Position)
    battery_percent: Optional[float] = None
    signal_strength: Optional[float] = None
    capabilities: list[NodeCapability] = []
    telemetry: dict[str, Any] = {}
    last_seen: Optional[datetime] = None
    home_position: Optional[Position] = None
    config: dict[str, Any] = {}


class NodeCreate(BaseModel):
    name: str
    plugin_id: str
    config: dict[str, Any] = {}


class NodeUpdate(BaseModel):
    name: Optional[str] = None
    config: Optional[dict[str, Any]] = None