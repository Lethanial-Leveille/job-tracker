"""Pydantic schemas for saving and reading tailored resume versions.

The API contract for the resume_versions table. Two shapes:

    ResumeVersionCreate — the POST body: which application, the reviewed Resume,
                          and the job description it was tailored against.
    ResumeVersionRead   — the response body: the stored version, with resume_json
                          handed back as a validated Resume (not a raw dict).

Storage vs API mismatch, handled explicitly: the ORM row keeps the resume as a
`resume_json` dict (JSON column), but the API should return a real `Resume`. We
map that in `from_row` rather than leaning on attribute aliases — one obvious
place, no serialization surprises.
"""

from datetime import datetime

from pydantic import BaseModel

from models.resume_version import ResumeVersion
from schemas.resume import Resume


class ResumeVersionCreate(BaseModel):
    """The POST body. The frontend sends this after you review a tailored draft
    (hard rule #1: nothing is saved without your explicit action)."""

    application_id: str
    resume: Resume
    job_description: str


class ResumeVersionRead(BaseModel):
    """The response body. `resume` is the stored version, validated back into a
    Resume so callers get a typed object, not a loose dict."""

    id: str
    application_id: str
    resume: Resume
    job_description: str
    created_at: datetime

    @classmethod
    def from_row(cls, row: ResumeVersion) -> "ResumeVersionRead":
        """Build a Read from a ResumeVersion ORM row, validating the stored
        resume_json dict back into a Resume."""
        return cls(
            id=row.id,
            application_id=row.application_id,
            resume=Resume.model_validate(row.resume_json),
            job_description=row.job_description,
            created_at=row.created_at,
        )
