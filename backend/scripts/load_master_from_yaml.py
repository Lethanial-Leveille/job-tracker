"""One-off: load the YAML master resume into the database for a user.

Background: the master resume used to live only as backend/data/master_resume.yaml.
Now each user's master lives in the `resumes` table (see models/resume.py). This
script bridges the two — it reads the YAML, validates it through the same
`load_master` the app uses, and upserts it into one user's row — so my existing
resume survives the file-to-DB move without being re-entered by hand.

It is idempotent: `upsert_master` replaces the row if it already exists, so
running it twice just reloads the file.

That replacement is the dangerous part, and the reason for the diff below. The
master now has TWO editors: this file and the resume builder UI. A plain
overwrite silently discards anything typed into the builder since the last load,
which nearly happened on 2026-08-25 (prod had been edited an hour earlier). So
the script now prints what would change and REFUSES to run if the stored resume
holds a bullet the YAML does not, unless you pass --force. Losing work should
take an explicit flag, not a default.

Run it from backend/ with the venv active:

    python scripts/load_master_from_yaml.py            # loads into the oldest user (me)
    python scripts/load_master_from_yaml.py you@x.com  # loads into a specific user
    python scripts/load_master_from_yaml.py --dry-run  # print the diff, write nothing
    python scripts/load_master_from_yaml.py --force    # overwrite builder-only edits

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
from services.resume import get_master, upsert_master  # noqa: E402
from services.resume_render import load_master  # noqa: E402

# data/ is a sibling of scripts/ under backend/ — same file as the app used.
MASTER_PATH = Path(__file__).resolve().parent.parent / "data" / "master_resume.yaml"


def _bullet_index(resume: dict) -> dict[str, list[str]]:
    """Map every entry to its bullets, keyed by "section: entry name".

    Flattening both sections into one dict keeps the comparison below simple:
    one loop over keys instead of a separate pass for experience and projects.
    """
    index: dict[str, list[str]] = {}
    for entry in resume.get("experience", []):
        index[f"experience: {entry.get('organization')}"] = entry.get("bullets", [])
    for entry in resume.get("projects", []):
        index[f"project: {entry.get('name')}"] = entry.get("bullets", [])
    return index


def report_changes(stored: dict, incoming: dict) -> list[str]:
    """Print what the load would change; return the bullets it would DESTROY.

    "Destroy" means present in the stored resume and absent from the YAML — the
    builder-only edits. Everything else the load is free to change, since the
    YAML is meant to win on content it actually carries.
    """
    for field in ("career_stage", "summary", "contact", "education", "skills"):
        if stored.get(field) != incoming.get(field):
            print(f"  {field}: differs, YAML wins")

    stored_bullets, incoming_bullets = _bullet_index(stored), _bullet_index(incoming)
    lost: list[str] = []
    for key, bullets in stored_bullets.items():
        only_stored = [b for b in bullets if b not in incoming_bullets.get(key, [])]
        added = len([b for b in incoming_bullets.get(key, []) if b not in bullets])
        if added:
            print(f"  {key}: +{added} bullet(s) from YAML")
        for bullet in only_stored:
            lost.append(f"{key}: {bullet}")
    for key in incoming_bullets:
        if key not in stored_bullets:
            print(f"  {key}: new entry from YAML")
    return lost


def main() -> None:
    # Flags are pulled out first so the positional email arg keeps working in any
    # order: `... --dry-run you@x.com` and `... you@x.com --dry-run` both parse.
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    force = "--force" in args
    positional = [a for a in args if not a.startswith("--")]

    # Optional first arg: the target user's email. Without it, default to the
    # oldest user (that's me — created first), matching how discovery/backfill
    # resolve "the owner".
    target_email = positional[0].strip() if positional else None

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

        incoming = master.model_dump()

        # Compare against what is already stored BEFORE writing. A first-time
        # load has nothing to lose, so the whole check is skipped.
        stored = get_master(db, user.id)
        if stored is not None:
            print(f"Changes for {user.email} (stored {stored.updated_at}):")
            lost = report_changes(stored.resume_json, incoming)
            if lost and not force:
                print(f"\n{len(lost)} bullet(s) exist only in the database and would be DESTROYED:")
                for item in lost:
                    print(f"  - {item[:140]}")
                sys.exit(
                    "\nRefusing to overwrite. Copy these into the YAML first, "
                    "or re-run with --force to discard them."
                )
            if lost:
                print(f"\n--force: discarding {len(lost)} database-only bullet(s).")
        else:
            print(f"No master stored for {user.email} yet; this is a first load.")

        if dry_run:
            print("\n--dry-run: nothing written.")
            return

        # Store the validated resume as its dict, same as the PUT /resume/master
        # route does. The service handles create-vs-replace.
        upsert_master(db, user.id, incoming)
        print(f"\nLoaded master resume from {MASTER_PATH.name} into {user.email} (id {user.id}).")


if __name__ == "__main__":
    main()
