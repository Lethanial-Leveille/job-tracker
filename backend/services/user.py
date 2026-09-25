"""User lookups: the DB access behind login and the auth dependency.

HTTP-ignorant like the other services (no FastAPI here). Kept separate from
services/auth.py, which is pure crypto with no DB — this file is the DB half.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings
from models.user import User


def get_user_by_email(db: Session, email: str) -> User | None:
    """Find a user by their login email, or None. Used by the login route."""
    return db.execute(
        select(User).where(User.email == email)
    ).scalar_one_or_none()


def get_user_by_id(db: Session, user_id: str) -> User | None:
    """Find a user by primary key, or None. Used by get_current_user to turn a
    token's `sub` back into a real user. db.get is the 2.0 way to fetch by PK
    (it also checks the session's identity map first)."""
    return db.get(User, user_id)


class OwnerNotConfigured(Exception):
    """OWNER_EMAIL is unset, or names a user that is not in the database.

    A distinct exception rather than returning None, for the same reason
    discovery.py raises RunAlreadyGoing: the caller cannot do anything sensible
    with the failure except report it, and a None would quietly invite someone
    to treat "no owner" as "no rows". This is always a deployment mistake, never
    a transient one, so it should be loud and stay loud until the env var is
    fixed.
    """


def get_owner(db: Session, settings: Settings) -> User:
    """The one person this deployment belongs to, named by OWNER_EMAIL.

    This is the single user answer to a question every non-login caller used to
    ask the CALLER: whose data is this. Automation and integrations hold a
    shared secret, not an identity, so letting them name a user in the request
    body means the secret reaches whichever account it asks for. There is a
    second account in this database. Resolving the owner from configuration
    instead means a token reaches exactly one account no matter what it sends.

    Deliberately not cached alongside get_settings. The settings object is a
    process lifetime singleton, but a User is attached to the request's session,
    and holding one past that session is how you get a detached instance error
    on a later attribute read. Looking it up per request is one indexed query on
    a unique column.

    Raises OwnerNotConfigured rather than an HTTPException: this module stays
    free of FastAPI like the rest of services/, and the dependency that calls it
    is what turns this into a status code.
    """
    if settings.owner_email is None:
        raise OwnerNotConfigured(
            "OWNER_EMAIL is not set, so no caller can be resolved to an owner."
        )

    owner = get_user_by_email(db, settings.owner_email)
    if owner is None:
        # The address goes in the message because this is a log line for you,
        # and a typo in the env var is invisible without it. Callers must not
        # pass this text through to an HTTP body.
        raise OwnerNotConfigured(
            f"OWNER_EMAIL is set to {settings.owner_email}, which matches no user."
        )

    return owner
