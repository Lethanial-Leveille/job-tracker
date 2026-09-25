"""Cross-cutting FastAPI dependencies. Sits beside database.py and config.py as
infrastructure — the things routes pull in via Depends().

get_current_user is the gate: any route that adds `Depends(get_current_user)`
becomes protected and receives the logged-in User. It lives here, not in
services/auth.py, because it needs FastAPI (Depends, HTTPException, the request
header) — services stay HTTP-ignorant.
"""

import logging
import secrets

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from models.user import User
from services.auth import decode_access_token
from services.user import OwnerNotConfigured, get_owner, get_user_by_id

# auto_error=False so a MISSING Authorization header hands us None instead of
# HTTPBearer raising its own 403. We want one consistent 401 for every auth
# failure (missing, malformed, expired, or unknown user), so we handle it below.
logger = logging.getLogger(__name__)

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


def verify_miles_token(
    x_miles_token: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    """Gate for the MILES integration: require its own shared secret.

    The THIRD auth path, and it gets its own everything on purpose.

    Its own HEADER, X-Miles-Token, for the reason written above verify_service_
    token: a credential on Authorization: Bearer would sit where the login JWT
    sits, and some function would end up guessing which kind it was holding.

    Its own SECRET, separate from n8n_service_token, because the two callers
    want different things. n8n writes on a schedule from a workflow you rarely
    touch; MILES reads on demand and files one accept, from a Pi that runs a
    voice assistant you are actively developing. Revoking the one you are
    iterating on must never take Gmail ingestion down with it.

    Returns None rather than a user, exactly like the n8n gate: a secret proves
    which MACHINE is calling and says nothing about whose data it may touch.
    get_miles_owner below is what answers that, from configuration.
    """
    forbidden = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing MILES token",
    )

    # Unset in this environment means the door is bolted shut, not held open.
    # Same fail-safe choice as the n8n token, and it matters more here: this one
    # ships to prod on the next push whether or not you have set the env var.
    if settings.miles_service_token is None:
        raise forbidden

    if x_miles_token is None:
        raise forbidden

    # Constant time compare, so the response time cannot be used to recover the
    # secret one character at a time.
    if not secrets.compare_digest(x_miles_token, settings.miles_service_token):
        raise forbidden


def get_miles_owner(
    _: None = Depends(verify_miles_token),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """The account MILES reads, resolved from config and never from the request.

    Chaining verify_miles_token in as an unused parameter is the point: it makes
    the identity impossible to obtain without first passing the gate, so a route
    cannot accidentally ask "whose data" without having asked "who is calling".
    FastAPI resolves it once per request and caches it, so listing this gate at
    router level as well costs nothing.

    The 500 below is deliberate, and it is not a 401. The caller's token was
    perfectly good; the SERVER has no owner configured. Answering 401 would send
    you hunting for a bad token on the Pi when the real fault is a missing
    OWNER_EMAIL on the droplet, and that is an afternoon you do not get back.

    The detail is generic while the log line is specific, because the exception
    text carries the configured address and an HTTP body is the wrong place for
    it.
    """
    try:
        return get_owner(db, settings)
    except OwnerNotConfigured as exc:
        logger.error("A MILES request could not resolve an owner: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="The integration owner is not configured on this server.",
        ) from exc
