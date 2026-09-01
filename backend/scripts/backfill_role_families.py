"""One-off: classify the role_family of applications that predate the column.

The parser fills `role_family` on every new application, but rows added before
that column existed have none, so the list still shows their raw posted titles
("Summer 2027 Intern - Software Engineer", "Engineering Internship", ...). This
sends those titles to Claude once, in a single call, and fills the gap.

It is a DRY RUN by default. It prints every proposed change and writes nothing
until you pass --apply, because this edits rows you created by hand and the
model's answer is a judgment call, not a fact lookup. Read the table first.

Only rows with role_family IS NULL are touched, so it is safe to re-run and it
can never overwrite a family you chose yourself in the edit modal.

Run it from backend/ with the venv active:

    python scripts/backfill_role_families.py               # show the plan
    python scripts/backfill_role_families.py --apply       # write it
    python scripts/backfill_role_families.py you@x.com     # a specific user
"""

import os
import sys

# Put backend/ on the import path so `from database import ...` works when run
# directly as a file (same trick as load_master_from_yaml.py / seed_user.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from config import get_settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models.application import Application  # noqa: E402
from models.user import User  # noqa: E402
from services.parsing import classify_role_families  # noqa: E402


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    positional = [a for a in args if not a.startswith("--")]
    target_email = positional[0].strip() if positional else None

    with SessionLocal() as db:
        # Same owner resolution as load_master_from_yaml: an explicit email, or
        # the oldest user (that's me, created first).
        if target_email is not None:
            user = db.execute(
                select(User).where(User.email == target_email)
            ).scalar_one_or_none()
            if user is None:
                sys.exit(f"No user with email {target_email}.")
        else:
            user = db.execute(
                select(User).order_by(User.created_at).limit(1)
            ).scalar_one_or_none()
            if user is None:
                sys.exit("No users exist.")

        rows = list(
            db.execute(
                select(Application)
                .where(Application.user_id == user.id)
                .where(Application.role_family.is_(None))
                .order_by(Application.created_at)
            ).scalars()
        )

        if not rows:
            print(f"Nothing to do: every application for {user.email} has a role family.")
            return

        print(f"{len(rows)} application(s) for {user.email} have no role family.\n")

        classified = classify_role_families(
            [r.role_or_program for r in rows], get_settings()
        )
        if classified is None:
            sys.exit("Claude returned no classification. Nothing written.")

        # A row the model skipped stays NULL rather than being guessed at.
        missing = [i for i in range(len(rows)) if i not in classified]

        width = max(len(r.organization) for r in rows)
        for i, row in enumerate(rows):
            family = classified.get(i)
            arrow = family if family else "(unclassified, left alone)"
            print(f"  {row.organization:{width}}  {row.role_or_program}")
            print(f"  {'':{width}}  -> {arrow}\n")

        if missing:
            print(f"{len(missing)} row(s) came back unclassified and will be skipped.\n")

        if not apply:
            print("Dry run. Re-run with --apply to write these.")
            return

        for i, row in enumerate(rows):
            family = classified.get(i)
            if family is not None:
                row.role_family = family
        db.commit()
        print(f"Wrote {len(rows) - len(missing)} role families.")


if __name__ == "__main__":
    main()
