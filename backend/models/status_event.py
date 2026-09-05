"""StatusEvent: one entry in an application's status history.

A single `status` column answers "where is this now" but erases how it got
there — advance to an interview, then get rejected, and the status reads
"rejected", indistinguishable from a straight rejection. This table keeps the
history: one row per status change, so the detail page can show the path.

A row is written wherever the status changes — creating the application (its
first status, with from_status null), a manual change, and accepting an email
suggestion — so the history is complete no matter how the change happened.

Cascade mirrors resume_versions: an application's history is meaningless once the
application is gone, so `cascade="all, delete-orphan"` on the parent deletes
these with it (SQLAlchemy deletes them explicitly, which stays portable to
SQLite in tests, unlike a DB-only ON DELETE).
"""

import enum
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.application import ApplicationStatus


class StatusEventSource(str, enum.Enum):
    """How the change was made. (str, enum.Enum) so members ARE strings, like
    the other enums, so what gets stored is exactly the value."""

    manual = "manual"  # a person: created the row, or changed it in the UI
    email = "email"  # applied by accepting a Gmail status suggestion


class StatusEvent(Base):
    __tablename__ = "status_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # Plain FK (no ON DELETE): the parent's cascade relationship deletes these
    # explicitly, matching how resume_versions is handled.
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), nullable=False
    )

    # Null marks the FIRST status (the application was created at it), so the UI
    # can say "Added as Discovered" rather than "— → Discovered".
    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        SqlEnum(ApplicationStatus), nullable=True
    )
    to_status: Mapped[ApplicationStatus] = mapped_column(
        SqlEnum(ApplicationStatus), nullable=False
    )

    source: Mapped[StatusEventSource] = mapped_column(
        SqlEnum(StatusEventSource),
        default=StatusEventSource.manual,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        frm = self.from_status.value if self.from_status else "new"
        return f"<StatusEvent {frm} -> {self.to_status.value} ({self.source.value})>"
