"""Auth primitives: password hashing and JWT issue/verify.

Pure and HTTP-ignorant, like the other services — no FastAPI, no DB session
here. Routes and dependencies (piece 4+) call these; that keeps the security
logic in one place and unit-testable without a request. Splits cleanly in two:
password hashing (bcrypt) and access tokens (JWT).
"""

from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from config import Settings


# --- Password hashing --------------------------------------------------------
# bcrypt operates on bytes, so we encode on the way in and decode the stored
# hash back to str for the String(255) column. bcrypt only uses the first 72
# bytes of a password; not guarded here because this is my own login, but worth
# knowing before this ever goes multi-user.


def hash_password(plain: str) -> str:
    """Hash a plaintext password for storage. Salt is random per call and is
    embedded in the returned hash, so no separate salt column is needed."""
    hashed: bytes = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Check a login attempt against a stored hash. checkpw reads the salt out
    of `hashed`, re-hashes `plain`, and compares in constant time."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# --- Access tokens -----------------------------------------------------------
# A JWT here carries `sub` (the user id) and `exp` (expiry). The secret and
# algorithm come from Settings so nothing is hardcoded. `exp` is a timezone
# aware UTC datetime; PyJWT converts it to a UNIX timestamp and, on decode,
# rejects an expired token automatically.


def create_access_token(user_id: str, settings: Settings) -> str:
    """Issue a signed token proving this user is logged in."""
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str, settings: Settings) -> str | None:
    """Verify a token's signature and expiry, returning the user id (`sub`), or
    None if the token is invalid, expired, or malformed. The caller turns None
    into a 401 — this function stays HTTP-ignorant."""
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
    except jwt.InvalidTokenError:
        return None
    return payload.get("sub")
