from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.application import ApplicationCreate, ApplicationRead, ApplicationUpdate
from schemas.fit import FitReport
from schemas.parsing import ParsedJob, ParseRequest
from schemas.resume import Resume
from schemas.status_event import StatusEventRead
from services.application import (
    create_application,
    delete_application,
    get_application,
    list_applications,
    update_application,
)
from services.matching import assess_requirements
from services.parsing import parse_job_description
from services.resume import get_master
from services.status_event import delete_status_event, list_status_events

# dependencies=[Depends(get_current_user)] protects EVERY route in this router by
# default — you can't forget to guard one. Handlers that need the owner also
# declare `user: User = Depends(get_current_user)`; FastAPI resolves it once per
# request, so asking for it twice costs nothing.
router = APIRouter(
    prefix="/applications",
    tags=["applications"],
    dependencies=[Depends(get_current_user)],
)


@router.post("", response_model=ApplicationRead, status_code=status.HTTP_201_CREATED)
def create(
    data: ApplicationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationRead:
    return create_application(db, data, user.id)


@router.post("/parse", response_model=ParsedJob)
def parse(data: ParseRequest, settings: Settings = Depends(get_settings)) -> ParsedJob:
    # Parse only — never writes a row. Protected by the router-level dependency
    # (it spends a paid API call, so it must not be anonymous), but it needs no
    # user id since it persists nothing. You review and submit through create.
    result = parse_job_description(data.text, settings)
    if result is None:
        raise HTTPException(status_code=502, detail="Could not parse the posting")
    return result


@router.get("/{application_id}", response_model=ApplicationRead)
def read_one(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationRead:
    result = get_application(db, application_id, user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.get("/{application_id}/timeline", response_model=list[StatusEventRead])
def timeline(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[StatusEventRead]:
    # Scoped 404 if it isn't yours; otherwise the status history, oldest first.
    if get_application(db, application_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return list_status_events(db, application_id, user.id)


@router.delete(
    "/{application_id}/timeline/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_timeline_event(
    application_id: str,
    event_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    # Prune one history entry (a corrected misclick). Scoped: the application and
    # the event must both be yours. Does not change the current status.
    if get_application(db, application_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Application not found")
    if not delete_status_event(db, event_id, user.id):
        raise HTTPException(status_code=404, detail="Timeline entry not found")


@router.get("", response_model=list[ApplicationRead])
def list_all(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[ApplicationRead]:
    return list_applications(db, user.id)


@router.patch("/{application_id}", response_model=ApplicationRead)
def update(
    application_id: str,
    data: ApplicationUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationRead:
    result = update_application(db, data, application_id, user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return result


@router.post("/{application_id}/fit", response_model=FitReport)
def compute_fit(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> FitReport:
    """Judge this posting's stated requirements against the user's master resume.

    POST, not GET, for two reasons: it spends a paid API call, and it writes the
    result back to the row. GET is expected to be safe and repeatable, and this
    is neither. Callers that just want the last computed report read `fit_report`
    off the application itself — no call, no cost.
    """
    application = get_application(db, application_id, user.id)
    if application is None:
        raise HTTPException(status_code=404, detail="Application not found")

    master_row = get_master(db, user.id)
    if master_row is None:
        raise HTTPException(
            status_code=400,
            detail="Create your master resume before checking requirements",
        )

    # The requirements come from the parser's stored extras. A row added by hand
    # has no jd_parsed at all, which is not an error — there is simply nothing to
    # judge against, and saying so beats returning an empty report that reads
    # like a perfect score.
    parsed = application.jd_parsed or {}
    requirements = parsed.get("key_requirements") or []
    # Absent on every row stored before the parser split the two lists, and on
    # postings that simply have no "we prefer" section.
    preferred = parsed.get("preferred_qualifications") or []
    if not requirements and not preferred:
        raise HTTPException(
            status_code=400,
            detail="This posting has no extracted requirements to check",
        )

    master = Resume.model_validate(master_row.resume_json)
    report = assess_requirements(master, requirements, settings, preferred=preferred)
    if report is None:
        raise HTTPException(
            status_code=502, detail="Could not assess the requirements"
        )

    # Cache it on the row so reopening the application costs nothing.
    application.fit_report = report.model_dump(mode="json")
    application.fit_computed_at = report.computed_at
    db.commit()

    return report


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete(
    application_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    result = delete_application(db, application_id, user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return None
