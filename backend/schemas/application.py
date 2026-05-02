from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, HttpUrl

ApplicationType = Literal["internship", "scholarship", "fellowship", "research", "grant"]
ApplicationStatus = Literal[
    "discovered", "shortlisted", "drafting", "ready", "applied",
    "applied_confirmed", "recruiter_engaged", "phone_screen", "technical_interview",
    "onsite", "offer", "accepted", "declined", "rejected", "ghosted", "missed_deadline",
]
ApplicationPriority = Literal["top_target", "standard", "longshot"]


class ApplicationCreate(BaseModel):
    """What the client sends to POST /applications. Just enough to get started."""
    posting_url: HttpUrl
    type: ApplicationType
    organization: str
    role_or_program: str
    deadline: datetime | None = None
    priority: ApplicationPriority | None = None
    notes: str | None = None


class ApplicationUpdate(BaseModel):
    """What the client sends to PATCH /applications/{id}. All fields optional."""
    status: ApplicationStatus | None = None
    priority: ApplicationPriority | None = None
    notes: str | None = None
    deadline: datetime | None = None


class ApplicationResponse(BaseModel):
    """What every endpoint returns. Includes server-set fields."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    organization: str
    role_or_program: str
    posting_url: str | None
    deadline: datetime | None
    status: str
    priority: str | None
    jd_text: str | None
    jd_parsed: dict[str, Any] | None
    match_score: int | None
    match_explanation: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
