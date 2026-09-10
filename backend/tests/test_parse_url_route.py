"""Route-level tests for POST /applications/parse-url.

The pieces are already covered elsewhere: test_fetch_posting_service.py proves
the fetcher picks the right adapter, test_parsing_service.py proves the parser
handles a refusal. What only a route test can see is the CONTRACT between them
and the frontend — which failure produces which status code, and whether the
posting text survives the trip.

That contract matters more than it looks. The add screen decides whether to fall
back to the paste box purely on the status code, so if these two ever collapse
onto one number, a dead link and a broken model become indistinguishable on
screen. Same isolation as test_fit_route.py: patch what the route calls where it
is used, override the dependencies, touch neither network nor database.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from main import app
from models.user import User
from schemas.parsing import FetchedPosting, ParsedJob
from services.fetch_posting import PostingFetchError


def _fake_settings() -> Settings:
    return Settings(anthropic_api_key="test-key", jwt_secret="test-secret")


def _fake_user() -> User:
    return User(id="test-user", email="test@example.com", password_hash="x")


def _parsed() -> ParsedJob:
    return ParsedJob(
        type="internship",
        organization="Acme Corp",
        role_or_program="Software Engineering Intern",
        role_family="Software Engineer Intern",
    )


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_current_user] = _fake_user
    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


@patch("routers.applications.parse_job_description")
@patch("routers.applications.fetch_posting")
def test_returns_the_parse_alongside_the_text_it_came_from(
    mock_fetch: MagicMock, mock_parse: MagicMock, client: TestClient
) -> None:
    """jd_text riding along is the load-bearing part of this response.

    It is what resume tailoring reads later. A link add that returned only the
    parsed fields would create rows that look complete and cannot be tailored
    against, which is the kind of gap you would not notice until you tried.
    """
    mock_fetch.return_value = FetchedPosting(
        text="the full posting text",
        source="workday",
        url="https://acme.wd1.myworkdayjobs.com/careers/job/R1",
    )
    mock_parse.return_value = _parsed()

    resp = client.post("/applications/parse-url", json={"url": "https://acme.example/job"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"]["organization"] == "Acme Corp"
    assert body["jd_text"] == "the full posting text"
    assert body["source"] == "workday"
    # The RESOLVED url, not the one that was posted in: that is the link worth
    # storing on the row once redirects have been followed.
    assert body["posting_url"] == "https://acme.wd1.myworkdayjobs.com/careers/job/R1"


@patch("routers.applications.parse_job_description")
@patch("routers.applications.fetch_posting")
def test_fetch_failure_is_400_and_no_paid_call_is_spent(
    mock_fetch: MagicMock, mock_parse: MagicMock, client: TestClient
) -> None:
    """A dead or blocked link must not reach the model.

    The message is passed through verbatim because it was written to be read by
    a person above the paste box, not logged. Asserting the parser was never
    called is the other half: a fetch that failed has nothing to parse, and
    calling anyway would bill for it.
    """
    mock_fetch.side_effect = PostingFetchError(
        "LinkedIn blocks automated fetches. Paste the posting text instead."
    )

    resp = client.post("/applications/parse-url", json={"url": "https://www.linkedin.com/jobs/view/1"})

    assert resp.status_code == 400
    assert resp.json()["detail"] == (
        "LinkedIn blocks automated fetches. Paste the posting text instead."
    )
    mock_parse.assert_not_called()


@patch("routers.applications.parse_job_description")
@patch("routers.applications.fetch_posting")
def test_parse_failure_is_502_not_400(
    mock_fetch: MagicMock, mock_parse: MagicMock, client: TestClient
) -> None:
    # The fetch worked, so falling back to the paste box would hand the user
    # the same text that just failed. Different problem, different code.
    mock_fetch.return_value = FetchedPosting(text="text", source="generic", url="https://acme.example/job")
    mock_parse.return_value = None

    resp = client.post("/applications/parse-url", json={"url": "https://acme.example/job"})

    assert resp.status_code == 502


def test_a_missing_url_is_a_422_from_validation(client: TestClient) -> None:
    """Guards the reason the route answers 400 rather than the more literal 422.

    FastAPI owns 422 and puts a LIST of error objects in `detail` there, where
    our own failures put a string. Keeping them on separate codes means the
    frontend never has to guess which shape it received.
    """
    resp = client.post("/applications/parse-url", json={})

    assert resp.status_code == 422
    assert isinstance(resp.json()["detail"], list)
