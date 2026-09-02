"""One-off: give a self-imposed deadline to applications that have none.

The add flow now defaults a new application's deadline to a week out, because a
row with no deadline sorts last and quietly sinks out of view. Rows added before
that change still have NULL, so they are exactly the ones most likely to be
forgotten.

Be clear about what this writes: these dates are INVENTED. The postings did not
state them. They are Lee's own "apply by" dates, not facts about the posting, and
they are indistinguishable in the database from a real scraped deadline. That is
the trade being made deliberately — a made-up date that surfaces the row beats a
NULL that hides it — but it is the reason this script is a dry run by default and
prints every row it would touch.

Only rows with deadline IS NULL are touched, so it is safe to re-run and can
never overwrite a real posted deadline.

Run it from backend/ with the venv active:

    python scripts/backfill_deadlines.py                 # show the plan
    python scripts/backfill_deadlines.py --apply         # write it
    python scripts/backfill_deadlines.py --days 14       # a different horizon
    python scripts/backfill_deadlines.py you@x.com       # a specific user
"""

import os
import sys
from datetime import date, timedelta

# Put backend/ on the import path so `from database import ...` works when run
# directly as a file (same trick as the other scripts here).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402

from database import SessionLocal  # noqa: E402
from models.application import Application, ApplicationStatus  # noqa: E402
from models.user import User  # noqa: E402

# Statuses meaning "already out the door". A future apply-by date on one of these
# is noise: there is nothing left to do by that date. They are still listed so the
# choice to include them is visible rather than silent.
SUBMITTED = {
    ApplicationStatus.applied,
    ApplicationStatus.recruiter_engaged,
    ApplicationStatus.phone_screen,
    ApplicationStatus.technical_interview,
    ApplicationStatus.onsite,
    ApplicationStatus.offer,
    ApplicationStatus.accepted,
    ApplicationStatus.declined,
    ApplicationStatus.rejected,
    ApplicationStatus.ghosted,
}


def main() -> None:
    args = sys.argv[1:]
    apply = "--apply" in args
    skip_submitted = "--skip-submitted" in args

    days = 7
    if "--days" in args:
        try:
            days = int(args[args.index("--days") + 1])
        except (IndexError, ValueError):
            sys.exit("--days needs a whole number, e.g. --days 14")

    positional = [a for a in args if not a.startswith("--") and not a.isdigit()]
    target_email = positional[0].strip() if positional else None

    # The server runs UTC, so "today" here is the UTC date. At most a few hours
    # off from Lee's local date, which does not matter for a self-imposed
    # deadline measured in days.
    target_date = date.today() + timedelta(days=days)

    with SessionLocal() as db:
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
                .where(Application.deadline.is_(None))
                .order_by(Application.created_at)
            ).scalars()
        )

        if not rows:
            print(f"Nothing to do: every application for {user.email} has a deadline.")
            return

        targets = [r for r in rows if not (skip_submitted and r.status in SUBMITTED)]
        submitted = [r for r in rows if r.status in SUBMITTED]

        print(
            f"{len(rows)} application(s) for {user.email} have no deadline. "
            f"Setting {len(targets)} to {target_date} ({days} days out).\n"
        )
        width = max(len(r.organization) for r in rows)
        for row in rows:
            skipped = skip_submitted and row.status in SUBMITTED
            mark = "skip" if skipped else str(target_date)
            print(f"  {row.organization:{width}}  {row.status.value:<12}  {mark}")

        if submitted and not skip_submitted:
            print(
                f"\nNote: {len(submitted)} of these are already submitted, where an "
                f"apply-by date means nothing. Use --skip-submitted to leave them NULL."
            )

        if not apply:
            print("\nDry run. Re-run with --apply to write these.")
            return

        for row in targets:
            row.deadline = target_date
        db.commit()
        print(f"\nWrote {len(targets)} deadline(s) of {target_date}.")


if __name__ == "__main__":
    main()
