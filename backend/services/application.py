from sqlalchemy import select
from sqlalchemy.orm import Session

from models.application import Application
from models.status_event import StatusEventSource
from schemas.application import ApplicationCreate, ApplicationUpdate
from services.status_event import record_status_event


def create_application(
    db: Session, data: ApplicationCreate, user_id: str
) -> Application:
    # user_id comes from the authenticated user, never the request body — a
    # client cannot choose who owns a row.
    application = Application(**data.model_dump(), user_id=user_id)
    db.add(application)
    # Flush to assign the generated id before recording the opening history entry
    # (from_status=None marks it as the row's first status).
    db.flush()
    record_status_event(
        db,
        user_id=user_id,
        application_id=application.id,
        from_status=None,
        to_status=application.status,
        source=StatusEventSource.manual,
    )
    db.commit()
    db.refresh(application)
    return application


def get_application(
    db: Session, application_id: str, user_id: str
) -> Application | None:
    # Scoped by owner: another user's row is invisible (returns None, so the
    # route 404s). We never reveal that a row belonging to someone else exists.
    stmt = select(Application).where(
        Application.id == application_id, Application.user_id == user_id
    )
    return db.execute(stmt).scalar_one_or_none()


def list_applications(db: Session, user_id: str) -> list[Application]:
    stmt = (
        select(Application)
        .where(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
    )
    return list(db.execute(stmt).scalars().all())


def update_application(
    db: Session, data: ApplicationUpdate, application_id: str, user_id: str
) -> Application | None:
    # Reuse the scoped fetch so ownership is enforced in exactly one place.
    application = get_application(db, application_id, user_id)
    if application is None:
        return None
    old_status = application.status
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(application, field, value)
    # Record a history entry only when the status actually changed (editing the
    # notes or deadline is not a status event).
    if "status" in update_data and application.status != old_status:
        record_status_event(
            db,
            user_id=user_id,
            application_id=application.id,
            from_status=old_status,
            to_status=application.status,
            source=StatusEventSource.manual,
        )
    db.commit()
    db.refresh(application)
    return application


def delete_application(
    db: Session, application_id: str, user_id: str
) -> Application | None:
    application = get_application(db, application_id, user_id)
    if application is None:
        return None
    db.delete(application)
    db.commit()
    return application
