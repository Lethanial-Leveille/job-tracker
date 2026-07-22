"""Tests for auth: the POST /auth/login route and the get_current_user gate.

No external services to mock here (unlike parsing/tailoring): bcrypt and JWT run
locally and deterministically, so these tests are pure and cheap. We seed a known
user into the in-memory `db` fixture, then cover two layers:

- the login route, over HTTP via TestClient, and
- get_current_user, called directly as a function — the cleaner way to unit-test
  a dependency's logic without standing up a protected route just for the test.

Settings are overridden with an explicit test jwt_secret so the suite does not
depend on a real .env being present (matters for CI).
"""

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from main import app
from models.user import User
from services.auth import create_access_token, hash_password

_PASSWORD = "password123"
_EMAIL = "lee@example.com"


def _test_settings() -> Settings:
    # Explicit secret so the token signed in a test is verifiable in the same
    # test, and so nothing here reads the real .env.
    return Settings(
        anthropic_api_key="test-key",
        jwt_secret="test-secret-at-least-32-bytes-long-for-hs256",
    )


@pytest.fixture
def seeded_user(db: Session) -> User:
    """Insert one known user into the test DB and return it."""
    user = User(email=_EMAIL, password_hash=hash_password(_PASSWORD))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def client(db: Session) -> TestClient:
    """TestClient with get_db pointed at the in-memory session and get_settings
    at the test settings. Both overrides are cleared after the test so they can
    not leak into another."""
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_settings] = _test_settings
    yield TestClient(app)
    app.dependency_overrides.clear()


# --- login route -------------------------------------------------------------


def test_login_success(client: TestClient, seeded_user: User) -> None:
    resp = client.post("/auth/login", json={"email": _EMAIL, "password": _PASSWORD})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]  # a non-empty token string


def test_login_wrong_password(client: TestClient, seeded_user: User) -> None:
    resp = client.post("/auth/login", json={"email": _EMAIL, "password": "WRONG"})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect email or password"


def test_login_unknown_email(client: TestClient, seeded_user: User) -> None:
    # Same 401 and message as a wrong password: the route must not reveal whether
    # an email is registered (user enumeration defense).
    resp = client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": _PASSWORD}
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Incorrect email or password"


# --- get_current_user dependency ---------------------------------------------


def _creds(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_get_current_user_valid_token(db: Session, seeded_user: User) -> None:
    settings = _test_settings()
    token = create_access_token(seeded_user.id, settings)
    user = get_current_user(credentials=_creds(token), db=db, settings=settings)
    assert user.id == seeded_user.id


def test_get_current_user_no_credentials(db: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=None, db=db, settings=_test_settings())
    assert exc.value.status_code == 401


def test_get_current_user_bad_token(db: Session) -> None:
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=_creds("garbage"), db=db, settings=_test_settings())
    assert exc.value.status_code == 401


def test_get_current_user_unknown_user(db: Session) -> None:
    # A validly signed token whose `sub` points at no user row (e.g. deleted).
    settings = _test_settings()
    token = create_access_token("nonexistent-id", settings)
    with pytest.raises(HTTPException) as exc:
        get_current_user(credentials=_creds(token), db=db, settings=settings)
    assert exc.value.status_code == 401
