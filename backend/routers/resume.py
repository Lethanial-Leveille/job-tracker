"""Resume routes: the HTTP surface over the resume services.

The master-resume endpoints are the per-user source of truth — one master
resume per user, stored in the DB and edited by the builder UI. Tailor and
render are the content-vs-format split layered over it (see decisions.md,
"v2 resume tailoring"):

- GET  /resume/master : the user's saved master Resume (404 if none yet).
- PUT  /resume/master : create-or-replace the user's master Resume.
- POST /resume/tailor : JD text in  -> tailored Resume JSON out (runs Opus).
- POST /resume/render : a Resume in -> PDF bytes out (pure, no API call).

Tailor and render are split on purpose. The tailored Resume is the reviewable
draft (hard rule #1, nothing auto-submits); the PDF is a download of an
already-reviewed draft. Keeping them separate means the expensive Opus call
happens once, and re-rendering after an edit costs nothing. The frontend holds
the Resume JSON between the two calls.
"""

from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.resume import Resume, TailorRequest
from schemas.resume_version import ResumeVersionCreate, ResumeVersionRead
from services.application import get_application
from services.resume import get_master, upsert_master
from services.resume_render import render_resume_pdf, resume_filename
from services.resume_version import list_resume_versions, save_resume_version
from services.tailoring import tailor_resume

router = APIRouter(
    prefix="/resume",
    tags=["resume"],
    dependencies=[Depends(get_current_user)],
)


@router.get("/master", response_model=Resume)
def get_master_resume(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Resume:
    # The user's stored master resume. 404 when they don't have one yet — the
    # builder UI reads that as "start from a blank resume". Stored data always
    # went in through the Resume schema (see PUT below), so it is always valid
    # to read back out through it.
    master = get_master(db, user.id)
    if master is None:
        raise HTTPException(status_code=404, detail="No master resume yet")
    return Resume.model_validate(master.resume_json)


@router.put("/master", response_model=Resume)
def put_master_resume(
    resume: Resume,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Resume:
    # Save (create-or-replace) the user's master. The body is a full Resume, not
    # a raw dict (the "no raw dicts" convention) — and because Resume's required
    # fields are unconstrained strings, a half-filled resume with empty strings
    # still validates, so the builder can save work in progress. We persist the
    # model_dump() dict; the service stays schema-agnostic.
    row = upsert_master(db, user.id, resume.model_dump())
    return Resume.model_validate(row.resume_json)


@router.post("/tailor", response_model=Resume)
def tailor(
    data: TailorRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> Resume:
    # Tailor only — this never renders or writes anything. The master now comes
    # from the DB per user (not one shared YAML file), so tailoring is genuinely
    # multi-user: each person tailors their OWN resume. 400 if they have not
    # built one yet. Opus selects and rephrases the master's own content for this
    # JD; you review the returned Resume before rendering (the "never auto-submit"
    # guardrail). None means Claude refused or the reply was truncated, like the
    # parse route.
    master_row = get_master(db, user.id)
    if master_row is None:
        raise HTTPException(
            status_code=400,
            detail="Create your master resume before tailoring",
        )
    master = Resume.model_validate(master_row.resume_json)
    result = tailor_resume(master, data.text, settings)
    if result is None:
        raise HTTPException(status_code=502, detail="Could not tailor the resume")
    return result


@router.post("/render")
def render(
    resume: Resume,
    company: str | None = None,
    grad_date: Literal["primary", "alternate"] | None = None,
) -> Response:
    # Returns raw PDF bytes, so we hand back a bare Response instead of a model:
    # FastAPI JSON-encodes anything else it's given. Content-Disposition
    # "attachment" makes the browser download the file rather than display it.
    # No settings dependency — rendering is pure and hits no API. A WeasyPrint
    # failure propagates as a 500 (a real bug, not an expected condition like
    # tailor's None), so it isn't dressed up as a friendly error.
    #
    # `company` and `grad_date` are QUERY params, not fields on Resume, on
    # purpose: Resume is the one shape shared by the master file, tailoring, and
    # the renderer, so a per-download presentation choice does not belong in it.
    #
    # `grad_date` overrides which of two true graduation dates prints (see
    # Education.dates_alternate). It is an explicit switch and never inferred:
    # tailoring is forbidden from choosing it, because guessing a program's
    # eligibility rules out of posting text and guessing wrong means printing a
    # date the user did not intend.
    if grad_date is not None:
        resume = resume.model_copy(update={"grad_date_variant": grad_date})
    pdf_bytes = render_resume_pdf(resume)
    filename = resume_filename(resume, company)
    # RFC 6266: an ASCII `filename` for old clients plus a percent-encoded
    # `filename*` for everything modern. resume_filename() has already folded the
    # value to ASCII and stripped quotes, so the quoted form cannot be escaped.
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"; '
                f"filename*=UTF-8''{quote(filename)}"
            )
        },
    )


@router.post(
    "/versions",
    response_model=ResumeVersionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_version(
    data: ResumeVersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ResumeVersionRead:
    # Explicit save (2a): the frontend calls this only after you review a tailored
    # draft. The scoped get_application 404s both when the application does not
    # exist AND when it belongs to another user — so you cannot attach a version
    # to someone else's application. That guard also compensates for SQLite not
    # enforcing the foreign key.
    if get_application(db, data.application_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    row = save_resume_version(db, data, user.id)
    return ResumeVersionRead.from_row(row)


@router.get("/versions", response_model=list[ResumeVersionRead])
def list_versions(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ResumeVersionRead]:
    # application_id is a required query param (?application_id=...). Returns that
    # application's saved versions owned by you, newest first; empty if none.
    rows = list_resume_versions(db, application_id, user.id)
    return [ResumeVersionRead.from_row(r) for r in rows]
