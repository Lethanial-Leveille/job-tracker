"""Persistence for tailored resume versions: save one, list an application's.

Business logic for the resume_versions table, HTTP-ignorant like the other
services (takes a Session and plain data, returns ORM rows). The route layer
owns validation and status codes; a non-HTTP caller could reuse these directly.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.resume_version import ResumeVersion
from schemas.resume_version import ResumeVersionCreate


def save_resume_version(db: Session, data: ResumeVersionCreate) -> ResumeVersion:
    """Persist a reviewed, tailored resume as a new version row.

    The Resume is stored as a dict (model_dump) in the JSON column; job_description
    is the snapshot of what it targeted. Append-only — this always inserts a new
    row, never updates an existing one.
    """
    version = ResumeVersion(
        application_id=data.application_id,
        resume_json=data.resume.model_dump(),
        job_description=data.job_description,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return version


def list_resume_versions(db: Session, application_id: str) -> list[ResumeVersion]:
    """Return an application's saved versions, newest first."""
    stmt = (
        select(ResumeVersion)
        .where(ResumeVersion.application_id == application_id)
        .order_by(ResumeVersion.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())
