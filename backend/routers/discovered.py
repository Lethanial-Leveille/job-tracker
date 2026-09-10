"""Discovery inbox routes: the logged-in user's side of the feed.

The nightly pull stages jobs as a machine (routers/webhooks.py); these routes
let the person read them and decide. Guarded by get_current_user like the rest
of the human-facing API — the opposite auth path from the webhook, and the same
split the Gmail pipeline already uses.

Nothing here decides anything on your behalf. Accept files a job into the
pipeline, dismiss turns it down, and both keep the row so tomorrow's pull cannot
hand you the same posting again.
"""

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import Settings, get_settings
from database import get_db
from dependencies import get_current_user
from models.user import User
from schemas.application import ApplicationRead
from schemas.discovery import DiscoveredJobRead, DiscoveryRunRead
from services.discovery import (
    RunAlreadyGoing,
    accept,
    dismiss,
    execute_run,
    get_discovered,
    latest_run,
    list_pending,
    start_run,
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


@router.post(
    "/refresh", response_model=DiscoveryRunRead, status_code=status.HTTP_202_ACCEPTED
)
def refresh(
    background: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> DiscoveryRunRead:
    """Start a pull and answer immediately with the run that was started.

    202, not 200, and the reason is the network rather than the code: the site
    is behind Cloudflare, which abandons any request the origin has not answered
    in 100 seconds and returns a 524. A first pull downloads a 12MB feed,
    classifies hundreds of titles, and then reads up to fifty postings one at a
    time — comfortably past that. Doing the work inside the request would show
    you a failure for a run that succeeded.

    So this claims the run, hands the work to a background task, and returns the
    row. The page polls /discovered/runs/latest to watch it finish.

    409 when one is already going. Two concurrent pulls would fetch the same
    feed twice and race each other into the same unique constraint, and a
    nightly job that fires twice ought to say so rather than be quietly queued.
    """
    try:
        run = start_run(db, user.id)
    except RunAlreadyGoing as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pull is already running.",
        ) from exc
    background.add_task(execute_run, run.id, user.id, settings)
    return DiscoveryRunRead.model_validate(run)


@router.get("/runs/latest", response_model=DiscoveryRunRead | None)
def read_latest_run(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> DiscoveryRunRead | None:
    """The most recent pull, running or finished.

    What makes a background run legible. Without it, an inbox that did not
    change could mean the feed was quiet, the run is still going, or the run
    died — and all three look identical.
    """
    run = latest_run(db, user.id)
    return DiscoveryRunRead.model_validate(run) if run else None


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
