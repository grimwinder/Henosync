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


class TelemetryFrame(BaseModel):
    node_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    values: dict[str, Any] = {}
    sequence_number: int = 0


class CommandResult(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = {}


class StepType(str, Enum):
    MOVE = "move"
    ACTION = "action"
    WAIT = "wait"
    CONDITION = "condition"
    PARALLEL = "parallel"
    LOOP = "loop"
    WAIT_FOR = "wait_for"


class MissionStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class FailsafeConfig(BaseModel):
    on_node_lost: str = "pause"
    on_low_battery: str = "return_home"
    low_battery_threshold: float = 20.0


class MissionStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_type: StepType
    label: str = ""
    target_node_id: Optional[str] = None
    parameters: dict[str, Any] = {}


class Mission(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    steps: list[MissionStep] = []
    failsafe: FailsafeConfig = Field(default_factory=FailsafeConfig)
    metadata: dict[str, Any] = {}