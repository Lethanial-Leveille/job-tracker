"""Route-level tests for POST /resume/tailor.

The service tests (test_tailoring_service.py) cover `tailor_resume` itself. These
cover the *route's* own logic — the thin HTTP layer on top — which the service
tests can't see: that a tailored Resume comes back as 200 JSON, and that a None
from the service is mapped to a 502. This path matters to test because, unlike
the parse route, /resume/tailor can't be curled for free — each real call spends
an Opus charge — so a mock is the only cheap way to exercise the 502 branch.

Isolation: we patch the two things the route calls (`load_master` and
`tailor_resume`) *where they are used* — in routers.resume, not where they are
defined — so neither the master file nor the network is touched. And we override
the get_settings dependency so the route needs no real .env / API key.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import Settings, get_settings
from dependencies import get_current_user
from main import app
from models.user import User
from schemas.resume import Contact, Resume


def _fake_settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key", anthropic_tailoring_model="claude-opus-4-8"
    )


def _fake_user() -> User:
    # The /resume routes are behind get_current_user now. This route doesn't use
    # the user object, so a throwaway (unpersisted) User just satisfies the guard.
    return User(id="test-user", email="test@example.com", password_hash="x")


@pytest.fixture
def client() -> TestClient:
    """A TestClient whose get_settings and get_current_user are overridden,
    cleaned up after the test.

    dependency_overrides is FastAPI's built-in seam for tests: it swaps what a
    Depends() resolves to without touching the route code. Overriding
    get_current_user lets us exercise a protected route without a real token. We
    clear all overrides in teardown so they can't leak into another test.
    """
    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_current_user] = _fake_user
    yield TestClient(app)
    app.dependency_overrides.clear()


@patch("routers.resume.load_master")
@patch("routers.resume.tailor_resume")
def test_tailor_returns_resume(
    mock_tailor: MagicMock, mock_load_master: MagicMock, client: TestClient
) -> None:
    mock_load_master.return_value = Resume(contact=Contact(name="Lee"))
    mock_tailor.return_value = Resume(
        contact=Contact(name="Lee"), summary="Tailored for this job."
    )

    resp = client.post("/resume/tailor", json={"text": "some job description"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["contact"]["name"] == "Lee"
    assert body["summary"] == "Tailored for this job."


@patch("routers.resume.load_master")
@patch("routers.resume.tailor_resume")
def test_tailor_returns_502_when_service_gives_none(
    mock_tailor: MagicMock, mock_load_master: MagicMock, client: TestClient
) -> None:
    mock_load_master.return_value = Resume(contact=Contact(name="Lee"))
    mock_tailor.return_value = None  # model declined or reply truncated

    resp = client.post("/resume/tailor", json={"text": "unparseable garbage"})

    assert resp.status_code == 502
    assert resp.json()["detail"] == "Could not tailor the resume"
