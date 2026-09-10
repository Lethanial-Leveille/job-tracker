"""Route-level tests for the discovery inbox.

The services own the hard logic and are tested separately. What only a route
test can see is the contract: that the inbox is scoped to its owner, that
accepting produces a real application carrying what the classifier already paid
to work out, and that the button and the nightly webhook run the same code.

Same isolation as test_fit_route.py — patch what the route calls where it is
used, override the dependencies, touch neither network nor the real database.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user, verify_service_token
from main import app
from models.application import Application, ApplicationStatus, ApplicationType
from models.discovered_job import DiscoveredJob, DiscoveryState
from models.user import User


def _fake_settings() -> Settings:
    return Settings(anthropic_api_key="test-key", jwt_secret="test-secret")


@pytest.fixture
def client(db: Session, user: User) -> TestClient:
    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[verify_service_token] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


def _discovery(db: Session, user: User, **overrides: object) -> DiscoveredJob:
    base = {
        "user_id": user.id,
        "source": "simplify",
        "external_id": "feed-1",
        "organization": "Acme Corp",
        "role_or_program": "Software Engineer Intern",
        "posting_url": "https://jobs.example.com/1",
        "role_family": "Embedded Engineer Intern",
    }
    base.update(overrides)
    row = DiscoveredJob(**base)  # type: ignore[arg-type]
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def test_the_inbox_shows_only_undecided_jobs(
    db: Session, user: User, client: TestClient
) -> None:
    # A dismissed row stays in the table so tomorrow's pull cannot re-offer it,
    # but it must not keep showing up on screen.
    _discovery(db, user, external_id="a")
    _discovery(db, user, external_id="b", state=DiscoveryState.dismissed)

    body = client.get("/discovered").json()

    assert [row["id"] for row in body] == [
        row.id for row in db.query(DiscoveredJob).filter_by(external_id="a")
    ]


def test_another_users_discovery_is_invisible(
    db: Session, user: User, client: TestClient
) -> None:
    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.commit()
    theirs = _discovery(db, other, external_id="theirs")

    assert client.get("/discovered").json() == []
    # And addressing it directly is a 404, not a 403: we never confirm it exists.
    assert client.post(f"/discovered/{theirs.id}/dismiss").status_code == 404


def test_accepting_creates_an_application_and_carries_the_family_across(
    db: Session, user: User, client: TestClient
) -> None:
    """The classifier's verdict must survive the transition.

    It was already paid for during staging. Dropping it here would mean the row
    arrives unclassified and the grouping views treat a known job as unknown.
    """
    job = _discovery(db, user)

    body = client.post(f"/discovered/{job.id}/accept").json()

    assert body["organization"] == "Acme Corp"
    assert body["role_family"] == "Embedded Engineer Intern"
    # Filed at the START of the pipeline: accepting means "worth pursuing", not
    # "applied".
    assert body["status"] == ApplicationStatus.discovered.value

    db.refresh(job)
    assert job.state is DiscoveryState.accepted
    assert job.application_id == body["id"]


def test_a_dismissed_job_keeps_its_row(
    db: Session, user: User, client: TestClient
) -> None:
    job = _discovery(db, user)

    client.post(f"/discovered/{job.id}/dismiss")

    db.refresh(job)
    assert job.state is DiscoveryState.dismissed
    assert job.resolved_at is not None


@patch("routers.discovered.run_pull")
def test_refresh_runs_the_pull_for_the_signed_in_user(
    mock_pull: MagicMock, db: Session, user: User, client: TestClient
) -> None:
    from schemas.discovery import PullResult

    mock_pull.return_value = PullResult(fetched=100, kept=10, staged=3)

    body = client.post("/discovered/refresh").json()

    assert body["staged"] == 3
    assert mock_pull.call_args.args[1] == user.id


@patch("routers.webhooks.run_pull")
def test_the_webhook_and_the_button_run_the_same_pull(
    mock_pull: MagicMock, db: Session, user: User, client: TestClient
) -> None:
    """The whole reason both triggers call one function.

    If the nightly job and the manual button ever diverge, the one you cannot
    watch is the one that breaks.
    """
    from schemas.discovery import PullResult

    mock_pull.return_value = PullResult(staged=2)

    body = client.post(
        "/webhooks/discovery/pull", json={"email": user.email}
    ).json()

    assert body["staged"] == 2
    assert mock_pull.call_args.args[1] == user.id


def test_the_webhook_fails_loudly_for_an_unknown_account(
    db: Session, user: User, client: TestClient
) -> None:
    # A configuration mistake on the Pi, not a transient failure. It should keep
    # failing until someone fixes it rather than quietly staging nothing.
    resp = client.post("/webhooks/discovery/pull", json={"email": "nobody@example.com"})

    assert resp.status_code == 404
