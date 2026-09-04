"""The StatusSuggestion model: a proposed status change, staged for review.

This is the "propose, never decide" half of the Gmail ingestion pipeline. A
confirmation email never writes to an application's status. It stages a row
here, the UI surfaces it, and one click accepts or dismisses it.

The reason is asymmetry of harm. A missed suggestion costs nothing: the status
stays where it would have been if the feature did not exist. A wrong automatic
flip is invisible — a row silently marked Applied that never was, discovered
when a deadline passes. So the design refuses to guess, and where it cannot
resolve an email to exactly one application it stages the candidates instead.

Deliberately NOT rebuilt here: the `applied_confirmed` status that
docs/decisions.md said to re-add "with that automation". The status list was
just cut from fourteen to six because there were too many to work with, and a
confirmed application is the same state as an applied one. The confirmation
email is PROVENANCE, recorded on this row via source_email_id, not a new stage
in the pipeline.
"""

import enum
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Enum as SqlEnum,
    ForeignKey,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base
from models.application import ApplicationStatus


class SuggestionState(str, enum.Enum):
    """Where a suggestion is in its short life.

    (str, enum.Enum) so members ARE strings, matching the enums in
    models/application.py — convenient for JSON and no surprise about what gets
    stored.
    """

    pending = "pending"
    accepted = "accepted"
    dismissed = "dismissed"


class StatusSuggestion(Base):
    __tablename__ = "status_suggestions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # The proposed target, and NULLABLE on purpose — this is what makes "propose,
    # never decide" structural rather than a rule the code has to remember.
    #
    # Null means the email could not be resolved to exactly one application:
    # either nothing matched, or several did (two roles at one company, where
    # neither the plausible-transition filter nor the role hint could separate
    # them). A suggestion with no target physically cannot flip a status. The
    # column enforces the policy instead of relying on a service to honor it.
    # ondelete="SET NULL", NOT cascade: this column is already nullable because
    # null means "could not be resolved to one application", and a deleted
    # application lands a suggestion in exactly that state. The inbound email is
    # still real evidence that arrived, so it survives as an unresolved
    # suggestion rather than disappearing with the row it happened to point at.
    # Without an explicit rule Postgres defaults to NO ACTION, which would block
    # the delete the same way resume_versions did.
    application_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("applications.id", ondelete="SET NULL"),
        nullable=True,
    )

    # The shortlist when application_id is null: the application ids that
    # survived narrowing, for the UI to render as a row of buttons.
    #
    # A JSON list of ids rather than a join table because it is never queried
    # across — it is read whole, with the row, and thrown away when the
    # suggestion resolves. Same call as the other JSON columns in this codebase.
    # No tiebreaker is applied before storing these: resolving two candidates by
    # something like "most recently updated" would be right about half the time,
    # and being wrong here is the invisible failure this table exists to avoid.
    candidate_application_ids: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )

    # Reuses the SAME enum the applications table stores, not a parallel set of
    # strings. Accepting a suggestion writes this value straight through, so a
    # value that could not be a real status must be unrepresentable here.
    suggested_status: Mapped[ApplicationStatus] = mapped_column(
        SqlEnum(ApplicationStatus), nullable=False
    )

    # Human-readable justification, e.g. "Confirmation from Neighbor, Sep 3".
    # Written by the ingestion service, shown verbatim in the UI. The snippet on
    # the source email is the underlying evidence; this is the one-line summary.
    reason: Mapped[str] = mapped_column(String(500), nullable=False)

    # Provenance: the email that produced this. This is where a confirmation
    # lives instead of in an `applied_confirmed` status, and it is what makes a
    # surprising suggestion traceable back to the message that caused it.
    source_email_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("ingested_emails.id"), nullable=False
    )

    state: Mapped[SuggestionState] = mapped_column(
        SqlEnum(SuggestionState),
        default=SuggestionState.pending,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    # Null until accepted or dismissed. Resolved rows are KEPT rather than
    # deleted: whether suggestions get accepted or dismissed is the only honest
    # signal about whether the matching rule actually works, and dismissals
    # clustering on one sender is exactly how you would find out it does not.
    # Storage is free at this volume.
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    def __repr__(self) -> str:
        target = self.application_id or f"{len(self.candidate_application_ids or [])} candidates"
        return (
            f"<StatusSuggestion {self.id} -> {self.suggested_status.value} "
            f"({target}) state={self.state.value}>"
        )
