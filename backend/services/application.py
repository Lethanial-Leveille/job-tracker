from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.application import Application, ApplicationStatus
from models.status_event import StatusEvent, StatusEventSource
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
    application = db.execute(stmt).scalar_one_or_none()
    if application is not None:
        application.applied_at = _first_applied_at(db, application_id)
    return application


def _first_applied_at(db: Session, application_id: str) -> object | None:
    """The single-row version of the query below."""
    stmt = select(func.min(StatusEvent.created_at)).where(
        StatusEvent.application_id == application_id,
        StatusEvent.to_status == ApplicationStatus.applied,
    )
    return db.execute(stmt).scalar_one_or_none()


def _applied_at_by_application(db: Session, user_id: str) -> dict[str, object]:
    """When each of this user's applications first reached `applied`.

    Derived from the status history rather than stored, so there is no column
    and no migration: the FIRST `applied` event IS the submitted date. MIN()
    matters because a row can re-enter `applied` (an interview falls through and
    you set it back), and the original submission is the one that dates it.

    ONE grouped query for the whole list. The obvious alternative — reading
    `application.status_events` per row — is a 65-query N+1 on a list that is
    currently a single SELECT, which is the kind of regression that only shows
    up in production.
    """
    stmt = (
        select(StatusEvent.application_id, func.min(StatusEvent.created_at))
        .where(
            StatusEvent.user_id == user_id,
            StatusEvent.to_status == ApplicationStatus.applied,
        )
        .group_by(StatusEvent.application_id)
    )
    return {row[0]: row[1] for row in db.execute(stmt).all()}


def list_applications(db: Session, user_id: str) -> list[Application]:
    stmt = (
        select(Application)
        .where(Application.user_id == user_id)
        .order_by(Application.created_at.desc())
    )
    applications = list(db.execute(stmt).scalars().all())
    # Attach the derived field. `applied_at` is not a mapped column, so this is a
    # plain instance attribute that Pydantic's from_attributes reads like any
    # other. Set on EVERY row, including None, so the schema never falls back to
    # its default for a row that simply has no applied event.
    applied = _applied_at_by_application(db, user_id)
    for application in applications:
        application.applied_at = applied.get(application.id)
    return applications


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
