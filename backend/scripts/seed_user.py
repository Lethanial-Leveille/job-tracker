"""One-off: create the single user (me). Run once, interactively.

There is no public signup — this script is how user #1 comes to exist. It
prompts for an email and password (password hidden, entered twice to catch
typos since you can't see it), hashes the password with the same bcrypt helper
the login route uses, and inserts one `users` row.

Run it from backend/ with the venv active, so the relative SQLite path resolves:

    python scripts/seed_user.py

It refuses to create a second row with an email that already exists, so running
it again is safe.
"""

import getpass
import os
import sys

# Put backend/ on the import path so `from database import ...` works when this
# is run directly as a file (same trick as alembic/env.py). __file__ is
# backend/scripts/seed_user.py, so two dirs up is backend/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.user import User  # noqa: E402
from services.auth import hash_password  # noqa: E402

MIN_PASSWORD_LENGTH = 8


def main() -> None:
    email = input("Email: ").strip()
    if not email:
        sys.exit("Email cannot be empty.")

    password = getpass.getpass("Password: ")
    if len(password) < MIN_PASSWORD_LENGTH:
        sys.exit(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if password != getpass.getpass("Confirm password: "):
        sys.exit("Passwords did not match.")

    with SessionLocal() as db:
        existing = db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()
        if existing is not None:
            sys.exit(f"A user with email {email} already exists (id {existing.id}).")

        user = User(email=email, password_hash=hash_password(password))
        db.add(user)
        db.commit()
        db.refresh(user)  # reload so the DB-generated id is populated
        print(f"Created user {user.email} with id {user.id}")


if __name__ == "__main__":
    main()
