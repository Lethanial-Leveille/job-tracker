"""The IngestedEmail model: one Gmail message that has been seen and classified.

This table is the dedupe ledger for the Gmail ingestion pipeline, and it is what
makes the whole retry design safe. n8n on the Raspberry Pi polls Gmail on a
schedule and POSTs everything from the last two days on EVERY run, with no
cursor tracking which messages it already sent. That design was chosen because a
cursor can advance past messages whose POST failed, losing mail permanently and
silently. The cost of dropping the cursor is that duplicates are guaranteed, and
this table is what absorbs them.

Two things are load-bearing:

1. The unique constraint on (user_id, message_id). See the note on it below.
2. A row here is the "already seen" marker, so it is inserted only AFTER the
   message classifies successfully. A classification failure records nothing,
   which means the next poll redelivers that message and tries again. The
   overlap window IS the retry mechanism, so there is no sweep job or dead
   letter queue anywhere in this design.

Note what is NOT stored: the message body. The Gmail node runs with Simplify on
and returns only `snippet`, roughly the first 200 characters, which already
carries the kind, the organization, and the role. Never fetching the full body
means no base64 multipart decoding, far less sensitive data crossing from the Pi
to the droplet, and nothing weighty at rest (hard rule #5). The snippet itself IS
kept, because it is the evidence behind a staged suggestion — "propose, never
decide" only works if the proposal can actually be judged.
"""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class IngestedEmail(Base):
    __tablename__ = "ingested_emails"

    # The unique constraint is the idempotency guarantee, and it lives on the
    # DATABASE rather than as a "look it up, insert if absent" check in the
    # service. The difference matters because of a race the overlap window makes
    # likely rather than rare:
    #
    #   Request A:  SELECT ... WHERE message_id='18f2a'  -> no rows
    #   Request B:  SELECT ... WHERE message_id='18f2a'  -> no rows  (A uncommitted)
    #   Request A:  INSERT -> ok
    #   Request B:  INSERT -> ok
    #
    # Two rows, two paid model calls, two identical suggestions to dismiss. The
    # gap between the SELECT and the INSERT is the whole problem, and its being
    # NARROW makes it worse, not better: it will not appear in testing and will
    # appear under exactly the retry storm this pipeline is built to invite.
    #
    # A unique constraint closes it because the database makes the check and the
    # write one atomic operation. The second INSERT cannot succeed; it raises
    # IntegrityError, which the ingestion service catches and treats as "already
    # seen, skip" — the correct outcome, not an error condition.
    #
    # Keyed on (user_id, message_id) rather than message_id alone: Gmail ids are
    # unique per mailbox, not globally, so two users could legitimately hold the
    # same id.
    __table_args__ = (
        UniqueConstraint(
            "user_id", "message_id", name="uq_ingested_email_user_message"
        ),
    )

    # Same UUID-as-36-char-string pattern as every other table.
    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid4())
    )

    # The owner, resolved from the `mailbox` field on the webhook payload. The
    # service token authenticates the MACHINE (n8n has no user), so the mailbox
    # address is what names which user's rows this message may touch.
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id"), nullable=False
    )

    # Gmail's own immutable id for the message. The dedupe key.
    message_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Gmail's conversation id. Nothing reads it yet, and it is kept anyway
    # because it is free now and expensive to backfill later: a rejection
    # arriving in the same thread as a confirmation we already matched
    # identifies the application outright, with no organization matching at all.
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # When GMAIL received it, converted on arrival from the `internalDate` epoch
    # milliseconds the API returns. Not when we ingested it — a message
    # redelivered by the overlap window must not appear to have arrived twice.
    received_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    # Sender, split on arrival from the raw "Neighbor <no-reply@hire.lever.co>"
    # header using email.utils.parseaddr. Split on the droplet rather than in
    # n8n so the parsing is standard-library-correct on quoted display names and
    # testable in this repo, and so n8n stays pure plumbing.
    #
    # 320 is the RFC 5321 maximum length of an email address; 255 is a practical
    # cap on a display name. from_name is nullable because a bare address with
    # no display name is a legitimate From header.
    from_email: Mapped[str] = mapped_column(String(320), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 998 is the RFC 5322 maximum line length, so it is the honest ceiling for a
    # single header value.
    subject: Mapped[str | None] = mapped_column(String(998), nullable=True)

    # Gmail's preview text: the classifier's main input, and the evidence shown
    # on the staged suggestion so a proposal can be judged without opening
    # Gmail. Gmail caps this near 200 characters; 500 leaves headroom.
    snippet: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # What the classifier extracted, as the dict from a Pydantic model_dump().
    # Same JSON-blob call as Application.jd_parsed and ResumeVersion.resume_json:
    # a document read and written whole, never queried across its insides.
    #
    # Per the stored-JSON rule in CLAUDE.md, every field on the Pydantic model
    # that validates this column needs a default — rows written today are read
    # back through tomorrow's schema forever.
    classification: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Created only. An ingested message is an immutable record of something that
    # already happened, so there is no updated_at — same reasoning as
    # ResumeVersion.
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(UTC), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<IngestedEmail {self.id} message_id={self.message_id!r} "
            f"from={self.from_email!r}>"
        )
