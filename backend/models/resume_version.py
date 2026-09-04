"""The ResumeVersion model: one saved, tailored resume for one application.

A row here is a snapshot: the tailored `Resume` (as JSON) that you reviewed and
explicitly chose to keep for a specific job, plus the job description it was
tailored against. Tailoring itself stays stateless (POST /resume/tailor just
drafts); saving is a separate, deliberate act (hard rule #1, nothing is kept
without your say-so). Re-tailoring and saving again makes a *new* row, so this
table is append-only history per application.

New concept vs the Application model: a FOREIGN KEY. `application_id` holds the
id of the applications row this version belongs to, and ForeignKey records that
link in the schema. (SQLite only enforces foreign keys with a pragma we haven't
set, so for now the constraint is declared but not database-enforced — fine for
single-user v1.)
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class ResumeVersion(Base):
    __tablename__ = "resume_versions"

    # Same UUID-as-36-char-string pattern as Application. Generated on insert.
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # The owner. Same users.id FK as Application. A version is owned by the same
    # user as the application it belongs to.
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # The link to the application this version was tailored for. String(36) to
    # match applications.id; the ForeignKey names the target column.
    #
    # ondelete="CASCADE" because a saved version is meaningless without the
    # posting it was tailored against, and without it the database REFUSES the
    # delete: every application you had ever saved a resume for became
    # undeletable with an opaque 500. The cascade lives on the CONSTRAINT rather
    # than only in the ORM so it holds for any caller, including a migration or
    # a psql session that never loads these classes.
    application_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("applications.id", ondelete="CASCADE"),
        nullable=False,
    )

    # The tailored resume itself, stored as the dict from Resume.model_dump().
    # Read back with Resume.model_validate(). Same JSON column type as
    # Application.jd_parsed.
    resume_json: Mapped[dict] = mapped_column(JSON, nullable=False)

    # Snapshot of the job description this version targeted — an honest record of
    # what it was tailored against, even if the application's JD later changes.
    job_description: Mapped[str] = mapped_column(Text, nullable=False)

    # Created only — a saved version is an immutable snapshot, so no updated_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<ResumeVersion {self.id} application_id={self.application_id} "
            f"created_at={self.created_at.isoformat()}>"
        )
