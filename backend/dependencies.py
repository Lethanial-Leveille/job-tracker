"""Cross-cutting FastAPI dependencies. Sits beside database.py and config.py as
infrastructure — the things routes pull in via Depends().

get_current_user is the gate: any route that adds `Depends(get_current_user)`
becomes protected and receives the logged-in User. It lives here, not in
services/auth.py, because it needs FastAPI (Depends, HTTPException, the request
header) — services stay HTTP-ignorant.
"""

from fastapi import Depends, HTTPException, status
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
