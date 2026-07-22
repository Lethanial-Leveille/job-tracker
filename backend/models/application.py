"""The Application model: one table for internships and scholarships.

One row per application, distinguished by the `type` column. Enums are defined
here alongside the model so the Pydantic schemas (piece 3) can import the exact
same value sets and validate against them.
"""

import enum
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, Enum as SqlEnum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


# --- Enums -------------------------------------------------------------------
# Each inherits (str, enum.Enum) so members ARE strings — convenient for JSON
# serialization and so name == value (no surprise about what gets stored).


class ApplicationType(str, enum.Enum):
    internship = "internship"
    scholarship = "scholarship"


class ApplicationStatus(str, enum.Enum):
    # The v1 pipeline, a superset of both types. No transition validation in v1
    # — any status can move to any other. That state machine is v2.
    #
    # Trimmed from the original 16: `shortlisted` (covered by priority) and
    # `applied_confirmed` (a v4 n8n-automation concern) were dropped for v1.
    discovered = "discovered"
    drafting = "drafting"
    ready = "ready"
    applied = "applied"
    recruiter_engaged = "recruiter_engaged"
    phone_screen = "phone_screen"
    technical_interview = "technical_interview"
    onsite = "onsite"
    offer = "offer"
    accepted = "accepted"
    declined = "declined"
    rejected = "rejected"
    ghosted = "ghosted"
    missed_deadline = "missed_deadline"


class Priority(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"


# --- Model -------------------------------------------------------------------


class Application(Base):
    __tablename__ = "applications"

    # UUID as a 36-char string. Generated on insert; never passed in by hand.
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # Enum columns: stored as VARCHAR plus a CHECK constraint in SQLite, so the
    # database itself rejects any value outside the enum.
    type: Mapped[ApplicationType] = mapped_column(
        SqlEnum(ApplicationType), nullable=False
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        SqlEnum(ApplicationStatus),
        default=ApplicationStatus.discovered,
        nullable=False,
    )
    priority: Mapped[Priority] = mapped_column(
        SqlEnum(Priority), default=Priority.medium, nullable=False
    )

    # Required identifying fields.
    organization: Mapped[str] = mapped_column(String(255), nullable=False)
    role_or_program: Mapped[str] = mapped_column(String(255), nullable=False)
    posting_url: Mapped[str] = mapped_column(String(2048), nullable=False)

    # Optional fields.
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Parser output home. Empty in v1 (no JD parsing yet); filled in v2.
    jd_parsed: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # The raw pasted job description text. Kept so resume tailoring can run
    # against the real posting from a saved application. Distinct from jd_parsed
    # (parser *output*): this is the parser *input*, and unlike jd_parsed it is
    # re-settable via update (you can paste a JD onto an app created by hand).
    jd_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps, always UTC. updated_at re-stamps on every modification via
    # the onupdate hook.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<Application {self.id} {self.type.value} "
            f"{self.organization!r} status={self.status.value}>"
        )
