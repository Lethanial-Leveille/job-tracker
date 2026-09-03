"""Cross-cutting FastAPI dependencies. Sits beside database.py and config.py as
infrastructure — the things routes pull in via Depends().

get_current_user is the gate: any route that adds `Depends(get_current_user)`
becomes protected and receives the logged-in User. It lives here, not in
services/auth.py, because it needs FastAPI (Depends, HTTPException, the request
header) — services stay HTTP-ignorant.
"""

import secrets

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from models.user import User
from services.auth import decode_access_token
from services.user import get_user_by_id

# auto_error=False so a MISSING Authorization header hands us None instead of
# HTTPBearer raising its own 403. We want one consistent 401 for every auth
# failure (missing, malformed, expired, or unknown user), so we handle it below.
_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Resolve the bearer token to the logged-in User, or raise 401.

    One shared 401 for every failure mode on purpose: leaking *why* a token was
    rejected (expired vs. forged vs. unknown user) gives an attacker nothing.
    """
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    user_id = decode_access_token(credentials.credentials, settings)
    if user_id is None:
        raise unauthorized

    user = get_user_by_id(db, user_id)
    if user is None:
        # Token was validly signed but points at a user that no longer exists.
        raise unauthorized

    return user


def verify_service_token(
    x_service_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Gate for automation (n8n) endpoints: require the shared service token.

    This is the second, separate auth path — the user's JWT goes through
    get_current_user above; n8n has no user, it authenticates with one shared
    secret in the X-Service-Token header. Kept in a distinct header (not
    Authorization: Bearer) so the two paths never get confused for each other.

    Returns None, not a user: automation isn't a person. A route protects
    itself by listing this in `dependencies=[Depends(verify_service_token)]`;
    the ingestion service is what resolves which user owns the rows it writes.
    """
    forbidden = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing service token",
    )

    # Token unset in this environment → the door is bolted shut. Reject every
    # call rather than treating "no configured secret" as "anything matches".
    if settings.n8n_service_token is None:
        raise forbidden

    if x_service_token is None:
        raise forbidden

    # Constant-time compare: takes the same time whether the mismatch is in the
    # first character or the last, so an attacker can't recover the token by
    # timing responses. compare_digest is the standard tool for secret checks.
    if not secrets.compare_digest(x_service_token, settings.n8n_service_token):
        raise forbidden
