"""Recording and reading an application's status history.

`record_status_event` is called from the three places a status changes
(create/update application, accept a suggestion). It deliberately does NOT
commit: the caller commits the status change, and adding the event to that same
transaction keeps the change and its history entry atomic — you can never end up
with a status that has no matching event, or an event for a change that rolled
back.

HTTP-ignorant like every service.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.application import ApplicationStatus
from models.status_event import StatusEvent, StatusEventSource


def record_status_event(
    db: Session,
    *,
    user_id: str,
    application_id: str,
    from_status: ApplicationStatus | None,
    to_status: ApplicationStatus,
    source: StatusEventSource,
) -> None:
    """Stage one status-history row. Flushed by the caller's commit."""
    db.add(
        StatusEvent(
            user_id=user_id,
            application_id=application_id,
            from_status=from_status,
            to_status=to_status,
            source=source,
        )
    )


def list_status_events(
    db: Session, application_id: str, user_id: str
) -> list[StatusEvent]:
    """An application's history, oldest first (the order a timeline reads)."""
    stmt = (
        select(StatusEvent)
        .where(
            StatusEvent.application_id == application_id,
            StatusEvent.user_id == user_id,
        )
        .order_by(StatusEvent.created_at.asc())
    )
    return list(db.execute(stmt).scalars().all())
