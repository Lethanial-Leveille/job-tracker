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


@patch("routers.discovered.execute_run")
def test_refresh_starts_a_run_and_answers_at_once(
    mock_execute: MagicMock, db: Session, user: User, client: TestClient
) -> None:
    """202, not 200, and the work happens afterwards.

    Cloudflare abandons any request the origin has not answered in 100 seconds.
    A first pull is comfortably past that, so holding the request open would
    show a failure for a run that succeeded.
    """
    resp = client.post("/discovered/refresh")

    assert resp.status_code == 202
    body = resp.json()
    assert body["state"] == "running"
    assert body["finished_at"] is None
    # The run row exists before the work starts — that is what makes "is one
    # already going" answerable.
    assert mock_execute.call_args.args[0] == body["id"]


@patch("routers.discovered.execute_run")
def test_a_second_pull_is_refused_while_one_is_running(
    mock_execute: MagicMock, db: Session, user: User, client: TestClient
) -> None:
    """Two concurrent pulls would fetch the same feed twice and race each other
    into the same unique constraint. A schedule that fires twice should say so
    rather than be quietly queued."""
    client.post("/discovered/refresh")

    resp = client.post("/discovered/refresh")

    assert resp.status_code == 409


@patch("routers.discovered.execute_run")
def test_the_latest_run_is_readable_while_it_is_still_going(
    mock_execute: MagicMock, db: Session, user: User, client: TestClient
) -> None:
    # What makes a background run legible: without this, a quiet night, a run in
    # progress, and a run that died all look like an inbox that did not change.
    assert client.get("/discovered/runs/latest").json() is None

    client.post("/discovered/refresh")

    assert client.get("/discovered/runs/latest").json()["state"] == "running"


@patch("routers.webhooks.execute_run")
def test_the_webhook_also_answers_before_the_work_happens(
    mock_execute: MagicMock, db: Session, user: User, client: TestClient
) -> None:
    """The endpoint n8n calls, and the one the 524 was actually about.

    Held open, it would hand n8n a failure for a working run, n8n would retry,
    and the retry would collide with the run still going.
    """
    resp = client.post("/webhooks/discovery/pull", json={"email": user.email})

    assert resp.status_code == 202
    assert resp.json()["state"] == "running"
    assert mock_execute.called


@patch("routers.webhooks.execute_run")
def test_the_webhook_refuses_to_start_a_second_run(
    mock_execute: MagicMock, db: Session, user: User, client: TestClient
) -> None:
    client.post("/webhooks/discovery/pull", json={"email": user.email})

    resp = client.post("/webhooks/discovery/pull", json={"email": user.email})

    assert resp.status_code == 409


def test_the_webhook_fails_loudly_for_an_unknown_account(
    db: Session, user: User, client: TestClient
) -> None:
    # A configuration mistake on the Pi, not a transient failure. It should keep
    # failing until someone fixes it rather than quietly staging nothing.
    resp = client.post("/webhooks/discovery/pull", json={"email": "nobody@example.com"})

    assert resp.status_code == 404


def test_accepting_can_carry_a_posting_that_was_never_read(
    db: Session, user: User, client: TestClient
) -> None:
    """For the rows the overnight pass could not read.

    Roughly four in ten ordinary careers sites need a browser. Filing one of
    those as-is gives a title, a link, and nothing to tailor against — a gap you
    would not notice until you sat down to write the resume weeks later, which
    is why accepting is the moment to ask.
    """
    job = _discovery(db, user)

    body = client.post(
        f"/discovered/{job.id}/accept",
        json={"jd_text": "the posting you pasted", "jd_parsed": {"key_requirements": ["Python"]}},
    ).json()

    assert body["jd_text"] == "the posting you pasted"
    assert body["jd_parsed"]["key_requirements"] == ["Python"]


def test_accepting_without_a_posting_still_works(
    db: Session, user: User, client: TestClient
) -> None:
    # The normal case: a posting read overnight already carries its text, and an
    # empty body must not be treated as an instruction to blank it.
    job = _discovery(db, user)
    job.jd_text = "read overnight"
    db.commit()

    body = client.post(f"/discovered/{job.id}/accept", json={}).json()

    assert body["jd_text"] == "read overnight"
