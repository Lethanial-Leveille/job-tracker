"""Staging: turn filtered feed listings into rows worth your attention.

services/feed.py answers the free questions — is this posting open, for the
right year, open to an undergraduate, recent. This module answers the two that
cost something, and the ORDER it answers them in is the whole design:

    1. Have I already seen this?   (free, and it eliminates the most)
    2. Is it the kind of job I want?  (a paid classifier call)

Backwards, that is a bill for classifying the same three hundred postings every
single night. This way the paid call only ever runs on postings that are new,
which after the first run is whatever landed overnight — a dozen or two.

Nothing here decides anything on your behalf. Everything that survives is staged
for you to accept or dismiss, exactly like a status suggestion.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings
from models.application import Application, ApplicationStatus, ApplicationType
from models.discovered_job import DiscoveredJob, DiscoveryState
from schemas.application import ApplicationCreate
from schemas.discovery import FeedListing, PullResult
from services.application import create_application
from services.feed import FEED_SOURCE, pull
from services.parsing import classify_role_families
from services.text_match import (
    normalize_organization,
    normalize_url,
    role_similarity,
)

# The families worth staging. This is the real "is it for me" filter — the feed's
# own category could not make this call, filing "Flight Software Intern" and
# "Hardware Design Verification Engineer" under one label.
#
# Absent on purpose: "AI and ML Engineer Intern" (those roles go to upperclassmen
# and grad students with the coursework to back them), "Hardware Engineer Intern"
# (RTL and circuit work, which needs Digital Logic), "Data Engineer Intern",
# "Frontend Engineer Intern", and "Other". Adding one back is one line here.
DEFAULT_WANTED_FAMILIES = frozenset(
    {
        "Software Engineer Intern",
        "Embedded Engineer Intern",
        "Backend Engineer Intern",
    }
)

# How alike two titles must be, at the same employer, to count as possibly the
# same posting. The same 0.7 the add flow's duplicate warning uses, deliberately
# — the browser and the backend must agree about what a duplicate is, or the
# same job is a repeat on one screen and a discovery on the other.
_SIMILAR_ENOUGH = 0.7

# Titles per classifier call. Sized well under what the reply budget can hold,
# because the failure mode when it does not fit is a truncated answer rather
# than an error, and a chunk that fits comfortably is worth more than a chunk
# that fits exactly.
_CLASSIFY_BATCH = 60


def _existing_applications(db: Session, user_id: str) -> list[Application]:
    return list(
        db.execute(select(Application).where(Application.user_id == user_id))
        .scalars()
        .all()
    )


def _match(
    listing: FeedListing, applications: list[Application]
) -> tuple[bool, list[str]]:
    """Decide what this listing already is, if anything.

    Returns (is_certain_duplicate, possible_application_ids), which are the
    three outcomes the inbox needs:

        (True, ...)   the same link you already track. Dropped; never shown.
        (False, [id]) same employer, near-identical title, DIFFERENT link.
                      Staged, carrying what it resembles, so you are told
                      rather than guessed at.
        (False, [])   new. Staged plainly.

    The middle case is the one that earns its complexity. Companies repost the
    same job to several boards under slightly different titles, and reapplying
    to a role in a new cycle is a real thing you do — so "looks similar" cannot
    mean "hide it" and cannot mean "say nothing" either.

    Both comparisons run through services/text_match.py, whose functions are
    deliberate twins of the frontend's dedupe.ts. That matters here: this is the
    server making the same judgement the add screen makes in the browser, and if
    the two drift, a job is a duplicate in one place and new in the other.
    """
    key = normalize_url(listing.url)
    if key is not None:
        for application in applications:
            if normalize_url(application.posting_url) == key:
                return True, []

    org_key = normalize_organization(listing.company_name)
    if not org_key:
        return False, []

    possible = [
        application.id
        for application in applications
        if normalize_organization(application.organization) == org_key
        and role_similarity(application.role_or_program, listing.title)
        >= _SIMILAR_ENOUGH
    ]
    return False, possible


def _already_staged_keys(db: Session, user_id: str) -> set[str]:
    """The feed ids already sitting in this user's inbox, resolved or not.

    Every state counts, including `filtered`. That is the point of keeping them:
    a job you turned down last week must not come back tomorrow just because the
    feed still publishes it, and a job the classifier already rejected must not
    be paid for again every night.
    """
    rows = db.execute(
        select(DiscoveredJob.external_id).where(
            DiscoveredJob.user_id == user_id,
            DiscoveredJob.source == FEED_SOURCE,
        )
    ).scalars()
    return set(rows)


def stage_listings(
    db: Session,
    user_id: str,
    listings: list[FeedListing],
    settings: Settings,
    result: PullResult,
    wanted_families: frozenset[str] = DEFAULT_WANTED_FAMILIES,
) -> PullResult:
    """Dedupe, classify, and write the survivors. Returns the filled-in result.

    Takes an existing PullResult rather than making one because feed.pull()
    already counted what it fetched and dropped; this fills in the rest of the
    same story.
    """
    seen = _already_staged_keys(db, user_id)
    applications = _existing_applications(db, user_id)

    # --- 1. Dedupe, free ----------------------------------------------------
    candidates: list[tuple[FeedListing, list[str]]] = []
    for listing in listings:
        if listing.id in seen:
            # Already in the inbox from a previous run. Not a duplicate of an
            # application — a duplicate of ourselves — so it is counted
            # separately from the ones you are actually tracking.
            result.duplicates += 1
            continue
        certain, possible = _match(listing, applications)
        if certain:
            result.duplicates += 1
            continue
        candidates.append((listing, possible))

    if not candidates:
        return result

    # --- 2. Classify, paid --------------------------------------------------
    # Chunked, because the first run against an empty table is hundreds of
    # titles at once and one reply cannot hold that many answers. Discovered by
    # running it: 150 titles overflowed the budget and the reply came back cut
    # off mid-string. Chunking is the caller's job rather than the classifier's
    # because only the caller knows how big its list is.
    #
    # Indices are local to each chunk, so they are shifted back to positions in
    # `candidates` as they come in.
    titles = [listing.title for listing, _ in candidates]
    families: dict[int, str] = {}
    # Indices whose whole chunk failed. Tracked separately from indices the
    # classifier simply skipped, because the two are different problems and
    # collapsing them would report a dead API as a batch of odd job titles.
    unavailable: set[int] = set()
    for start in range(0, len(titles), _CLASSIFY_BATCH):
        chunk = titles[start : start + _CLASSIFY_BATCH]
        answered = classify_role_families(chunk, settings)
        if answered is None:
            # One dead chunk does not condemn the others. Its listings go
            # unstaged and unwritten, so the next run retries exactly them.
            unavailable.update(range(start, start + len(chunk)))
            result.dropped["classifier unavailable"] = (
                result.dropped.get("classifier unavailable", 0) + len(chunk)
            )
            continue
        for index, family in answered.items():
            families[start + index] = family

    # --- 3. Write -----------------------------------------------------------
    for index, (listing, possible) in enumerate(candidates):
        if index in unavailable:
            # Already counted as unavailable above. Counting it again as
            # unclassified would double-report one listing under two reasons and
            # break the tally as a breakdown.
            continue
        family = families.get(index)
        if family is None:
            # Unclassified after every round. Left alone rather than guessed at,
            # the same call classify_role_families makes for the backfill.
            result.dropped["unclassified"] = result.dropped.get("unclassified", 0) + 1
        elif family not in wanted_families:
            result.dropped[f"family:{family}"] = (
                result.dropped.get(f"family:{family}", 0) + 1
            )

        state = (
            DiscoveryState.pending
            if family in wanted_families
            else DiscoveryState.filtered
        )

        db.add(
            DiscoveredJob(
                state=state,
                user_id=user_id,
                source=FEED_SOURCE,
                external_id=listing.id,
                organization=listing.company_name,
                role_or_program=listing.title,
                posting_url=listing.url,
                # The feed gives a list; the column holds one line. Joined rather
                # than truncated to the first, because "Seattle, WA or Austin, TX"
                # is a fact worth having when you decide whether to apply.
                location=", ".join(listing.locations) or None,
                posted_at=listing.posted_on(),
                role_family=family,
                possible_application_ids=possible or None,
                raw=listing.model_dump(),
            )
        )
        if state is DiscoveryState.pending:
            result.staged += 1

    db.commit()
    return result


def run_pull(db: Session, user_id: str, settings: Settings, **filters: object) -> PullResult:
    """Fetch the feed and stage what survives, for one user.

    The entry point behind both triggers: the refresh button and the nightly
    webhook call the same function, so the two can never drift into behaving
    differently.
    """
    listings, result = pull(**filters)
    return stage_listings(db, user_id, listings, settings, result)


def resolve(
    db: Session, job: DiscoveredJob, state: DiscoveryState, application_id: str | None = None
) -> DiscoveredJob:
    """Mark a discovery accepted or dismissed. The row is kept either way.

    Deleting it would break the unique constraint's whole purpose — tomorrow's
    pull would see the feed still publishing this job, find no record of it, and
    hand it back to you as new.
    """
    job.state = state
    job.application_id = application_id
    job.resolved_at = datetime.now(UTC)
    db.commit()
    db.refresh(job)
    return job


# --- Reading and resolving ---------------------------------------------------


def list_pending(db: Session, user_id: str) -> list[DiscoveredJob]:
    """This user's undecided discoveries, newest posting first.

    Ordered by when the EMPLOYER posted, not by when we found it. A pull hands
    you a batch all at once, so the discovery date says nothing useful, while
    the posted date is the thing that decides what deserves attention first.
    Rows with no posted date sort last rather than first — an unknown date is
    not evidence of freshness.
    """
    rows = db.execute(
        select(DiscoveredJob)
        .where(
            DiscoveredJob.user_id == user_id,
            DiscoveredJob.state == DiscoveryState.pending,
        )
        .order_by(DiscoveredJob.posted_at.desc().nullslast(), DiscoveredJob.created_at.desc())
    ).scalars()
    return list(rows)


def get_discovered(db: Session, job_id: str, user_id: str) -> DiscoveredJob | None:
    """One discovery, scoped by owner.

    Another user's row comes back as None so the route 404s — the same rule
    services/application.py follows. We never reveal that someone else's row
    exists.
    """
    return db.execute(
        select(DiscoveredJob).where(
            DiscoveredJob.id == job_id, DiscoveredJob.user_id == user_id
        )
    ).scalar_one_or_none()


def accept(db: Session, job: DiscoveredJob, user_id: str) -> Application:
    """Turn a discovery into a real application.

    Everything comes from the row itself, so this spends no network call and
    cannot fail partway. The posting was already read during staging; accepting
    is a filing decision, not a fetch.

    Status is `discovered` rather than anything further along. Accepting means
    "this is worth pursuing", not "I have applied" — the pipeline still starts
    at the beginning, and it goes through create_application so the status
    history records its opening entry like every other row.
    """
    application = create_application(
        db,
        ApplicationCreate(
            type=ApplicationType.internship,
            organization=job.organization,
            role_or_program=job.role_or_program,
            posting_url=job.posting_url,
            status=ApplicationStatus.discovered,
            # Carried across so accepting does not throw away what the
            # classifier already paid to work out.
            role_family=job.role_family,
        ),
        user_id,
    )
    resolve(db, job, DiscoveryState.accepted, application.id)
    return application


def dismiss(db: Session, job: DiscoveredJob) -> DiscoveredJob:
    """Turn a discovery down. The row stays so the feed cannot re-offer it."""
    return resolve(db, job, DiscoveryState.dismissed)
