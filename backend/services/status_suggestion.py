"""Reviewing staged status suggestions: list, accept, dismiss.

The read/resolve half of the Gmail pipeline. The webhook stages suggestions
(services/email_ingest.py); this is where a human acts on them. Accepting is the
ONLY thing that writes a status change from an email — and only because a person
clicked it, which is the whole "propose, never decide" point (see
models/status_suggestion.py).

HTTP-ignorant like every service: it returns rows or None, or raises ValueError
for a bad target; the router maps those to status codes.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.application import Application, ApplicationType
from models.ingested_email import IngestedEmail
from models.status_event import StatusEventSource
from models.status_suggestion import StatusSuggestion, SuggestionState
from services.status_event import record_status_event


def list_pending_suggestions(
    db: Session, user_id: str
) -> list[tuple[StatusSuggestion, IngestedEmail]]:
    """Pending suggestions for a user, newest first, each with its email.

    Inner join is safe: source_email_id is a non-null FK, so every suggestion
    has exactly one ingested email behind it.
    """
    stmt = (
        select(StatusSuggestion, IngestedEmail)
        .join(IngestedEmail, StatusSuggestion.source_email_id == IngestedEmail.id)
        .where(
            StatusSuggestion.user_id == user_id,
            StatusSuggestion.state == SuggestionState.pending,
        )
        .order_by(StatusSuggestion.created_at.desc())
    )
    return [(s, e) for s, e in db.execute(stmt).all()]


def _get_pending(
    db: Session, user_id: str, suggestion_id: str
) -> StatusSuggestion | None:
    # Scoped by owner and to pending only: another user's suggestion is invisible
    # (route 404s), and an already-resolved one can't be resolved twice.
    stmt = select(StatusSuggestion).where(
        StatusSuggestion.id == suggestion_id,
        StatusSuggestion.user_id == user_id,
        StatusSuggestion.state == SuggestionState.pending,
    )
    return db.execute(stmt).scalar_one_or_none()


def accept_suggestion(
    db: Session,
    user_id: str,
    suggestion_id: str,
    chosen_application_id: str | None,
) -> StatusSuggestion | None:
    """Apply a suggestion's status to its application. Returns None if not found.

    Resolving the target mirrors the three staged shapes:
    - resolved (application_id set): apply straight through, ignore any choice.
    - ambiguous (candidate ids): the choice must be one of the candidates.
    - unmatched (neither): the choice may be any application the user owns.
    A bad or missing choice raises ValueError (the route maps it to 400).
    """
    suggestion = _get_pending(db, user_id, suggestion_id)
    if suggestion is None:
        return None

    if suggestion.application_id is not None:
        target_id = suggestion.application_id
    elif suggestion.candidate_application_ids:
        if chosen_application_id not in suggestion.candidate_application_ids:
            raise ValueError("Choose one of the candidate applications to accept.")
        target_id = chosen_application_id
    else:
        if not chosen_application_id:
            raise ValueError(
                "This suggestion matched no application; choose one to apply it to."
            )
        target_id = chosen_application_id

    # Scoped fetch: you can only apply a suggestion to your own application.
    application = db.execute(
        select(Application).where(
            Application.id == target_id, Application.user_id == user_id
        )
    ).scalar_one_or_none()
    if application is None:
        raise ValueError("Application not found.")

    old_status = application.status
    application.status = suggestion.suggested_status
    # A status history entry, tagged as coming from an email, so the timeline
    # shows the interview/rejection that arrived in the inbox. Only when it
    # actually changed (accepting a suggestion for the status it's already at is
    # a no-op worth no event).
    if application.status != old_status:
        record_status_event(
            db,
            user_id=user_id,
            application_id=application.id,
            from_status=old_status,
            to_status=application.status,
            source=StatusEventSource.email,
        )
    # Record which application it resolved to (matters for ambiguous/unmatched,
    # where application_id was null until now) and close the suggestion out.
    suggestion.application_id = target_id
    suggestion.state = SuggestionState.accepted
    suggestion.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def create_application_from_suggestion(
    db: Session, user_id: str, suggestion_id: str
) -> Application | None:
    """Create a new application from an (unmatched) suggestion's email, then
    accept it. For when you applied somewhere that was never in the tracker: the
    email carries the employer, the role, and the implied status, so we capture
    those and you fill in the URL / deadline / JD later. Returns None if the
    suggestion isn't found.

    Built directly rather than through ApplicationCreate because that schema
    requires a non-empty posting_url, which an email doesn't provide — the row
    starts with an empty URL you add when you have it.
    """
    suggestion = _get_pending(db, user_id, suggestion_id)
    if suggestion is None:
        return None

    email = db.get(IngestedEmail, suggestion.source_email_id)
    classification = (email.classification or {}) if email else {}
    org = (classification.get("organization") or "").strip()
    if not org and email is not None:
        org = (email.from_name or email.from_email or "").strip()
    role = (classification.get("role_hint") or "").strip()

    application = Application(
        user_id=user_id,
        type=ApplicationType.internship,
        organization=(org or "Unknown employer")[:255],
        role_or_program=(role or "Role from email")[:255],
        posting_url="",  # no URL in an email; add it later
        status=suggestion.suggested_status,
    )
    db.add(application)
    db.flush()  # assign id before recording the opening history entry

    record_status_event(
        db,
        user_id=user_id,
        application_id=application.id,
        from_status=None,
        to_status=application.status,
        source=StatusEventSource.email,
    )

    suggestion.application_id = application.id
    suggestion.state = SuggestionState.accepted
    suggestion.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(application)
    return application


def dismiss_suggestion(
    db: Session, user_id: str, suggestion_id: str
) -> StatusSuggestion | None:
    """Mark a suggestion dismissed without touching any application. None if not found."""
    suggestion = _get_pending(db, user_id, suggestion_id)
    if suggestion is None:
        return None
    suggestion.state = SuggestionState.dismissed
    suggestion.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(suggestion)
    return suggestion
