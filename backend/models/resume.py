"""The MasterResume model: one user's master resume, stored in the database.

Until now a master resume was a YAML file on disk (`backend/data/master_resume.yaml`)
— fine when there was exactly one user (me). Going multi-user means each person
needs their own master, and a non-technical user can't edit YAML, so the master
moves into the database where a builder UI can read and write it.

Storage choice (see docs/decisions.md, v1 data-model rule): the whole resume is
kept as ONE JSON blob, not split into education/experience/projects tables. A
resume is a document you always load and save *whole* — you never query across
its insides ("find users whose 3rd bullet says Python" is not a thing) — so
normalizing it into many tables would be pure overhead. Same call, same reason,
as `ResumeVersion.resume_json` and `Application.jd_parsed`.

The `Resume` Pydantic model in schemas/resume.py stays the single source of
truth for the *shape* of that JSON. This model is only the row that HOLDS it —
which is why it's named MasterResume, not Resume, so the two never collide when
both are imported together.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class MasterResume(Base):
    __tablename__ = "resumes"

    # Same UUID-as-36-char-string pattern as every other table. Generated on
    # insert, never passed in by hand.
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # The owner. Same users.id FK as Application and ResumeVersion — BUT here it
    # is unique=True. That is the key difference: ResumeVersion is many-per-user
    # (append-only history of tailored snapshots); a master resume is exactly
    # ONE per user. Making the column unique lets the database itself guarantee
    # that, which is what lets get_master() safely use scalar_one_or_none() and
    # upsert_master() trust there's never a second row to reconcile. Same
    # mechanism as User.email being unique.
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), unique=True, nullable=False
    )

    # The resume itself, stored as the dict from Resume.model_dump() and read
    # back with Resume.model_validate(). Same JSON column type as
    # ResumeVersion.resume_json.
    resume_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Both timestamps, unlike ResumeVersion. A saved version is an immutable
    # snapshot (created only); the master is the opposite — the builder edits it
    # constantly — so it's mutable and re-stamps updated_at on every save via the
    # onupdate hook, exactly like Application.
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
        return f"<MasterResume {self.id} user_id={self.user_id}>"
