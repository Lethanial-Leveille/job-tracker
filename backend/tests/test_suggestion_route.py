"""Route-level tests for "Add as application" on an email suggestion.

test_suggestion_service.py already proves the service creates the row. What it
could not see is the step after: the route serializing that row through
ApplicationRead. An email carries no posting link, so the row is stored with an
empty URL, and when the read schema demanded one the route 500ed AFTER the
commit. The suggestion vanished, the application was created, and the list
quietly skipped it, so the click looked like it did nothing. Only a test that
goes through the HTTP layer catches that.

Same isolation as test_discovered_route.py: override the dependencies, touch
neither the network nor the real database.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_current_user
from main import app
from models.application import ApplicationStatus
from models.ingested_email import IngestedEmail
from models.status_suggestion import StatusSuggestion
from models.user import User


@pytest.fixture
def client(db: Session, user: User) -> TestClient:
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _unmatched_suggestion(db: Session, user: User) -> StatusSuggestion:
    # Unmatched: no application_id and no candidates, which is exactly the case
    # the "Add as application" button is shown for.
    email = IngestedEmail(
        user_id=user.id,
        message_id="msg-1",
        received_at=datetime.now(UTC),
        from_email="no-reply@hire.lever.co",
        from_name="Stoke Space",
        subject="Thanks for applying",
        snippet="We received your application.",
        classification={
            "kind": "application_received",
            "organization": "Stoke Space",
            "role_hint": "Software Intern",
        },
    )
    db.add(email)
    db.commit()
    suggestion = StatusSuggestion(
        user_id=user.id,
        suggested_status=ApplicationStatus.applied,
        reason="Confirmation from Stoke Space",
        source_email_id=email.id,
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)
    return suggestion


def test_add_as_application_returns_the_new_row(
    db: Session, user: User, client: TestClient
) -> None:
    suggestion = _unmatched_suggestion(db, user)

    res = client.post(f"/suggestions/{suggestion.id}/create-application")

    assert res.status_code == 201
    body = res.json()
    assert body["organization"] == "Stoke Space"
    assert body["status"] == "applied"
    assert body["posting_url"] == ""


def test_added_application_shows_in_the_list_and_leaves_the_queue(
    db: Session, user: User, client: TestClient
) -> None:
    # The list validates rows one at a time and skips any it cannot read, so a
    # row with an unreadable URL would not fail this request; it would just be
    # missing. Asserting it is present is the real check.
    suggestion = _unmatched_suggestion(db, user)
    created = client.post(f"/suggestions/{suggestion.id}/create-application").json()

    assert [a["id"] for a in client.get("/applications").json()] == [created["id"]]
    assert client.get("/suggestions").json() == []


def test_added_application_can_be_edited_before_it_has_a_url(
    db: Session, user: User, client: TestClient
) -> None:
    # The detail drawer sends every field back on save, including the still
    # empty URL, so an edit to anything else must not be refused over it.
    suggestion = _unmatched_suggestion(db, user)
    created = client.post(f"/suggestions/{suggestion.id}/create-application").json()

    res = client.patch(
        f"/applications/{created['id']}",
        json={"posting_url": "", "notes": "Found it on their careers page"},
    )

    assert res.status_code == 200
    assert res.json()["notes"] == "Found it on their careers page"
