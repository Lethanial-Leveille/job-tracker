"""Route-level tests for POST /webhooks/email.

The ingestion service is covered by test_email_ingest_service.py. What is
exercised here is the thin HTTP layer those tests cannot see, and most of it is
the SECOND auth path — the one that had never been used until this feature, so
nothing had ever proven it works.

The auth cases matter more than the happy path. This endpoint accepts writes
from a machine over the public internet, so every way in that should be closed
gets its own test, including the one that is easy to get backwards: an
environment with NO token configured must reject everything rather than wave
everyone through.

Isolation follows test_resume_route.py: patch what the route calls where it is
USED (routers.webhooks), and override the dependencies, so neither the database
nor the network is touched.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from config import Settings, get_settings
from database import get_db
from main import app
from models.user import User
from services.email_ingest import IngestOutcome
from services.user import OwnerNotConfigured

_TOKEN = "test-service-token"


def _settings_with_token() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        jwt_secret="test-secret",
        n8n_service_token=_TOKEN,
    )


def _settings_without_token() -> Settings:
    return Settings(anthropic_api_key="test-key", jwt_secret="test-secret")


def _user() -> User:
    return User(id="test-user", email="lee@example.com", password_hash="x")


def _message(message_id: str = "18f2a") -> dict:
    return {
        "message_id": message_id,
        "thread_id": "t1",
        "internal_date_ms": 1756915331000,
        "from_raw": "Neighbor <no-reply@hire.lever.co>",
        "subject": "Thank you for applying to Neighbor",
        "snippet": "Thank you for submitting your application...",
    }


def _body(count: int = 1) -> dict:
    return {
        "mailbox": "lee@example.com",
        "messages": [_message(f"m{i}") for i in range(count)],
    }


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[get_settings] = _settings_with_token
    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def unconfigured_client() -> TestClient:
    """A deployment where N8N_SERVICE_TOKEN was never set."""
    app.dependency_overrides[get_settings] = _settings_without_token
    app.dependency_overrides[get_db] = lambda: MagicMock()
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- auth: the half that had never been exercised ---------------------------


def test_rejects_a_request_with_no_token(client: TestClient) -> None:
    resp = client.post("/webhooks/email", json=_body())

    assert resp.status_code == 401


def test_rejects_a_wrong_token(client: TestClient) -> None:
    resp = client.post(
        "/webhooks/email", json=_body(), headers={"X-Service-Token": "not-it"}
    )

    assert resp.status_code == 401


def test_rejects_everything_when_no_token_is_configured(
    unconfigured_client: TestClient,
) -> None:
    """The one that is easy to get backwards. An environment with no configured
    secret must bolt the door shut, not treat "nothing to compare against" as
    "anything matches". The droplet auto-deploys on push, so this is the state a
    new environment is in before anyone sets the variable."""
    resp = unconfigured_client.post(
        "/webhooks/email", json=_body(), headers={"X-Service-Token": _TOKEN}
    )

    assert resp.status_code == 401


def test_a_user_jwt_does_not_open_the_webhook(client: TestClient) -> None:
    """The two auth paths are separate on purpose. A bearer token belongs to a
    person and must not satisfy a machine-only endpoint."""
    resp = client.post(
        "/webhooks/email",
        json=_body(),
        headers={"Authorization": "Bearer some.jwt.value"},
    )

    assert resp.status_code == 401


# --- the request contract ---------------------------------------------------


@patch("routers.webhooks.get_owner")
def test_an_unconfigured_owner_is_a_500(
    mock_get_owner: MagicMock, client: TestClient
) -> None:
    """No OWNER_EMAIL on the server is a misconfiguration, not a bad request.

    500 rather than the 404 this used to answer, and the difference is the
    thing it points at. There is no mailbox in the body any more, so a failure
    here can only mean the DROPLET is misconfigured. Answering 4xx would send
    someone to the Pi to debug a payload that is fine.
    """
    mock_get_owner.side_effect = OwnerNotConfigured("OWNER_EMAIL is not set")

    resp = client.post(
        "/webhooks/email", json=_body(), headers={"X-Service-Token": _TOKEN}
    )

    assert resp.status_code == 500


def test_a_body_still_carrying_a_mailbox_is_accepted(client: TestClient) -> None:
    """The trim must not require changing n8n at the same moment.

    _body() still sends `mailbox`, which EmailIngestRequest no longer declares.
    Pydantic ignores undeclared fields, so the workflow already running on the
    Pi keeps working and can be tidied up whenever. If this ever fails, someone
    has added extra="forbid" and turned a deploy into a coordinated one.
    """
    assert "mailbox" in _body()

    with patch("routers.webhooks.get_owner") as mock_get_owner, patch(
        "routers.webhooks.ingest_messages"
    ) as mock_ingest:
        mock_get_owner.return_value = _user()
        mock_ingest.return_value = []
        resp = client.post(
            "/webhooks/email", json=_body(), headers={"X-Service-Token": _TOKEN}
        )

    assert resp.status_code == 200


@patch("routers.webhooks.ingest_messages")
@patch("routers.webhooks.get_owner")
def test_a_batch_over_the_cap_is_rejected_before_any_work(
    mock_get_user: MagicMock, mock_ingest: MagicMock, client: TestClient
) -> None:
    """Ten is the cap because classification is a model call per message and this
    endpoint answers synchronously. An oversized batch must fail validation
    rather than run long enough for n8n to time out and retry it."""
    mock_get_user.return_value = _user()

    resp = client.post(
        "/webhooks/email", json=_body(11), headers={"X-Service-Token": _TOKEN}
    )

    assert resp.status_code == 422
    mock_ingest.assert_not_called()


@patch("routers.webhooks.ingest_messages")
@patch("routers.webhooks.get_owner")
def test_an_empty_batch_is_rejected(
    mock_get_user: MagicMock, mock_ingest: MagicMock, client: TestClient
) -> None:
    mock_get_user.return_value = _user()

    resp = client.post(
        "/webhooks/email",
        json={"mailbox": "lee@example.com", "messages": []},
        headers={"X-Service-Token": _TOKEN},
    )

    assert resp.status_code == 422
    mock_ingest.assert_not_called()


# --- the response -----------------------------------------------------------


@patch("routers.webhooks.ingest_messages")
@patch("routers.webhooks.get_owner")
def test_summarises_a_mixed_batch(
    mock_get_user: MagicMock, mock_ingest: MagicMock, client: TestClient
) -> None:
    mock_get_user.return_value = _user()
    mock_ingest.return_value = [
        IngestOutcome("m0", "suggested", "s1"),
        IngestOutcome("m1", "ambiguous", "s2"),
        IngestOutcome("m2", "duplicate"),
        IngestOutcome("m3", "not_classified"),
        IngestOutcome("m4", "no_action"),
    ]

    resp = client.post(
        "/webhooks/email", json=_body(5), headers={"X-Service-Token": _TOKEN}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["received"] == 5
    # A duplicate wrote nothing; the other four did.
    assert body["stored"] == 3
    assert body["suggestions_created"] == 2
    assert body["retry"] == 1
    assert [r["message_id"] for r in body["results"]] == ["m0", "m1", "m2", "m3", "m4"]


@patch("routers.webhooks.ingest_messages")
@patch("routers.webhooks.get_owner")
def test_a_batch_where_everything_failed_is_still_a_200(
    mock_get_user: MagicMock, mock_ingest: MagicMock, client: TestClient
) -> None:
    """A per-message failure is not a failed REQUEST. Answering non-200 would
    make n8n retry the whole batch and re-bill every message that succeeded —
    and here, the failures are already scheduled for redelivery by the rolling
    window, so a retry would add nothing."""
    mock_get_user.return_value = _user()
    mock_ingest.return_value = [
        IngestOutcome("m0", "not_classified"),
        IngestOutcome("m1", "not_classified"),
    ]

    resp = client.post(
        "/webhooks/email", json=_body(2), headers={"X-Service-Token": _TOKEN}
    )

    assert resp.status_code == 200
    assert resp.json()["retry"] == 2
    assert resp.json()["suggestions_created"] == 0


@patch("routers.webhooks.ingest_messages")
@patch("routers.webhooks.get_owner")
def test_the_configured_owner_decides_whose_rows_are_touched(
    mock_get_user: MagicMock, mock_ingest: MagicMock, client: TestClient
) -> None:
    """The service token authenticates the machine and returns nobody, so
    something else must name the owner. That used to be the mailbox in the
    body; it is now OWNER_EMAIL on the server. Either way the property under
    test is the same one: ingestion is handed exactly one user's id, and it is
    not chosen by the caller."""
    mock_get_user.return_value = _user()
    mock_ingest.return_value = []

    client.post("/webhooks/email", json=_body(), headers={"X-Service-Token": _TOKEN})

    assert mock_ingest.call_args.args[1] == "test-user"
