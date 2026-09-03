"""Route-level tests for POST /applications/{id}/fit.

The service tests (test_matching_service.py) cover `assess_requirements` itself.
These cover the route's own logic, which the service tests cannot see: where the
requirements come from, which failures are refused BEFORE the paid call, and
that the result is written back to the row.

Same isolation approach as test_resume_route.py: patch what the route calls
where it is USED (routers.applications), override the dependencies, so neither
the database nor the network is touched.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from main import app
from models.user import User
from schemas.fit import FitReport, RequirementMatch
from schemas.resume import Contact, Resume


def _fake_settings() -> Settings:
    return Settings(anthropic_api_key="test-key", jwt_secret="test-secret")


def _fake_user() -> User:
    return User(id="test-user", email="test@example.com", password_hash="x")


def _fake_master() -> MagicMock:
    row = MagicMock()
    row.resume_json = Resume(contact=Contact(name="Lee")).model_dump()
    return row


def _fake_application(requirements: list[str] | None) -> MagicMock:
    """Stands in for an Application row. jd_parsed is None for a row added by
    hand (the parser never ran on it)."""
    row = MagicMock()
    row.jd_parsed = None if requirements is None else {"key_requirements": requirements}
    row.fit_report = None
    row.fit_computed_at = None
    return row


def _report() -> FitReport:
    return FitReport.from_matches(
        [
            RequirementMatch(requirement="Python", verdict="met", evidence="Built X"),
            RequirementMatch(requirement="Rust", verdict="missing"),
        ]
    )


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


@patch("routers.applications.get_application")
@patch("routers.applications.get_master")
@patch("routers.applications.assess_requirements")
def test_returns_report_and_caches_it_on_the_row(
    mock_assess: MagicMock,
    mock_get_master: MagicMock,
    mock_get_application: MagicMock,
    client: TestClient,
) -> None:
    row = _fake_application(["Python", "Rust"])
    mock_get_application.return_value = row
    mock_get_master.return_value = _fake_master()
    mock_assess.return_value = _report()

    resp = client.post("/applications/abc/fit")

    assert resp.status_code == 200
    body = resp.json()
    assert body["met_count"] == 1
    assert body["total"] == 2

    # The point of caching: reopening the application must not re-run the call.
    assert row.fit_report is not None
    assert row.fit_report["met_count"] == 1
    assert row.fit_computed_at is not None


@patch("routers.applications.get_application")
def test_404_for_a_row_that_is_not_yours(
    mock_get_application: MagicMock, client: TestClient
) -> None:
    # get_application is owner-scoped, so someone else's row comes back as None
    # and must be indistinguishable from one that does not exist.
    mock_get_application.return_value = None

    resp = client.post("/applications/abc/fit")

    assert resp.status_code == 404


@patch("routers.applications.get_application")
@patch("routers.applications.get_master")
@patch("routers.applications.assess_requirements")
def test_400_without_a_master_resume_and_no_call_is_spent(
    mock_assess: MagicMock,
    mock_get_master: MagicMock,
    mock_get_application: MagicMock,
    client: TestClient,
) -> None:
    mock_get_application.return_value = _fake_application(["Python"])
    mock_get_master.return_value = None

    resp = client.post("/applications/abc/fit")

    assert resp.status_code == 400
    mock_assess.assert_not_called()


@patch("routers.applications.get_application")
@patch("routers.applications.get_master")
@patch("routers.applications.assess_requirements")
def test_400_for_a_hand_added_row_with_no_parsed_requirements(
    mock_assess: MagicMock,
    mock_get_master: MagicMock,
    mock_get_application: MagicMock,
    client: TestClient,
) -> None:
    """A row added by hand never went through the parser, so it has no
    jd_parsed at all. That must refuse clearly rather than return an empty
    report, which would render as a flawless score against zero requirements."""
    mock_get_application.return_value = _fake_application(None)
    mock_get_master.return_value = _fake_master()

    resp = client.post("/applications/abc/fit")

    assert resp.status_code == 400
    assert "no extracted requirements" in resp.json()["detail"]
    mock_assess.assert_not_called()


@patch("routers.applications.get_application")
@patch("routers.applications.get_master")
@patch("routers.applications.assess_requirements")
def test_502_when_the_model_declines(
    mock_assess: MagicMock,
    mock_get_master: MagicMock,
    mock_get_application: MagicMock,
    client: TestClient,
) -> None:
    mock_get_application.return_value = _fake_application(["Python"])
    mock_get_master.return_value = _fake_master()
    mock_assess.return_value = None

    resp = client.post("/applications/abc/fit")

    assert resp.status_code == 502
