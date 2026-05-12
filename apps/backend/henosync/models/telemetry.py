from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TelemetryFrame(BaseModel):
    node_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    node_id: Optional[str] = None
    acknowledged: bool = False


class CommandResult(BaseModel):
    success: bool
    message: str = ""
    data: dict[str, Any] = {}
