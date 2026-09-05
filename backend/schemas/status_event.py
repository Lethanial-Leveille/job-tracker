"""API shape for a status-history entry (the application timeline)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from models.application import ApplicationStatus
from models.status_event import StatusEventSource


class StatusEventRead(BaseModel):
    # from_attributes so a StatusEvent ORM row serializes straight through.
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_status: ApplicationStatus | None = None
    to_status: ApplicationStatus
    source: StatusEventSource
    created_at: datetime
