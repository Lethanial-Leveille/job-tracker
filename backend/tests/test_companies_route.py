"""Route-level tests for the target company watchlist.

The services cover the rules. What only a route test can see is that a company
saved in a shape that could never be read comes back as a 422 with a message
naming the field, rather than a 500 or a silent success — this is a list you
edit by hand and then forget about, so the moment you are typing is the only
moment a mistake is cheap to fix.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from main import app
from models.user import User


def _fake_settings() -> Settings:
    return Settings(anthropic_api_key="test-key", jwt_secret="test-secret")


@pytest.fixture
def client(db: Session, user: User) -> TestClient:
    app.dependency_overrides[get_settings] = _fake_settings
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_adding_a_company_and_reading_it_back(client: TestClient) -> None:
    created = client.post(
        "/companies", json={"name": "Stripe", "ats": "greenhouse", "board": "stripe"}
    )

    assert created.status_code == 201
    assert [c["name"] for c in client.get("/companies").json()] == ["Stripe"]


def test_an_incomplete_company_is_refused_with_a_usable_message(
    client: TestClient,
) -> None:
    """A 422 you can act on, not "Request failed".

    The same column is a board token on Greenhouse and a tenant on Workday, so
    the message has to say which box is empty in the vendor's own words.
    """
    resp = client.post(
        "/companies", json={"name": "Adobe", "ats": "workday", "board": "adobe"}
    )

    assert resp.status_code == 422
    assert "site id" in str(resp.json()["detail"])


def test_changing_the_system_without_its_fields_is_refused(client: TestClient) -> None:
    """A patch is valid in isolation and breaks the row.

    Switching Greenhouse to Workday leaves a board token and no hostname. The
    merged row is what gets judged, and a 422 says so rather than a 500.
    """
    company = client.post(
        "/companies", json={"name": "Stripe", "ats": "greenhouse", "board": "stripe"}
    ).json()

    resp = client.patch(f"/companies/{company['id']}", json={"ats": "workday"})

    assert resp.status_code == 422


def test_pausing_a_company_keeps_its_configuration(client: TestClient) -> None:
    # Paused rather than deleted is the common case: a noisy board this month is
    # one you want back in October, and deleting loses what you worked out.
    company = client.post(
        "/companies", json={"name": "Stripe", "ats": "greenhouse", "board": "stripe"}
    ).json()

    updated = client.patch(f"/companies/{company['id']}", json={"active": False}).json()

    assert updated["active"] is False
    assert updated["board"] == "stripe"


def test_the_form_requirements_come_from_the_same_table_as_the_validator(
    client: TestClient,
) -> None:
    """Served rather than duplicated in the frontend, so the two cannot drift.

    A second copy in the UI is how a form stops asking for a field the backend
    still requires.
    """
    reqs = client.get("/companies/requirements").json()

    assert reqs["greenhouse"] == ["board"]
    assert set(reqs["workday"]) == {"host", "board", "site"}


def test_another_users_company_is_a_404_not_a_403(
    db: Session, user: User, client: TestClient
) -> None:
    from models.target_company import TargetCompany

    other = User(email="other@example.com", password_hash="x")
    db.add(other)
    db.commit()
    theirs = TargetCompany(user_id=other.id, name="Theirs", ats="lever", board="x")
    db.add(theirs)
    db.commit()

    # Never confirms that someone else's row exists.
    assert client.patch(f"/companies/{theirs.id}", json={"active": False}).status_code == 404
    assert client.delete(f"/companies/{theirs.id}").status_code == 404
