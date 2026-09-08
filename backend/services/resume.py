"""Master-resume persistence: read and save one user's master resume.

The master used to be a YAML file loaded by services/resume_render.load_master.
Now it lives in the `resumes` table (one row per user), so these two functions
are the DB-backed replacement the builder UI and the tailoring/render routes
read through.

HTTP-ignorant like every service: plain arguments in, a model (or None) out, no
HTTPException. The routes turn a None into a 404.

Note the `resume_json: dict`, not a strict `Resume`: the builder saves work in
progress that may not yet satisfy Resume's required fields (name, degree, ...),
so we store the raw dict loosely here and only validate to the strict `Resume`
later, at the moment it must actually render or be tailored.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.resume import MasterResume
from schemas.resume import Resume
from services.tailoring import cap_bold_spans, fit_to_one_page


def get_master(db: Session, user_id: str) -> MasterResume | None:
    # user_id is unique on the table, so this is one row or none — never a list.
    stmt = select(MasterResume).where(MasterResume.user_id == user_id)
    return db.execute(stmt).scalar_one_or_none()


def upsert_master(
    db: Session, user_id: str, resume_json: dict
) -> MasterResume:
    """Update the user's master if it exists, otherwise create it.

    "Upsert" = update-or-insert. There is at most one master per user (the
    unique constraint enforces it), so we look for it and branch:
    """
    master = get_master(db, user_id)

    if master is not None:
        # Existing row: reassign the blob. The row is already session-tracked,
        # so no db.add is needed — commit flushes the change and the onupdate
        # hook restamps updated_at.
        master.resume_json = resume_json
    else:
        # First save for this user: create the one row they get.
        master = MasterResume(user_id=user_id, resume_json=resume_json)
        db.add(master)

    db.commit()
    db.refresh(master)
    return master


# --- The general-purpose base resume ----------------------------------------
# What to print when there is no job to tailor against: a career fair, a club,
# a workshop. It is DERIVED from the master rather than stored, which is the
# whole point — a second stored resume is a second thing to edit and a second
# thing to drift (the master YAML vs DB problem, one level down).
#
# No model call. Selection is positional because the master is already ordered
# strongest-first, the same assumption `fit_to_one_page` makes when it cuts from
# the end. That means the user tunes their base resume by REORDERING in the
# builder they already have, not by maintaining a separate document.

# Enough to fill a page before trimming. Deliberately generous: the page is
# measured and cut down afterwards, and asking low leaves the page short with no
# later step able to fix it.
_BASE_BULLETS_PER_JOB = 4
_BASE_BULLETS_PER_PROJECT = 3
_BASE_PROJECTS = 3
_BASE_BULLETS_PER_ACTIVITY = 1
# A project's tool list is a single line in the template. The master holds every
# tool ever used (M.I.L.E.S. lists 15); printing them all wraps the line and
# costs the page.
_BASE_TOOLS_PER_PROJECT = 5


def build_base_resume(master: Resume) -> tuple[Resume, list[str]]:
    """Derive the one-page general resume from `master`. Returns it and the cuts.

    Pure and deterministic: same master in, same resume out, no API call. The
    one-page guarantee comes from `fit_to_one_page`, the identical measured trim
    the tailoring path uses, so the base resume and a tailored resume can never
    disagree about what fits.
    """
    base = master.model_copy(deep=True)

    for job in base.experience:
        job.bullets = job.bullets[:_BASE_BULLETS_PER_JOB]
    base.projects = [p for p in base.projects if p.bullets][:_BASE_PROJECTS]
    for project in base.projects:
        project.bullets = project.bullets[:_BASE_BULLETS_PER_PROJECT]
        project.tools = project.tools[:_BASE_TOOLS_PER_PROJECT]
    for activity in base.activities:
        activity.bullets = activity.bullets[:_BASE_BULLETS_PER_ACTIVITY]
    # A base resume is never tailored to a posting, so it carries no summary for
    # the same reason a tailored one does not.
    base.summary = None

    # The same emphasis rules the tailored path enforces. This is not belt-and-
    # braces: the base resume never passes through the model, so nothing else
    # would apply them, and the master banks the tutoring bullet with
    # "**3 students**" marked — a small number bolded beside a page of
    # percentages and millisecond timings.
    cap_bold_spans(base)

    return fit_to_one_page(base)
