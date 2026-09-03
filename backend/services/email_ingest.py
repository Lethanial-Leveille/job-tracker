"""Gmail ingestion: an email in, a staged suggestion out.

The heart of the pipeline, and the only place that decides anything. Classifying
extracts facts (services/email_classify.py); this module turns facts into a
proposal, and refuses to turn them into an action.

THE GOVERNING RULE: PROPOSE, NEVER DECIDE
------------------------------------------
Nothing here writes to an application's status. Everything becomes a
StatusSuggestion for a human to accept in one click. The reason is asymmetry of
harm: a missed suggestion costs nothing (the status stays where it would have
been without the feature), while a wrong automatic flip is INVISIBLE — a row
silently marked Applied that never was, discovered when the deadline passes. So
where an email cannot be resolved to exactly one application, this code stages
the candidates rather than guessing between them.

WHY THERE IS NO CURSOR, AND WHAT THAT DEMANDS
----------------------------------------------
n8n re-sends a rolling two day window on every run and tracks nothing. A cursor
could advance past messages whose POST failed, losing mail permanently and
silently; a rolling window cannot. The cost is that duplicates are guaranteed,
which puts two requirements on this module:

1. An email is recorded as seen ONLY after it classifies successfully. A
   classification failure records nothing, so the next poll redelivers it. The
   overlap window IS the retry mechanism — there is no sweep job anywhere.
2. Duplicate delivery must be free and safe. A cheap SELECT skips the paid model
   call in the common case, and the unique constraint on
   (user_id, message_id) closes the race the SELECT cannot: see the note in
   models/ingested_email.py.

Each message commits independently. A failure on one must not roll back the nine
that already succeeded in the same batch.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parseaddr
from typing import Literal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import Settings
from models.application import Application, ApplicationStatus
from models.ingested_email import IngestedEmail
from models.status_suggestion import StatusSuggestion, SuggestionState
from schemas.email import EmailClassification, IncomingEmail
from services.email_classify import classify_email
from services.text_match import normalize_organization, role_similarity

logger = logging.getLogger(__name__)

# Same cutoff findSimilarPosting uses in frontend/src/lib/dedupe.ts. Kept equal
# on purpose: a pair of titles the UI calls "probably the same posting" and this
# code calls "different jobs" would be indefensible to explain.
_ROLE_MATCH_THRESHOLD = 0.7

# Statuses before an application goes out the door, and statuses for one in
# flight. Mirrors isPreSubmit in frontend/src/components/applications/statuses.ts.
_PRE_SUBMIT = frozenset(
    {
        ApplicationStatus.discovered,
        ApplicationStatus.drafting,
        ApplicationStatus.ready,
    }
)
_IN_FLIGHT = frozenset(
    {
        ApplicationStatus.applied,
        ApplicationStatus.recruiter_engaged,
        ApplicationStatus.phone_screen,
        ApplicationStatus.technical_interview,
        ApplicationStatus.onsite,
    }
)

# What each kind of email proposes, and which CURRENT statuses it may act on.
#
# The eligibility half is the first and strongest narrowing step, and it does
# more work than it looks like. A confirmation only makes sense for a row not yet
# applied; a rejection only for one already out. That alone separates two rows at
# the same company most of the time, because they are rarely in the same state.
#
# It also prevents nonsense: a rejection for an already-rejected row produces
# nothing rather than a redundant suggestion to dismiss.
#
# "interview_invite" proposes phone_screen, the EARLIEST interview stage, and is
# eligible only from applied/recruiter_engaged. So an invite arriving when the
# row already sits at phone_screen or later produces no suggestion instead of
# proposing a backwards step — a snippet cannot tell a first screen from a third
# round, so the conservative answer is to stay quiet.
#
# "other" is deliberately absent: no transition, no suggestion.
_TRANSITIONS: dict[str, tuple[ApplicationStatus, frozenset[ApplicationStatus]]] = {
    "application_received": (ApplicationStatus.applied, _PRE_SUBMIT),
    "rejection": (ApplicationStatus.rejected, _IN_FLIGHT),
    "interview_invite": (
        ApplicationStatus.phone_screen,
        frozenset({ApplicationStatus.applied, ApplicationStatus.recruiter_engaged}),
    ),
    "offer": (ApplicationStatus.offer, _IN_FLIGHT),
}

_KIND_LABEL = {
    "application_received": "Confirmation",
    "rejection": "Rejection",
    "interview_invite": "Interview invite",
    "offer": "Offer",
}

IngestResult = Literal[
    "duplicate",  # already seen; no work done, no call spent
    "not_classified",  # model gave nothing; NOT recorded, will be redelivered
    "no_action",  # recorded, but nothing to propose
    "suggested",  # one application matched
    "ambiguous",  # several matched; candidates staged for a human to pick
    "unmatched",  # no application matched
]


@dataclass(frozen=True)
class IngestOutcome:
    """What happened to one message. Returned rather than logged so the webhook
    can answer with a summary and tests can assert on the decision."""

    message_id: str
    result: IngestResult
    suggestion_id: str | None = None


def parse_sender(from_raw: str) -> tuple[str | None, str]:
    """Split a From header into (display name, address).

    Uses the standard library rather than a regex: '"Smith, Jane" <j@x.com>' has
    a comma inside a quoted name, and hand-rolled splitting gets it wrong. An
    empty display name becomes None, since a bare address is a legitimate header.
    """
    name, address = parseaddr(from_raw)
    return (name.strip() or None), address.strip()


def received_at_from_ms(internal_date_ms: int) -> datetime:
    """Gmail's epoch milliseconds to an aware UTC datetime."""
    return datetime.fromtimestamp(internal_date_ms / 1000, UTC)


def _already_seen(db: Session, user_id: str, message_id: str) -> bool:
    """Cheap pre-check so a redelivered message costs no model call.

    This is an OPTIMIZATION, not the correctness guarantee. Two overlapping
    requests can both pass it and both proceed; the unique constraint is what
    actually stops the second insert. Never rely on this alone.
    """
    stmt = select(IngestedEmail.id).where(
        IngestedEmail.user_id == user_id,
        IngestedEmail.message_id == message_id,
    )
    return db.execute(stmt).first() is not None


def _candidates(
    db: Session, user_id: str, organization: str
) -> list[Application]:
    """The user's applications at this employer.

    Filtered in Python rather than SQL because normalize_organization is not
    expressible as a WHERE clause, and a stored normalized column would be a
    second source of truth to keep in sync. At this scale (tens of rows) loading
    the user's applications is cheaper than that complexity. Revisit if the
    pipeline ever reaches thousands.
    """
    key = normalize_organization(organization)
    if not key:
        return []
    rows = db.execute(
        select(Application).where(Application.user_id == user_id)
    ).scalars()
    return [a for a in rows if normalize_organization(a.organization) == key]


def narrow(
    candidates: list[Application], kind: str, role_hint: str | None
) -> list[Application]:
    """Reduce candidates to those an email could plausibly refer to.

    Two steps, in this order, and then it STOPS:

    1. Plausible transition — only rows whose current status this kind of email
       can act on.
    2. Role hint — only when a hint exists AND more than one row survived step 1.
       Used to break a tie, never to widen the field. If the hint matches none of
       them, the step is abandoned rather than returning nothing: a title that
       fits no candidate is weak evidence, not proof of absence.

    There is deliberately NO third tiebreaker. Something like "most recently
    updated" would resolve two rows at one company by coin flip and be right
    about half the time, and being wrong here is the invisible failure this whole
    design exists to avoid. Two buttons in the UI beats a wrong guess.
    """
    transition = _TRANSITIONS.get(kind)
    if transition is None:
        return []
    _, eligible = transition

    survivors = [a for a in candidates if a.status in eligible]

    if len(survivors) > 1 and role_hint:
        by_role = [
            a
            for a in survivors
            if role_similarity(a.role_or_program, role_hint) >= _ROLE_MATCH_THRESHOLD
        ]
        if by_role:
            survivors = by_role

    return survivors


def _reason(
    classification: EmailClassification,
    from_name: str | None,
    from_email: str,
    received_at: datetime,
) -> str:
    """The one-line justification shown beside a suggestion.

    Names the sender the way it appeared, so a surprising suggestion is
    traceable to the message without opening Gmail. The snippet on the linked
    email is the underlying evidence; this is the summary.
    """
    label = _KIND_LABEL.get(classification.kind, "Email")
    sender = from_name or from_email
    # Avoids %-d, which is not portable off Linux/macOS.
    when = f"{received_at:%b} {received_at.day}"
    return f"{label} from {sender}, {when}"


def _has_pending_suggestion(
    db: Session, user_id: str, application_id: str, status: ApplicationStatus
) -> bool:
    """Whether an identical proposal is already waiting.

    Companies routinely send both "we received your application" and a follow-up
    confirmation, and the two day window can redeliver either. Without this you
    get several identical rows to dismiss, which trains you to dismiss without
    reading — the exact habit that makes a wrong suggestion dangerous.
    """
    stmt = select(StatusSuggestion.id).where(
        StatusSuggestion.user_id == user_id,
        StatusSuggestion.application_id == application_id,
        StatusSuggestion.suggested_status == status,
        StatusSuggestion.state == SuggestionState.pending,
    )
    return db.execute(stmt).first() is not None


def ingest_message(
    db: Session,
    user_id: str,
    message: IncomingEmail,
    settings: Settings,
) -> IngestOutcome:
    """Process one message end to end, committing or rolling back on its own.

    Self-contained transactions on purpose: one bad message in a batch of ten
    must not undo the nine that worked.
    """
    from_name, from_email = parse_sender(message.from_raw)
    received_at = received_at_from_ms(message.internal_date_ms)

    if _already_seen(db, user_id, message.message_id):
        return IngestOutcome(message.message_id, "duplicate")

    # Classify BEFORE recording. A None here must leave no trace, so the next
    # poll redelivers the message and tries again.
    classification = classify_email(
        subject=message.subject,
        from_name=from_name,
        from_email=from_email,
        snippet=message.snippet,
        settings=settings,
    )
    if classification is None:
        logger.warning("Not classified, will retry: %s", message.message_id)
        return IngestOutcome(message.message_id, "not_classified")

    email_row = IngestedEmail(
        user_id=user_id,
        message_id=message.message_id,
        thread_id=message.thread_id,
        received_at=received_at,
        from_email=from_email,
        from_name=from_name,
        subject=message.subject,
        snippet=message.snippet,
        classification=classification.model_dump(),
    )
    db.add(email_row)
    try:
        # Flush rather than commit so the insert hits the unique constraint now,
        # while the suggestion below can still join the same transaction.
        db.flush()
    except IntegrityError:
        # The race the pre-check cannot close: a concurrent delivery inserted
        # this message between our SELECT and our INSERT. Already handled by
        # whoever won, so this is a normal outcome, not an error.
        db.rollback()
        return IngestOutcome(message.message_id, "duplicate")

    transition = _TRANSITIONS.get(classification.kind)
    if transition is None or not classification.organization:
        # Recorded anyway: it classified fine, there is simply nothing to
        # propose. Keeping the row means the next poll will not pay to
        # classify this same message again.
        db.commit()
        return IngestOutcome(message.message_id, "no_action")

    suggested_status, _ = transition
    survivors = narrow(
        _candidates(db, user_id, classification.organization),
        classification.kind,
        classification.role_hint,
    )
    reason = _reason(classification, from_name, from_email, received_at)

    if len(survivors) == 1:
        target = survivors[0]
        if _has_pending_suggestion(db, user_id, target.id, suggested_status):
            db.commit()
            return IngestOutcome(message.message_id, "no_action")
        suggestion = StatusSuggestion(
            user_id=user_id,
            application_id=target.id,
            suggested_status=suggested_status,
            reason=reason,
            source_email_id=email_row.id,
        )
        result: IngestResult = "suggested"
    else:
        # Zero or several. Either way application_id stays NULL, which is what
        # makes it impossible for this suggestion to flip a status on its own.
        suggestion = StatusSuggestion(
            user_id=user_id,
            application_id=None,
            candidate_application_ids=[a.id for a in survivors],
            suggested_status=suggested_status,
            reason=reason,
            source_email_id=email_row.id,
        )
        result = "ambiguous" if survivors else "unmatched"

    db.add(suggestion)
    db.commit()
    return IngestOutcome(message.message_id, result, suggestion.id)


def ingest_messages(
    db: Session,
    user_id: str,
    messages: list[IncomingEmail],
    settings: Settings,
) -> list[IngestOutcome]:
    """Process a batch, one independent transaction per message.

    An unexpected exception on one message is caught and reported rather than
    aborting the batch: the message simply goes unrecorded, and the overlap
    window brings it back on the next poll.
    """
    outcomes: list[IngestOutcome] = []
    for message in messages:
        try:
            outcomes.append(ingest_message(db, user_id, message, settings))
        except Exception:
            db.rollback()
            logger.exception("Ingestion failed for %s", message.message_id)
            outcomes.append(IngestOutcome(message.message_id, "not_classified"))
    return outcomes
