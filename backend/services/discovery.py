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
from schemas.resume import Resume
from services.application import create_application
from services.resume import get_master
from services.eligibility import assess, graduation_years
from services.feed import FEED_SOURCE, pull
from services.fetch_posting import PostingFetchError, fetch_posting
from services.parsing import classify_role_families, parse_job_description
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


def run_pull(
    db: Session,
    user_id: str,
    settings: Settings,
    enrich_limit: int = 50,
    **filters: object,
) -> PullResult:
    """Fetch the feed, stage what survives, then read what was staged.

    The entry point behind both triggers: the refresh button and the nightly
    webhook call the same function, so the two can never drift into behaving
    differently.

    Reading happens HERE rather than when you accept a job, which is the whole
    point of doing it overnight — by morning the inbox already knows which
    postings want the Class of 2026, and you never open one to find out. It is
    capped so that a first run finishes rather than timing out; the remainder is
    picked up by the next pass.
    """
    listings, result = pull(**filters)
    result = stage_listings(db, user_id, listings, settings, result)
    result.enriched = enrich_pending(db, user_id, settings, limit=enrich_limit)
    result.ruled_out = filtered_by_graduation(db, user_id)
    return result


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
            # Carried across so accepting does not throw away what was already
            # paid for: the classifier's verdict, and the posting itself. The
            # text is what resume tailoring reads, so a row that arrived without
            # it would look complete and quietly refuse to tailor.
            role_family=job.role_family,
            jd_text=job.jd_text,
            jd_parsed=job.jd_parsed,
        ),
        user_id,
    )
    resolve(db, job, DiscoveryState.accepted, application.id)
    return application


def dismiss(db: Session, job: DiscoveredJob) -> DiscoveredJob:
    """Turn a discovery down. The row stays so the feed cannot re-offer it."""
    return resolve(db, job, DiscoveryState.dismissed)


# --- Enrichment --------------------------------------------------------------
# Reading each newly staged posting so the inbox can answer "am I even eligible"
# before you open anything. Separate from staging because it is the slow half:
# staging is one feed download and one batched classifier call, while this is a
# network round trip per posting.


def _your_graduation_years(db: Session, user_id: str) -> list[int]:
    """Graduation years from the master resume, or empty if there is none.

    Empty is not a failure. eligibility.assess returns "unclear" with nothing to
    compare against, which is the honest answer for a user who has not filled in
    their education yet.
    """
    master = get_master(db, user_id)
    if master is None or not master.resume_json:
        return []
    return graduation_years(Resume.model_validate(master.resume_json))


def enrich(db: Session, job: DiscoveredJob, settings: Settings, years: list[int]) -> None:
    """Read one posting and record what it says. Never raises.

    A failure here must not cost you the row. Roughly four in ten ordinary
    careers sites cannot be read without a browser, and a discovery you can
    still click through to is worth far more than a pull that aborted. So every
    failure path leaves the row exactly as it was and moves on — the fields stay
    null, which the UI reads as "not read yet" rather than as a verdict.

    enriched_at is stamped only on success, so a failed posting is retried by a
    later pass rather than being permanently marked as done.
    """
    try:
        fetched = fetch_posting(job.posting_url)
    except PostingFetchError:
        # Expected and common: a blocked site, a page that needs a browser, a
        # link that has already gone dead. Not worth a log line each.
        return
    except Exception:
        # Anything else is a surprise rather than a known limitation, and it
        # still must not take the pull down with it.
        return

    parsed = parse_job_description(fetched.text, settings)

    job.jd_text = fetched.text
    job.jd_parsed = parsed.model_dump(mode="json") if parsed is not None else None
    requirements = (
        [*parsed.key_requirements, *parsed.preferred_qualifications]
        if parsed is not None
        else []
    )
    verdict = assess(fetched.text, requirements, years)
    job.eligibility = verdict.model_dump()
    job.enriched_at = datetime.now(UTC)

    # A posting whose graduation window closes before you can finish is not a
    # judgement call. It is a new-grad role or a cycle already gone, and there
    # is nothing to decide, so it leaves the inbox rather than sitting there as
    # a row you can only dismiss.
    #
    # Filtered rather than deleted, like every other rejection here: the record
    # is what stops tomorrow's pull staging it again, and what lets you see why
    # it went if you ever go looking.
    if verdict.verdict == "too_early":
        job.state = DiscoveryState.filtered


def enrich_pending(db: Session, user_id: str, settings: Settings, limit: int = 50) -> int:
    """Read the postings staged for this user that have not been read yet.

    Capped, and the cap is the point. A first run against an empty table stages
    a few hundred jobs, and reading all of them in one request would take many
    minutes and time out whatever called it. Later passes pick up the rest,
    newest first, because that is the end of the list you would actually work
    through.
    """
    rows = db.execute(
        select(DiscoveredJob)
        .where(
            DiscoveredJob.user_id == user_id,
            DiscoveredJob.state == DiscoveryState.pending,
            DiscoveredJob.enriched_at.is_(None),
        )
        .order_by(DiscoveredJob.posted_at.desc().nullslast())
        .limit(limit)
    ).scalars().all()
    if not rows:
        return 0

    years = _your_graduation_years(db, user_id)
    for job in rows:
        enrich(db, job, settings, years)
    db.commit()
    return sum(1 for job in rows if job.enriched_at is not None)


def filtered_by_graduation(db: Session, user_id: str) -> int:
    """How many discoveries reading ruled out on graduation timing.

    Not decoration. This is the number that says whether the eligibility check
    is doing real work or quietly eating your inbox — if it climbs while the
    inbox empties, the check has gone wrong, and nothing else would tell you.
    """
    return len(
        db.execute(
            select(DiscoveredJob.id).where(
                DiscoveredJob.user_id == user_id,
                DiscoveredJob.state == DiscoveryState.filtered,
                DiscoveredJob.enriched_at.is_not(None),
            )
        ).scalars().all()
    )
