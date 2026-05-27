import uuid
from datetime import datetime, timezone
from typing import Optional

from henosync_sdk.models import CommandResult, EventSeverity, TelemetryFrame
from pydantic import BaseModel, Field

# Re-export so existing imports from henosync.models still work.
__all__ = [
    "TelemetryFrame", "CommandResult", "EventSeverity",
    "SystemEvent",
]


# ── Backend-only types ────────────────────────────────────────────────────────

class SystemEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    severity: EventSeverity
    title: str
    message: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    node_id: Optional[str] = None
    acknowledged: bool = False
