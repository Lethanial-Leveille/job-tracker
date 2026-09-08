"""Dump a user's master resume OUT of the database and into YAML.

The inverse of load_master_from_yaml.py, and the direction that matters now.

Background: the master resume used to live in backend/data/master_resume.yaml
and be pushed INTO the database. That made the file the source of truth and the
database a copy, which meant two editors (this file and the resume builder UI)
racing to overwrite each other, and a manual sync per machine that left
production stale for weeks at a time.

The direction is now inverted. The DATABASE is the source of truth, edited in
the builder UI from any device. This script writes a YAML snapshot so the bullet
bank stays in git, where its history has already earned its keep: a rewrite pass
on 2026-09-03 silently deleted 14 real facts and git is how they came back.

So: edit in the UI, run this occasionally, commit the result. The YAML is a
backup and a diffable record, never an input. load_master_from_yaml.py stays as
a rescue and seeding tool, not part of the routine.

Run it from backend/ with the venv active:

    python scripts/dump_master_to_yaml.py                     # -> data/master_resume.snapshot.yaml
    python scripts/dump_master_to_yaml.py you@x.com           # a specific user
    python scripts/dump_master_to_yaml.py --out data/snap.yaml
    python scripts/dump_master_to_yaml.py --stdout            # print, write nothing

On the droplet the app lives at /opt/job-tracker and uses uv, so it reads:

    cd /opt/job-tracker/backend && export PATH="$HOME/.local/bin:$PATH"
    uv run python scripts/dump_master_to_yaml.py you@x.com --stdout > master.yaml
"""

import os
import sys
from pathlib import Path

# Put backend/ on the import path so `from services...` works when run directly
# as a file (same trick as load_master_from_yaml.py / build_base_resume.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import yaml  # noqa: E402
from sqlalchemy import select  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.user import User  # noqa: E402
from schemas.resume import Resume  # noqa: E402
from services.resume import get_master  # noqa: E402

# NOT master_resume.yaml. That file is hand-annotated — the bench markers, the
# note on why merged-PR counts are excluded, the measured reason coursework stops
# at three — and a YAML dump cannot preserve comments, so writing over it would
# destroy the reasoning to save the data. The snapshot is a separate, diffable
# record of what the database actually holds.
DEFAULT_OUT = (
    Path(__file__).resolve().parent.parent / "data" / "master_resume.snapshot.yaml"
)


def _resolve_user(db, email: str | None) -> User:
    """The named user, or the oldest one when no email is given.

    Same rule as the loader: prod has more than one user, so passing the email
    is the safe habit. Defaulting to the oldest keeps the common single-user
    case a bare command.
    """
    if email:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user is None:
            sys.exit(f"No user with email {email!r}.")
        return user
    user = db.execute(select(User).order_by(User.created_at)).scalars().first()
    if user is None:
        sys.exit("No users in this database.")
    return user


def _dump(resume: Resume) -> str:
    """Serialise to YAML in the shape load_master() reads back.

    `exclude_none` keeps optional-but-unset fields (phone, dates_alternate) out
    of the file rather than writing a wall of `null`s, and every one of them has
    a default on the model, so the file still round-trips.

    sort_keys=False preserves the model's field order, which is the order a
    human reads a resume in: contact, education, skills, experience, projects.
    Alphabetising it would make every future diff unreadable.
    """
    data = resume.model_dump(exclude_none=True)
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=10_000)


def main() -> None:
    args = [a for a in sys.argv[1:]]
    to_stdout = "--stdout" in args
    out = DEFAULT_OUT
    if "--out" in args:
        out = Path(args[args.index("--out") + 1])
        args = [a for a in args if a != "--out" and a != str(out)]
    email = next((a for a in args if not a.startswith("--")), None)

    db = SessionLocal()
    try:
        user = _resolve_user(db, email)
        master = get_master(db, user.id)
        if master is None:
            sys.exit(f"{user.email} has no master resume saved.")
        # Validate on the way out: a blob that cannot satisfy Resume would
        # produce a YAML file the loader could never read back, and a backup you
        # cannot restore from is not a backup.
        resume = Resume.model_validate(master.resume_json)
        text = _dump(resume)
    finally:
        db.close()

    if to_stdout:
        sys.stdout.write(text)
        return

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text)
    bullets = (
        sum(len(e.bullets) for e in resume.experience)
        + sum(len(p.bullets) for p in resume.projects)
        + sum(len(a.bullets) for a in resume.activities)
    )
    print(f"Wrote {out} for {user.email}")
    print(
        f"  {len(resume.experience)} experience, {len(resume.projects)} projects, "
        f"{len(resume.activities)} activities, {bullets} bullets total"
    )
    print("  Commit it: this is the versioned record of what prod actually holds.")


if __name__ == "__main__":
    main()
