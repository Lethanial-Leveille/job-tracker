"""Route-level tests for POST /resume/tailor.

The service tests (test_tailoring_service.py) cover `tailor_resume` itself. These
cover the *route's* own logic — the thin HTTP layer on top — which the service
tests can't see: that a tailored Resume comes back as 200 JSON, that a None from
the service maps to 502, and that a user with no master resume yet gets a 400.
This path matters to test because, unlike the parse route, /resume/tailor can't
be curled for free — each real call spends an Opus charge — so a mock is the only
cheap way to exercise these branches.

Isolation: we patch the two things the route calls (`get_master` and
`tailor_resume`) *where they are used* — in routers.resume, not where they are
defined — so neither the database nor the network is touched. We override
get_settings so the route needs no real .env / API key, get_current_user so the
protected route needs no real token, and get_db to a no-op (the real DB lookup
is what `get_master` is patched to stand in for, so the session is never used).
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from main import app
from models.user import User
from schemas.resume import Contact, Resume


def _fake_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key", anthropic_tailoring_model="claude-opus-4-8"
    )


def _fake_user() -> User:
    # The /resume routes are behind get_current_user. A throwaway (unpersisted)
    # User satisfies the guard; the route only reads user.id.
    return User(id="test-user", email="test@example.com", password_hash="x")


def _fake_master() -> MagicMock:
    # Stands in for a MasterResume row. The route reads only `.resume_json` and
    # validates it back into a Resume, so a dict from a minimal valid Resume is
    # all it needs.
    row = MagicMock()
    row.resume_json = Resume(contact=Contact(name="Lee")).model_dump()
    return row


@pytest.fixture
def client() -> TestClient:
    """A TestClient whose get_settings, get_current_user, and get_db are
    overridden, cleaned up after the test.

    dependency_overrides is FastAPI's built-in seam for tests: it swaps what a
    Depends() resolves to without touching the route code. get_db is overridden
    to None because the route's only DB touch goes through get_master, which the
    tests patch — so the session is never actually used. We clear all overrides
    in teardown so they can't leak into another test.
    """
    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = lambda: None
    yield TestClient(app)
    app.dependency_overrides.clear()


@patch("routers.resume.get_master")
@patch("routers.resume.tailor_resume")
def test_tailor_returns_resume(
    mock_tailor: MagicMock, mock_get_master: MagicMock, client: TestClient
) -> None:
    mock_get_master.return_value = _fake_master()
    mock_tailor.return_value = Resume(
        contact=Contact(name="Lee"), summary="Tailored for this job."
    )

    resp = client.post("/resume/tailor", json={"text": "some job description"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["contact"]["name"] == "Lee"
    assert body["summary"] == "Tailored for this job."


@patch("routers.resume.get_master")
@patch("routers.resume.tailor_resume")
def test_tailor_returns_502_when_service_gives_none(
    mock_tailor: MagicMock, mock_get_master: MagicMock, client: TestClient
) -> None:
    mock_get_master.return_value = _fake_master()
    mock_tailor.return_value = None  # model declined or reply truncated

    resp = client.post("/resume/tailor", json={"text": "unparseable garbage"})

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Could not tailor the resume"


@patch("routers.resume.get_master")
def test_tailor_returns_400_when_no_master(
    mock_get_master: MagicMock, client: TestClient
) -> None:
    # A user who has never built a master resume can't tailor. The route stops
    # at 400 before ever calling the (expensive) model.
    mock_get_master.return_value = None

    resp = client.post("/resume/tailor", json={"text": "some job description"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == "Create your master resume before tailoring"
