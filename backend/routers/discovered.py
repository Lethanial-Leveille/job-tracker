"""Discovery inbox routes: the logged-in user's side of the feed.

The nightly pull stages jobs as a machine (routers/webhooks.py); these routes
let the person read them and decide. Guarded by get_current_user like the rest
of the human-facing API — the opposite auth path from the webhook, and the same
split the Gmail pipeline already uses.

Nothing here decides anything on your behalf. Accept files a job into the
pipeline, dismiss turns it down, and both keep the row so tomorrow's pull cannot
hand you the same posting again.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.application import ApplicationRead
from schemas.discovery import DiscoveredJobRead, PullResult
from services.discovery import (
    accept,
    dismiss,
    get_discovered,
    list_pending,
    run_pull,
)

router = APIRouter(
    prefix="/discovered",
    tags=["discovered"],
    dependencies=[Depends(get_current_user)],
)


@router.get("", response_model=list[DiscoveredJobRead])
def list_discovered(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[DiscoveredJobRead]:
    """The undecided inbox, newest posting first."""
    return [DiscoveredJobRead.model_validate(job) for job in list_pending(db, user.id)]


@router.post("/refresh", response_model=PullResult)
def refresh(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> PullResult:
    """Run the pull now, rather than waiting for tonight.

    The same run_pull the webhook calls, so the button and the schedule can
    never drift into behaving differently. It is safe to press repeatedly: the
    unique constraint on the feed's own id means a second run stages only what
    is genuinely new.

    Deliberately synchronous, and it can take a while on a first run. A
    background job would return instantly and leave you watching an inbox that
    might fill in or might have failed, with no way to tell which. The count
    that comes back is the answer.
    """
    return run_pull(db, user.id, settings)


@router.post("/{job_id}/accept", response_model=ApplicationRead)
def accept_discovered(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ApplicationRead:
    """File a discovery into the pipeline as a real application.

    Answers with the created application rather than the discovery, because that
    is the row you now care about and the one the UI navigates to.
    """
    job = _owned(db, job_id, user)
    return accept(db, job, user.id)


@router.post("/{job_id}/dismiss", response_model=DiscoveredJobRead)
def dismiss_discovered(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiscoveredJobRead:
    job = _owned(db, job_id, user)
    return DiscoveredJobRead.model_validate(dismiss(db, job))


def _owned(db: Session, job_id: str, user: User):
    """Fetch a discovery or 404.

    A row belonging to someone else is indistinguishable from one that does not
    exist — get_discovered is owner-scoped, so this never reveals that another
    user's discovery is there.
    """
    job = get_discovered(db, job_id, user.id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Discovery not found"
        )
    return job
