"""The Application model: one table for internships and scholarships.

One row per application, distinguished by the `type` column. Enums are defined
here alongside the model so the Pydantic schemas (piece 3) can import the exact
same value sets and validate against them.
"""

import enum
from datetime import UTC, date, datetime
from uuid import uuid4

from sqlalchemy import JSON, Date, DateTime, Enum as SqlEnum, ForeignKey, String, Text
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

    # The owner. Foreign key to users.id, mirroring resume_version's FK. Every
    # application belongs to exactly one user (non-null is the end state; the
    # migration backfills existing rows before enforcing it).
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
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

    # The normalized role, e.g. "Software Engineer Intern". Postings title the
    # same job fourteen different ways ("Summer 2027 Intern - Software Engineer",
    # "Software Engineer, Internship", "Engineering Internship"), which makes the
    # list unreadable at a glance; the parser picks one of a fixed set of values
    # and this holds it, while role_or_program keeps the real posted title.
    #
    # Deliberately a plain VARCHAR, NOT a SqlEnum like type/status/priority: the
    # set of role families is expected to change as Lee applies to new kinds of
    # roles, and adding a value to a native Postgres enum needs an ALTER TYPE
    # migration (see docs/decisions.md, the v3 enum gotcha). The allowed values
    # are enforced at the API boundary by the Pydantic Literal instead, so adding
    # one is a code change rather than a schema migration.
    #
    # Nullable because every row predating this column has no value, and because
    # a posting that fits nothing sensible is better left empty than force-fit.
    role_family: Mapped[str | None] = mapped_column(String(64), nullable=True)
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

    # The requirement-match report (schemas/fit.py), cached here after it is
    # computed. Same JSON-blob call as jd_parsed and MasterResume.resume_json:
    # it is a document read and written whole, never queried across its insides.
    #
    # A CACHE, not a record: recomputing overwrites it. That is fine because the
    # report is a pure function of this posting's requirements and your master
    # resume as it stands, so an old one has no value once the master changes.
    # fit_computed_at is what makes staleness visible — the master is edited
    # constantly, and a report from before an edit may no longer be true.
    fit_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    fit_computed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )

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
