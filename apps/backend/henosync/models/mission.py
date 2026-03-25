from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum
from datetime import datetime
import uuid


class StepType(str, Enum):
    MOVE = "move"
    ACTION = "action"
    WAIT = "wait"
    CONDITION = "condition"
    PARALLEL = "parallel"
    LOOP = "loop"           # NEW
    WAIT_FOR = "wait_for"   # NEW


class StepStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ConditionOperator(str, Enum):
    GREATER_THAN = "gt"
    LESS_THAN = "lt"
    EQUALS = "eq"
    NOT_EQUALS = "neq"


class Condition(BaseModel):
    telemetry_key: str
    operator: ConditionOperator
    value: float
    node_id: str


class MissionStep(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    step_type: StepType
    label: str = ""
    target_node_id: Optional[str] = None
    parameters: dict[str, Any] = {}
    status: StepStatus = StepStatus.PENDING
    on_complete: Optional[str] = None
    on_fail: Optional[str] = None
    condition: Optional[Condition] = None
    then_step_id: Optional[str] = None
    else_step_id: Optional[str] = None
    parallel_step_ids: list[str] = []
    loop_step_ids: list[str] = []
    loop_count: Optional[int] = None        
    loop_condition: Optional[Condition] = None 
    wait_for_condition: Optional[Condition] = None
    wait_for_timeout_seconds: float = 30.0 


class FailsafeAction(str, Enum):
    ABORT = "abort"
    PAUSE = "pause"
    CONTINUE = "continue"
    RETURN_HOME = "return_home"


class FailsafeConfig(BaseModel):
    on_node_lost: FailsafeAction = FailsafeAction.PAUSE
    on_low_battery: FailsafeAction = FailsafeAction.RETURN_HOME
    low_battery_threshold: float = 20.0


class MissionStatus(str, Enum):
    DRAFT = "draft"
    READY = "ready"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class Mission(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: MissionStatus = MissionStatus.DRAFT
    steps: list[MissionStep] = []
    failsafe: FailsafeConfig = Field(default_factory=FailsafeConfig)
    metadata: dict[str, Any] = {}


class MissionCreate(BaseModel):
    name: str
    steps: list[MissionStep] = []
    failsafe: FailsafeConfig = Field(default_factory=FailsafeConfig)
    metadata: dict[str, Any] = {}


class MissionUpdate(BaseModel):
    name: Optional[str] = None
    steps: Optional[list[MissionStep]] = None
    failsafe: Optional[FailsafeConfig] = None
    metadata: Optional[dict[str, Any]] = None