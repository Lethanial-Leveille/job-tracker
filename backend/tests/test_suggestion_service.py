"""Tests for reviewing status suggestions: list, accept, dismiss.

The webhook/ingest side is covered elsewhere; these exercise the resolve half,
where the one status-writing action in the whole pipeline lives. The cases that
matter: accepting applies the status to the right application and nowhere else,
an ambiguous/unmatched suggestion refuses to apply without a valid choice, and
everything stays scoped to the owner.
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from models.application import Application, ApplicationStatus, ApplicationType
from models.ingested_email import IngestedEmail
from models.status_suggestion import StatusSuggestion, SuggestionState
from models.user import User
from services.status_suggestion import (
    accept_suggestion,
    dismiss_suggestion,
    list_pending_suggestions,
)


def _app(db: Session, user_id: str, org: str = "Neighbor") -> Application:
    row = Application(
        user_id=user_id,
        type=ApplicationType.internship,
        organization=org,
        role_or_program="SWE Intern",
        posting_url="https://example.com/job",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _email(db: Session, user_id: str) -> IngestedEmail:
    row = IngestedEmail(
        user_id=user_id,
        message_id="msg-1",
        received_at=datetime.now(UTC),
        from_email="no-reply@hire.lever.co",
        from_name="Neighbor",
        subject="Thanks for applying",
        snippet="We received your application.",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _suggestion(
    db: Session,
    user_id: str,
    email_id: str,
    *,
    application_id: str | None = None,
    candidate_application_ids: list | None = None,
    suggested_status: ApplicationStatus = ApplicationStatus.applied,
    state: SuggestionState = SuggestionState.pending,
) -> StatusSuggestion:
    row = StatusSuggestion(
        user_id=user_id,
        application_id=application_id,
        candidate_application_ids=candidate_application_ids,
        suggested_status=suggested_status,
        reason="Confirmation from Neighbor",
        source_email_id=email_id,
        state=state,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_list_returns_only_pending_with_email(db: Session, user: User) -> None:
    email = _email(db, user.id)
    app = _app(db, user.id)
    _suggestion(db, user.id, email.id, application_id=app.id)
    _suggestion(
        db, user.id, email.id, application_id=app.id, state=SuggestionState.dismissed
    )

    rows = list_pending_suggestions(db, user.id)

    assert len(rows) == 1
    suggestion, joined_email = rows[0]
    assert suggestion.state == SuggestionState.pending
    assert joined_email.subject == "Thanks for applying"


def test_accept_resolved_applies_status(db: Session, user: User) -> None:
    email = _email(db, user.id)
    app = _app(db, user.id)
    assert app.status == ApplicationStatus.discovered
    suggestion = _suggestion(
        db, user.id, email.id, application_id=app.id,
        suggested_status=ApplicationStatus.applied,
    )

    result = accept_suggestion(db, user.id, suggestion.id, None)

    assert result is not None
    assert result.state == SuggestionState.accepted
    assert result.resolved_at is not None
    db.refresh(app)
    assert app.status == ApplicationStatus.applied


def test_accept_ambiguous_requires_a_candidate(db: Session, user: User) -> None:
    email = _email(db, user.id)
    app1 = _app(db, user.id, org="Neighbor A")
    app2 = _app(db, user.id, org="Neighbor B")
    suggestion = _suggestion(
        db, user.id, email.id,
        candidate_application_ids=[app1.id, app2.id],
        suggested_status=ApplicationStatus.rejected,
    )

    # A choice outside the candidate set is refused.
    with pytest.raises(ValueError):
        accept_suggestion(db, user.id, suggestion.id, "not-a-candidate")

    # The right candidate gets the status; it resolves to that application.
    result = accept_suggestion(db, user.id, suggestion.id, app2.id)
    assert result.application_id == app2.id
    db.refresh(app2)
    assert app2.status == ApplicationStatus.rejected
    db.refresh(app1)
    assert app1.status == ApplicationStatus.discovered  # untouched


def test_accept_unmatched_needs_a_target(db: Session, user: User) -> None:
    email = _email(db, user.id)
    suggestion = _suggestion(db, user.id, email.id)  # no app, no candidates

    with pytest.raises(ValueError):
        accept_suggestion(db, user.id, suggestion.id, None)


def test_accept_rejects_another_users_application(db: Session, user: User) -> None:
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.commit()
    db.refresh(other)
    their_app = _app(db, other.id)
    email = _email(db, user.id)
    suggestion = _suggestion(db, user.id, email.id)  # unmatched

    with pytest.raises(ValueError):
        accept_suggestion(db, user.id, suggestion.id, their_app.id)


def test_accept_unknown_suggestion_returns_none(db: Session, user: User) -> None:
    assert accept_suggestion(db, user.id, "nope", None) is None


def test_dismiss_marks_dismissed_without_touching_status(
    db: Session, user: User
) -> None:
    email = _email(db, user.id)
    app = _app(db, user.id)
    suggestion = _suggestion(db, user.id, email.id, application_id=app.id)

    result = dismiss_suggestion(db, user.id, suggestion.id)

    assert result.state == SuggestionState.dismissed
    assert result.resolved_at is not None
    db.refresh(app)
    assert app.status == ApplicationStatus.discovered  # untouched
