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
