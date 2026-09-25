"""The surface MILES calls.

A third router with a third auth path, kept apart from the other two for the
same reason webhooks.py is kept apart from everything else: mixing auth paths
in one module is how a route ends up on the wrong one.

  routers/*.py      a logged in person, JWT on Authorization
  routers/webhooks  n8n, shared secret on X-Service-Token, writes only
  this module       MILES, its own secret on X-Miles-Token

Two rules shape every handler here.

ARITHMETIC HAPPENS IN PYTHON. Every count, every day difference, every filter
runs here and the model receives the answer. Handing a language model a list of
rows and asking it to count them produces a confident wrong number, and this
one speaks its answers out loud where a wrong number sounds exactly as certain
as a right one.

NOTHING REACHES THE OUTSIDE WORLD. Four of these five routes read. The fifth
files a discovered job into the pipeline at status `discovered`, which spends
no network call and submits nothing. That is the hard rule: Prowl proposes and
you submit, and putting a microphone in front of it does not change that.
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database import get_db
from dependencies import get_miles_owner, verify_miles_token
from models.application import Application, ApplicationStatus
from models.status_event import StatusEvent
from models.user import User
from schemas.integrations import (
    MilesApplication,
    MilesApplicationDetail,
    MilesDiscovered,
    MilesSuggestion,
    MilesSummary,
)
from services.application import get_application, list_applications
from services.discovery import accept, get_discovered, list_pending
from services.status_suggestion import list_pending_suggestions

# Guarded at router level so a route added here later is protected whether or
# not anyone remembers to protect it. Same fail-safe shape as webhooks.py.
router = APIRouter(
    prefix="/integrations/miles",
    tags=["integrations"],
    dependencies=[Depends(verify_miles_token)],
)

# Statuses where the row is finished and nothing is pending on you. Everything
# else counts as active. Kept here rather than on the model because it is a
# reporting judgment, not a fact about the enum: `declined` means you turned an
# offer down, which is an outcome worth counting separately from `rejected`,
# and both are equally over.
CLOSED_STATUSES = frozenset(
    {
        ApplicationStatus.rejected,
        ApplicationStatus.ghosted,
        ApplicationStatus.declined,
        ApplicationStatus.accepted,
        ApplicationStatus.missed_deadline,
    }
)

# How long a row sits untouched before it is worth mentioning unprompted. Two
# weeks is roughly when silence stops being normal for an internship pipeline.
STALE_AFTER_DAYS = 14


def _days_since(moment: datetime | None) -> int | None:
    """Whole days from `moment` until now, or None.

    Timestamps are stored in naive DateTime columns while the defaults that
    write them are timezone aware UTC, so what comes back out has no tzinfo.
    Subtracting an aware datetime from a naive one raises, so anything naive is
    read as the UTC it actually is.
    """
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (datetime.now(UTC) - moment).days


def _days_until(day: date | None) -> int | None:
    """Whole days until `day`. Negative once it has passed."""
    return None if day is None else (day - date.today()).days


def _applied_at(db: Session, user_id: str, ids: list[str]) -> dict[str, datetime]:
    """When each application FIRST reached `applied`.

    First rather than most recent: a row can pass through `applied` more than
    once if a status is corrected, and "how long since I applied" means the
    original date, not the correction.
    """
    if not ids:
        return {}
    stmt = (
        select(StatusEvent.application_id, func.min(StatusEvent.created_at))
        .where(
            StatusEvent.user_id == user_id,
            StatusEvent.to_status == ApplicationStatus.applied,
            StatusEvent.application_id.in_(ids),
        )
        .group_by(StatusEvent.application_id)
    )
    return {row[0]: row[1] for row in db.execute(stmt).all()}


def _last_change(db: Session, user_id: str, ids: list[str]) -> dict[str, datetime]:
    """When each application last moved, whatever it moved to."""
    if not ids:
        return {}
    stmt = (
        select(StatusEvent.application_id, func.max(StatusEvent.created_at))
        .where(
            StatusEvent.user_id == user_id,
            StatusEvent.application_id.in_(ids),
        )
        .group_by(StatusEvent.application_id)
    )
    return {row[0]: row[1] for row in db.execute(stmt).all()}


def _row(
    application: Application,
    applied: datetime | None,
    moved: datetime | None,
) -> MilesApplication:
    """One Application turned into the narrow spoken shape."""
    return MilesApplication(
        id=application.id,
        organization=application.organization,
        role=application.role_or_program,
        status=application.status,
        priority=application.priority,
        posting_url=application.posting_url,
        role_family=application.role_family,
        deadline=application.deadline,
        days_until_deadline=_days_until(application.deadline),
        applied_at=applied,
        days_since_applied=_days_since(applied),
        # Falls back to created_at so a row that has never moved still reports
        # how long it has been sitting. Without the fallback the rows most
        # worth chasing would be the ones reporting nothing.
        days_since_last_change=_days_since(moved or application.created_at),
    )


def _rows(db: Session, user_id: str, applications: list[Application]) -> list[MilesApplication]:
    """Build the spoken shape for a list of applications in two queries total.

    The obvious version asks for each row's events inside the loop, which is one
    query per application. At twenty rows nobody notices and at two hundred the
    voice turn times out, so both lookups are batched up front.
    """
    ids = [a.id for a in applications]
    applied = _applied_at(db, user_id, ids)
    moved = _last_change(db, user_id, ids)
    return [_row(a, applied.get(a.id), moved.get(a.id)) for a in applications]


@router.get("/applications", response_model=list[MilesApplication])
def miles_applications(
    db: Session = Depends(get_db),
    owner: User = Depends(get_miles_owner),
    status_filter: ApplicationStatus | None = Query(default=None, alias="status"),
    include_closed: bool = Query(default=False),
) -> list[MilesApplication]:
    """The pipeline, narrowed before it reaches the model.

    Closed rows are excluded by default. "How many applications do I have out"
    means live ones, and a search that has been running a while is mostly
    rejections, which would otherwise dominate everything MILES says.

    The filter is applied here rather than left to the model for the reason in
    the module docstring: filtering in code is exact, and filtering by reading
    is a guess that sounds like a fact.
    """
    rows = list_applications(db, owner.id)
    if status_filter is not None:
        rows = [a for a in rows if a.status == status_filter]
    elif not include_closed:
        rows = [a for a in rows if a.status not in CLOSED_STATUSES]
    return _rows(db, owner.id, rows)


@router.get("/applications/{application_id}", response_model=MilesApplicationDetail)
def miles_application(
    application_id: str,
    db: Session = Depends(get_db),
    owner: User = Depends(get_miles_owner),
) -> MilesApplicationDetail:
    """One application, opened up, still without the posting text.

    `jd_parsed` is a stored blob that has changed shape over the life of this
    app, so every read of it here is a .get() with a fallback rather than an
    attribute access. A row parsed by an older version must degrade to a
    thinner answer, never to a 500 that makes the whole integration look down.
    """
    application = get_application(db, application_id, owner.id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Application not found"
        )

    base = _rows(db, owner.id, [application])[0]
    parsed = application.jd_parsed or {}
    report = application.fit_report or {}

    return MilesApplicationDetail(
        **base.model_dump(),
        location=parsed.get("location"),
        salary=parsed.get("salary"),
        summary=parsed.get("summary"),
        key_requirements=parsed.get("key_requirements") or [],
        notes=application.notes,
        requirements_met=report.get("met_count"),
        requirements_partial=report.get("partial_count"),
        requirements_total=report.get("total"),
    )


@router.get("/discovered", response_model=list[MilesDiscovered])
def miles_discovered(
    db: Session = Depends(get_db),
    owner: User = Depends(get_miles_owner),
) -> list[MilesDiscovered]:
    """What is waiting in the discovery inbox, best fit first.

    Rows with no fit score sort last rather than as zero: unscored means the
    posting could not be read, which is not the same as a bad match, and
    sorting them as zeroes would bury readable-but-mediocre jobs beneath them.
    """
    jobs = list_pending(db, owner.id)
    jobs.sort(key=lambda j: (j.fit_score is None, -(j.fit_score or 0)))
    return [
        MilesDiscovered(
            id=j.id,
            organization=j.organization,
            role=j.role_or_program,
            posting_url=j.posting_url,
            source=j.source,
            location=j.location,
            posted_at=j.posted_at,
            role_family=j.role_family,
            fit_score=j.fit_score,
            possible_duplicate_of=j.possible_application_ids or [],
        )
        for j in jobs
    ]


@router.post("/discovered/{job_id}/accept", response_model=MilesApplication)
def miles_accept_discovered(
    job_id: str,
    db: Session = Depends(get_db),
    owner: User = Depends(get_miles_owner),
) -> MilesApplication:
    """File a discovered job into the pipeline. The one write MILES can do.

    What this is NOT: applying. The row lands at status `discovered`, the same
    place it would if you had clicked accept in the browser. Nothing is sent,
    nothing is submitted, and the next steps still happen at a keyboard.

    What it IS: irreversible enough to care about. This route is driven by
    speech, and speech gets misheard. A wrong accept files a row you then have
    to find and delete, which is annoying rather than dangerous, but it is the
    reason the id has to be explicit. There is deliberately no "accept the best
    one" or "accept them all" here: the caller names exactly one job, and the
    confirming is MILES's job before it ever gets this far.

    Unlike the browser's version this takes no body. That route accepts pasted
    posting text for discoveries that could not be read, which is a job for a
    screen, not a sentence.
    """
    job = get_discovered(db, job_id, owner.id)
    if job is None:
        # A job belonging to someone else is indistinguishable from one that
        # does not exist, because get_discovered is owner scoped.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Discovery not found"
        )

    application = accept(db, job, owner.id)
    return _rows(db, owner.id, [application])[0]


@router.get("/summary", response_model=MilesSummary)
def miles_summary(
    db: Session = Depends(get_db),
    owner: User = Depends(get_miles_owner),
    deadline_days: int = Query(default=7, ge=1, le=90),
) -> MilesSummary:
    """The whole search in one call, shaped for the morning brief.

    This is the route worth having. The others answer questions you thought to
    ask; this one carries the things you did not: a deadline four days out, a
    suggestion that has been waiting since Tuesday, a row nobody has touched in
    three weeks.

    Everything is already filtered, already sorted, and already counted. The
    lists are capped because this is spoken: five deadlines is a sentence and
    forty is a filibuster.
    """
    applications = list_applications(db, owner.id)
    live = [a for a in applications if a.status not in CLOSED_STATUSES]
    rows = _rows(db, owner.id, live)

    counts: dict[str, int] = {}
    for a in applications:
        key = a.status.value
        counts[key] = counts.get(key, 0) + 1

    # Deadlines still ahead and inside the window. Sorted soonest first, which
    # is the order you would say them in.
    deadlines = sorted(
        (
            r
            for r in rows
            if r.days_until_deadline is not None
            and 0 <= r.days_until_deadline <= deadline_days
        ),
        key=lambda r: r.days_until_deadline or 0,
    )

    # Deadlines that passed while the row never reached `applied`. This is the
    # gap the window filter above leaves: a deadline four days out gets said,
    # and one that passed last week vanishes, which is backwards for the only
    # case that matters. Sorted most recently missed first, because a deadline
    # that slipped two days ago may still be worth a late application and one
    # that slipped two months ago is history.
    overdue = sorted(
        (
            r
            for r in rows
            if r.days_until_deadline is not None
            and r.days_until_deadline < 0
            and r.days_since_applied is None
        ),
        key=lambda r: r.days_until_deadline or 0,
        reverse=True,
    )

    # Quiet rows, longest silence first. Restricted to rows you have actually
    # applied to: something sitting at `discovered` is not being ignored by an
    # employer, it is waiting on you, and that is a different sentence.
    stale = sorted(
        (
            r
            for r in rows
            if r.days_since_applied is not None
            and (r.days_since_last_change or 0) >= STALE_AFTER_DAYS
        ),
        key=lambda r: r.days_since_last_change or 0,
        reverse=True,
    )

    organizations = {a.id: a.organization for a in applications}
    suggestions = [
        MilesSuggestion(
            id=s.id,
            suggested_status=s.suggested_status,
            reason=s.reason,
            state=s.state,
            created_at=s.created_at,
            days_waiting=_days_since(s.created_at) or 0,
            application_id=s.application_id,
            organization=organizations.get(s.application_id) if s.application_id else None,
            # No single application behind it means it matched nothing, or
            # matched several. Either way it needs a screen, and saying it out
            # loud as though it were actionable would be a lie.
            needs_a_screen=s.application_id is None,
        )
        for s, _email in list_pending_suggestions(db, owner.id)
    ]

    return MilesSummary(
        active_count=len(live),
        counts_by_status=counts,
        upcoming_deadlines=deadlines[:5],
        overdue=overdue[:5],
        stale=stale[:5],
        pending_suggestions=suggestions[:5],
        discovered_waiting=len(list_pending(db, owner.id)),
    )
