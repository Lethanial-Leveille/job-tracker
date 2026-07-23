from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.application import ApplicationCreate, ApplicationRead, ApplicationUpdate
from schemas.parsing import ParsedJob, ParseRequest
from services.application import (
    create_application,
    delete_application,
    get_application,
    list_applications,
    update_application,
)
from services.parsing import parse_job_description

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
