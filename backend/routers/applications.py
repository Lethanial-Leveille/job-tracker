from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from database import get_db
from models.application import Application
from schemas.application import ApplicationCreate, ApplicationResponse, ApplicationUpdate
from services.jd_parser import parse_jd

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("/", response_model=list[ApplicationResponse])
def list_applications(
    status: str | None = Query(default=None),
    type: str | None = Query(default=None),
    priority: str | None = Query(default=None),
    db: Session = Depends(get_db),
) -> list[Application]:
    stmt = select(Application)
    if status:
        stmt = stmt.where(Application.status == status)
    if type:
        stmt = stmt.where(Application.type == type)
    if priority:
        stmt = stmt.where(Application.priority == priority)
    return list(db.execute(stmt).scalars().all())


@router.post("/", response_model=ApplicationResponse, status_code=201)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db)) -> Application:
    # Parse the JD first so we can fall back to Claude's inferences
    # for any fields the caller didn't provide
    jd_text, jd_parsed = parse_jd(str(body.posting_url))

    app = Application(
        type=body.type or jd_parsed.get("inferred_type", "internship"),
        organization=body.organization or jd_parsed.get("inferred_organization", "Unknown"),
        role_or_program=body.role_or_program or jd_parsed.get("inferred_role", "Unknown Role"),
        posting_url=str(body.posting_url),
        deadline=body.deadline,
        priority=body.priority,
        notes=body.notes,
        jd_text=jd_text,
        jd_parsed=jd_parsed,
    )

    db.add(app)
    db.commit()
    db.refresh(app)
    return app


@router.get("/{application_id}", response_model=ApplicationResponse)
def get_application(application_id: str, db: Session = Depends(get_db)) -> Application:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.patch("/{application_id}", response_model=ApplicationResponse)
def update_application(
    application_id: str,
    body: ApplicationUpdate,
    db: Session = Depends(get_db),
) -> Application:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")

    # model_dump(exclude_unset=True) returns only the fields the client actually sent,
    # so PATCH {"status": "applied"} won't accidentally wipe out priority or notes
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(app, field, value)

    db.commit()
    db.refresh(app)
    return app


@router.delete("/{application_id}", status_code=204)
def delete_application(application_id: str, db: Session = Depends(get_db)) -> None:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    db.delete(app)
    db.commit()
