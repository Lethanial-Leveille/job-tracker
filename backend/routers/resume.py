"""Resume tailoring routes: the HTTP surface over the two resume services.

Two endpoints, one per half of the content-vs-format split (see decisions.md,
"v2 resume tailoring"):

- POST /resume/tailor : JD text in  -> tailored Resume JSON out (runs Opus).
- POST /resume/render : a Resume in -> PDF bytes out (pure, no API call).

They are split on purpose. The tailored Resume is the reviewable draft (hard
rule #1, nothing auto-submits); the PDF is a download of an already-reviewed
draft. Keeping them separate means the expensive Opus call happens once, and
re-rendering after an edit costs nothing. The frontend holds the Resume JSON
between the two calls.
"""

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from schemas.resume import Resume, TailorRequest
from schemas.resume_version import ResumeVersionCreate, ResumeVersionRead
from services.application import get_application
from services.resume_render import load_master, render_resume_pdf
from services.resume_version import list_resume_versions, save_resume_version
from services.tailoring import tailor_resume

# data/ is a sibling of routers/ under backend/, same relative-path convention
# resume_render.py uses for templates/. This is the bullet-bank master resume.
_MASTER_PATH = Path(__file__).resolve().parent.parent / "data" / "master_resume.yaml"

router = APIRouter(prefix="/resume", tags=["resume"])


@router.post("/tailor", response_model=Resume)
def tailor(
    data: TailorRequest, settings: Settings = Depends(get_settings)
) -> Resume:
    # Tailor only — this never renders or writes anything. Opus selects and
    # rephrases the master's own content for this JD; you review the returned
    # Resume before rendering (the "never auto-submit" guardrail). None means
    # Claude refused or the reply was truncated, same as the parse route.
    master = load_master(_MASTER_PATH)
    result = tailor_resume(master, data.text, settings)
    if result is None:
        raise HTTPException(status_code=502, detail="Could not tailor the resume")
    return result


@router.post("/render")
def render(resume: Resume) -> Response:
    # Returns raw PDF bytes, so we hand back a bare Response instead of a model:
    # FastAPI JSON-encodes anything else it's given. Content-Disposition
    # "attachment" makes the browser download the file rather than display it.
    # No settings dependency — rendering is pure and hits no API. A WeasyPrint
    # failure propagates as a 500 (a real bug, not an expected condition like
    # tailor's None), so it isn't dressed up as a friendly error.
    pdf_bytes = render_resume_pdf(resume)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="resume.pdf"'},
    )


@router.post(
    "/versions",
    response_model=ResumeVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    data: ResumeVersionCreate, db: Session = Depends(get_db)
) -> ResumeVersionRead:
    # Explicit save (2a): the frontend calls this only after you review a tailored
    # draft. We verify the application exists first and 404 if not — SQLite does
    # not enforce the foreign key, so this guard is what actually prevents an
    # orphaned version pointing at no application.
    if get_application(db, data.application_id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    row = save_resume_version(db, data)
    return ResumeVersionRead.from_row(row)


@router.get("/versions", response_model=list[ResumeVersionRead])
def list_versions(
    application_id: str, db: Session = Depends(get_db)
) -> list[ResumeVersionRead]:
    # application_id is a required query param (?application_id=...). Returns that
    # application's saved versions, newest first; an empty list if it has none.
    rows = list_resume_versions(db, application_id)
    return [ResumeVersionRead.from_row(r) for r in rows]
