from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum
from datetime import datetime


class TelemetryFrame(BaseModel):
    node_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    values: dict[str, Any] = {}
    sequence_number: int = 0


class EventSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class SystemEvent(BaseModel):
    id: str
    severity: EventSeverity
    title: str
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    node_id: Optional[str] = None
    acknowledged: bool = False


class CommandResult(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = {}