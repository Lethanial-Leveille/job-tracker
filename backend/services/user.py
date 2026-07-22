"""User lookups: the DB access behind login and the auth dependency.

HTTP-ignorant like the other services (no FastAPI here). Kept separate from
services/auth.py, which is pure crypto with no DB — this file is the DB half.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

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
