"""One-off: load the YAML master resume into the database for a user.

Background: the master resume used to live only as backend/data/master_resume.yaml.
Now each user's master lives in the `resumes` table (see models/resume.py). This
script bridges the two — it reads the YAML, validates it through the same
`load_master` the app uses, and upserts it into one user's row — so my existing
resume survives the file-to-DB move without being re-entered by hand.

It is idempotent: `upsert_master` replaces the row if it already exists, so
running it twice just reloads the file.

Run it from backend/ with the venv active:

    python scripts/load_master_from_yaml.py            # loads into the oldest user (me)
    python scripts/load_master_from_yaml.py you@x.com  # loads into a specific user

The email arg matters once there is more than one user (e.g. after mom is
seeded): pass it to be explicit about whose master you are loading into.
"""

import os
import sys
from pathlib import Path

# Put backend/ on the import path so `from database import ...` works when run
# directly as a file (same trick as seed_user.py / alembic/env.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.user import User  # noqa: E402
from services.resume import upsert_master  # noqa: E402
from services.resume_render import load_master  # noqa: E402

# data/ is a sibling of scripts/ under backend/ — same file as the app used.
MASTER_PATH = Path(__file__).resolve().parent.parent / "data" / "master_resume.yaml"


def main() -> None:
    # Optional first arg: the target user's email. Without it, default to the
    # oldest user (that's me — created first), matching how discovery/backfill
    # resolve "the owner".
    target_email = sys.argv[1].strip() if len(sys.argv) > 1 else None

    if not MASTER_PATH.exists():
        sys.exit(f"Master YAML not found at {MASTER_PATH}")

    # Validate the YAML through the app's own loader, so a malformed file fails
    # here (loudly) rather than storing garbage.
    master = load_master(MASTER_PATH)

    with SessionLocal() as db:
        if target_email is not None:
            user = db.execute(
                select(User).where(User.email == target_email)
            ).scalar_one_or_none()
            if user is None:
                sys.exit(f"No user with email {target_email}. Seed one first.")
        else:
            user = db.execute(
                select(User).order_by(User.created_at).limit(1)
            ).scalar_one_or_none()
            if user is None:
                sys.exit("No users exist. Run scripts/seed_user.py first.")

        # Store the validated resume as its dict, same as the PUT /resume/master
        # route does. The service handles create-vs-replace.
        upsert_master(db, user.id, master.model_dump())
        print(f"Loaded master resume from {MASTER_PATH.name} into {user.email} (id {user.id}).")


if __name__ == "__main__":
    main()
