"""Tests for the status history: an event is recorded at every change and only
at a change, and it dies with the application.

The point of the feature is that "interviewed, then rejected" leaves a trail,
so the coverage that matters is: creation writes an opening event, a status
change writes one (a non-status edit does not), accepting a suggestion writes an
email-sourced one, and deleting the application takes its history with it.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from models.application import ApplicationStatus, ApplicationType
from models.ingested_email import IngestedEmail
from models.status_event import StatusEventSource
from models.status_suggestion import StatusSuggestion, SuggestionState
from models.user import User
from schemas.application import ApplicationCreate, ApplicationUpdate
from services.application import (
    create_application,
    delete_application,
    update_application,
)
from services.status_event import delete_status_event, list_status_events
from services.status_suggestion import accept_suggestion


def _new_application(db: Session, user_id: str):
    data = ApplicationCreate(
        type=ApplicationType.internship,
        organization="Neighbor",
        role_or_program="SWE Intern",
        posting_url="https://example.com/job",
    )
    return create_application(db, data, user_id)


def test_create_records_opening_event(db: Session, user: User) -> None:
    app = _new_application(db, user.id)
    events = list_status_events(db, app.id, user.id)
    assert len(events) == 1
    assert events[0].from_status is None  # marks the first status
    assert events[0].to_status == ApplicationStatus.discovered
    assert events[0].source == StatusEventSource.manual


def test_status_change_records_event(db: Session, user: User) -> None:
    app = _new_application(db, user.id)
    update_application(
        db, ApplicationUpdate(status=ApplicationStatus.applied), app.id, user.id
    )
    events = list_status_events(db, app.id, user.id)
    assert len(events) == 2  # opening + the change
    assert events[-1].from_status == ApplicationStatus.discovered
    assert events[-1].to_status == ApplicationStatus.applied
    assert events[-1].source == StatusEventSource.manual


def test_non_status_edit_records_nothing(db: Session, user: User) -> None:
    app = _new_application(db, user.id)
    update_application(db, ApplicationUpdate(notes="a note"), app.id, user.id)
    assert len(list_status_events(db, app.id, user.id)) == 1  # only the opening


def test_accept_suggestion_records_email_event(db: Session, user: User) -> None:
    app = _new_application(db, user.id)
    email = IngestedEmail(
        user_id=user.id,
        message_id="m1",
        received_at=datetime.now(UTC),
        from_email="no-reply@hire.lever.co",
    )
    db.add(email)
    db.commit()
    db.refresh(email)
    suggestion = StatusSuggestion(
        user_id=user.id,
        application_id=app.id,
        suggested_status=ApplicationStatus.phone_screen,
        reason="Interview invite from Neighbor",
        source_email_id=email.id,
        state=SuggestionState.pending,
    )
    db.add(suggestion)
    db.commit()

    accept_suggestion(db, user.id, suggestion.id, None)

    events = list_status_events(db, app.id, user.id)
    assert len(events) == 2  # opening + the accepted change
    assert events[-1].to_status == ApplicationStatus.phone_screen
    assert events[-1].source == StatusEventSource.email


def test_delete_takes_history_with_it(db: Session, user: User) -> None:
    app = _new_application(db, user.id)
    assert len(list_status_events(db, app.id, user.id)) == 1
    delete_application(db, app.id, user.id)
    assert list_status_events(db, app.id, user.id) == []


def test_delete_one_entry_prunes_only_it(db: Session, user: User) -> None:
    app = _new_application(db, user.id)
    update_application(
        db, ApplicationUpdate(status=ApplicationStatus.applied), app.id, user.id
    )
    events = list_status_events(db, app.id, user.id)
    assert len(events) == 2

    assert delete_status_event(db, events[0].id, user.id) is True
    assert len(list_status_events(db, app.id, user.id)) == 1
    # Unknown id (or another user's) can't be deleted.
    assert delete_status_event(db, "nope", user.id) is False
