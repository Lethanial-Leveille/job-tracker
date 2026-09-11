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

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import Settings
from database import SessionLocal
from models.application import Application, ApplicationStatus, ApplicationType
from models.discovered_job import DiscoveredJob, DiscoveryState
from models.discovery_run import DiscoveryRun, RunState
from models.target_company import TargetCompany
from schemas.application import ApplicationCreate
from schemas.discovery import FeedListing, PullResult, StageCandidate
from schemas.resume import Resume
from services.application import create_application
from services.resume import get_master
from services.eligibility import assess, graduation_dates
from services.boards import read_board
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
    candidate: "StageCandidate", applications: list[Application]
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
    key = normalize_url(candidate.posting_url)
    if key is not None:
        for application in applications:
            if normalize_url(application.posting_url) == key:
                return True, []

    org_key = normalize_organization(candidate.organization)
    if not org_key:
        return False, []

    possible = [
        application.id
        for application in applications
        if normalize_organization(application.organization) == org_key
        and role_similarity(application.role_or_program, candidate.role_or_program)
        >= _SIMILAR_ENOUGH
    ]
    return False, possible


def _already_staged_keys(db: Session, user_id: str) -> set[tuple[str, str]]:
    """The feed ids already sitting in this user's inbox, resolved or not.

    Every state counts, including `filtered`. That is the point of keeping them:
    a job you turned down last week must not come back tomorrow just because the
    feed still publishes it, and a job the classifier already rejected must not
    be paid for again every night.
    """
    rows = db.execute(
        select(DiscoveredJob.source, DiscoveredJob.external_id).where(
            DiscoveredJob.user_id == user_id
        )
    ).all()
    # Keyed by SOURCE and id together, not id alone. Two systems number their
    # jobs independently, and a bare id set would let one source's "12345" hide
    # another's.
    return {(source, external_id) for source, external_id in rows}


# Column widths, mirrored from models/discovered_job.py. Postgres enforces these
# and SQLite does not, which is a genuinely dangerous combination: every test
# and every local run passes, and prod raises.
_LIMITS = {"organization": 255, "role_or_program": 255, "location": 255, "external_id": 128}

# How many locations to name before summarising. A posting open in thirty one
# cities is real — Google's was — and naming all of them produced a 404
# character string that blew the column, aborted the whole transaction, and
# staged NOTHING from that pull. Three plus a count reads better anyway, and the
# full list is kept verbatim in `raw`.
_LOCATIONS_SHOWN = 3


def summarize_locations(locations: list[str]) -> str | None:
    """Name a few places and count the rest.

    Truncating the joined string would cut a city in half; this keeps every name
    it shows intact and is honest about what it left out.
    """
    if not locations:
        return None
    if len(locations) <= _LOCATIONS_SHOWN:
        return ", ".join(locations)
    shown = ", ".join(locations[:_LOCATIONS_SHOWN])
    return f"{shown} +{len(locations) - _LOCATIONS_SHOWN} more"


def _fit(candidate: StageCandidate) -> StageCandidate:
    """Trim any field that would not fit its column.

    A backstop rather than the fix — summarize_locations is the fix for the case
    that actually happened. This exists because the failure mode is so bad: the
    whole batch is written in one transaction, so a single oversized value on
    one row discards every row in the pull, and the only symptom is an inbox
    that stays empty.
    """
    for field, limit in _LIMITS.items():
        value = getattr(candidate, field)
        if isinstance(value, str) and len(value) > limit:
            setattr(candidate, field, value[:limit])
    return candidate


def _staged_urls(db: Session, user_id: str) -> set[str]:
    """Normalized links of every discovery this user already has, any source.

    This is what makes deduplication work ACROSS sources. The per-source id
    check cannot see that a job on Stripe's own board is the same job the
    aggregator lists, because the two sources number it differently — only the
    link says so.

    Ordering upstream does the rest: boards are polled before the feed, so when
    both carry a job, the one already staged is the direct board record, which
    is the fresher of the two.
    """
    rows = db.execute(
        select(DiscoveredJob.posting_url).where(DiscoveredJob.user_id == user_id)
    ).scalars()
    return {key for key in (normalize_url(url) for url in rows) if key}


def stage_candidates(
    db: Session,
    user_id: str,
    candidates: list[StageCandidate],
    settings: Settings,
    result: PullResult,
    wanted_families: frozenset[str] = DEFAULT_WANTED_FAMILIES,
) -> PullResult:
    """Dedupe, classify, and write. The one path both sources go through.

    Order matters and is the whole design: deduplication is free and eliminates
    the most, classification costs money per call. Backwards, this bills you to
    re-judge the same few hundred postings every night and nothing about the
    output would look wrong.
    """
    seen_ids = _already_staged_keys(db, user_id)
    seen_urls = _staged_urls(db, user_id)
    applications = _existing_applications(db, user_id)

    # --- 1. Dedupe, free ----------------------------------------------------
    fresh: list[tuple[StageCandidate, list[str]]] = []
    for candidate in candidates:
        if (candidate.source, candidate.external_id) in seen_ids:
            result.duplicates += 1
            continue
        key = normalize_url(candidate.posting_url)
        if key is not None and key in seen_urls:
            # Already staged from another source. Counted as a duplicate rather
            # than dropped silently, so a run that finds the same jobs twice is
            # visible in the numbers.
            result.duplicates += 1
            continue
        certain, possible = _match(candidate, applications)
        if certain:
            result.duplicates += 1
            continue
        if key is not None:
            # Guard against one batch carrying the same link twice, which a
            # board and its own paging can produce.
            seen_urls.add(key)
        fresh.append((_fit(candidate), possible))

    if not fresh:
        return result

    # --- 2. Classify, paid --------------------------------------------------
    titles = [candidate.role_or_program for candidate, _ in fresh]
    families: dict[int, str] = {}
    unavailable: set[int] = set()
    for start in range(0, len(titles), _CLASSIFY_BATCH):
        chunk = titles[start : start + _CLASSIFY_BATCH]
        answered = classify_role_families(chunk, settings)
        if answered is None:
            unavailable.update(range(start, start + len(chunk)))
            result.dropped["classifier unavailable"] = (
                result.dropped.get("classifier unavailable", 0) + len(chunk)
            )
            continue
        for index, family in answered.items():
            families[start + index] = family

    # --- 3. Write -----------------------------------------------------------
    for index, (candidate, possible) in enumerate(fresh):
        if index in unavailable:
            continue
        family = families.get(index)
        if family is None:
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
                source=candidate.source,
                target_company_id=candidate.target_company_id,
                external_id=candidate.external_id,
                organization=candidate.organization,
                role_or_program=candidate.role_or_program,
                posting_url=candidate.posting_url,
                location=candidate.location,
                posted_at=candidate.posted_at,
                role_family=family,
                possible_application_ids=possible or None,
                raw=candidate.raw,
            )
        )
        if state is DiscoveryState.pending:
            result.staged += 1

    db.commit()
    return result


def stage_listings(
    db: Session,
    user_id: str,
    listings: list[FeedListing],
    settings: Settings,
    result: PullResult,
    wanted_families: frozenset[str] = DEFAULT_WANTED_FAMILIES,
) -> PullResult:
    """Stage what survived the feed's free filters."""
    return stage_candidates(
        db,
        user_id,
        [
            StageCandidate(
                source=FEED_SOURCE,
                external_id=listing.id,
                organization=listing.company_name,
                role_or_program=listing.title,
                posting_url=listing.url,
                # A few names plus a count. Joining all of them is what broke
                # prod: a Google posting open in thirty one cities produced a
                # 404 character string, overflowed the column, aborted the
                # transaction and staged nothing from the entire pull.
                location=summarize_locations(listing.locations),
                posted_at=listing.posted_on(),
                raw=listing.model_dump(),
            )
            for listing in listings
        ],
        settings,
        result,
        wanted_families,
    )


# --- Direct company boards ---------------------------------------------------


def active_companies(db: Session, user_id: str) -> list[TargetCompany]:
    return list(
        db.execute(
            select(TargetCompany)
            .where(TargetCompany.user_id == user_id, TargetCompany.active.is_(True))
            .order_by(TargetCompany.name)
        ).scalars().all()
    )


def poll_companies(
    db: Session, user_id: str, settings: Settings, result: PullResult
) -> dict[str, int]:
    """Read every active company's board and stage what is new.

    Returns a per-company count of what was staged, for the run record.

    One company failing must never end the run, so each is wrapped
    individually. A failure is written to that company's row rather than only
    into a log: a board that has been quietly returning nothing for a fortnight
    is invisible otherwise — the run finishes, the inbox is thinner than it
    should be, and nothing says why.

    Companies are read one at a time, and services/boards.py spaces requests to
    the same vendor. These are other people's servers being polled nightly by a
    personal tool with no arrangement in place; a trickle is the right shape.
    """
    staged_by_company: dict[str, int] = {}

    for company in active_companies(db, user_id):
        before = result.staged
        try:
            postings = read_board(company.ats, company.host, company.board, company.site)
            if postings:
                stage_candidates(
                    db,
                    user_id,
                    [
                        StageCandidate(
                            source=company.ats,
                            external_id=posting.external_id,
                            # The company's OWN name, not anything scraped. A
                            # board does not reliably say who it belongs to, and
                            # the name you typed is the one you will recognise.
                            organization=company.name,
                            role_or_program=posting.title,
                            posting_url=posting.url,
                            location=posting.location,
                            posted_at=posting.posted_at,
                            target_company_id=company.id,
                            raw=posting.model_dump(mode="json"),
                        )
                        for posting in postings
                    ],
                    settings,
                    result,
                )
            company.last_error = None if postings else "Board returned no postings."
        except Exception as exc:  # noqa: BLE001 - see docstring
            company.last_error = f"{type(exc).__name__}: {exc}"[:1000]
        company.last_checked_at = datetime.now(UTC)
        staged_by_company[company.name] = result.staged - before

    db.commit()
    return staged_by_company


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
    result = PullResult()

    # Companies FIRST, deliberately. When a job appears on its employer's own
    # board and in the aggregator, whichever source runs first is the one that
    # gets staged — and the direct board record is the fresher of the two, with
    # a link that goes to the posting rather than through a list.
    result.by_company = poll_companies(db, user_id, settings, result)

    listings, feed_result = pull(**filters)
    result.fetched = feed_result.fetched
    result.kept = feed_result.kept
    for reason, count in feed_result.dropped.items():
        result.dropped[reason] = result.dropped.get(reason, 0) + count
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


def _your_graduation_dates(db: Session, user_id: str) -> list[tuple[int, int | None]]:
    """Graduation dates from the master resume, or empty if there is none.

    Months included, because the too-early rule turns on them: "Expected May
    2028" against a posting wanting January 2028 graduates is not a match, and a
    year-only comparison calls it one.

    Empty is not a failure. eligibility.assess returns "unclear" with nothing to
    compare against, which is the honest answer for a user who has not filled in
    their education yet.
    """
    master = get_master(db, user_id)
    if master is None or not master.resume_json:
        return []
    return graduation_dates(Resume.model_validate(master.resume_json))


def enrich(
    db: Session,
    job: DiscoveredJob,
    settings: Settings,
    your_dates: list[tuple[int, int | None]],
) -> None:
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
    verdict = assess(fetched.text, requirements, your_dates)
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

    your_dates = _your_graduation_dates(db, user_id)
    for job in rows:
        enrich(db, job, settings, your_dates)
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


# --- Runs --------------------------------------------------------------------
# The pull is asynchronous now, for a reason that has nothing to do with the
# code: the site sits behind Cloudflare, which gives up on any request the
# origin takes more than 100 seconds to answer and returns a 524. A first pull
# downloads a 12MB feed, classifies hundreds of titles, and then fetches and
# reads up to fifty postings one at a time. It will exceed that, and n8n would
# record a failure for a run that actually succeeded.
#
# So the request starts the work and answers immediately, and the work leaves a
# record behind. Everything below exists to make an invisible run legible.


class RunAlreadyGoing(Exception):
    """A pull is already in progress for this user.

    Two concurrent runs would fetch the same feed twice, classify the same
    titles twice, and race each other into the same unique constraint. The
    second caller is told to wait rather than being quietly queued, because a
    nightly job that fires twice should say so.
    """


def release_orphaned_runs(db: Session) -> int:
    """Mark every in-progress run as failed. Called once at startup.

    A pull runs as a background task inside the web process, so a restart kills
    it outright — and every deploy restarts the process. The run row is left
    saying "running" with nothing left to finish it, and because the button is
    disabled while a run appears to be in progress, the screen deadlocks: the
    spinner never stops and you cannot start another.

    Startup is the exact moment this is knowable. If the process is booting,
    nothing it was running is still running, so this needs no timeout and no
    guessing. The hour-old sweep in start_run stays as a backstop for the other
    case — a run that hangs without the process dying — which startup cannot see.

    Found the hard way: a deploy went out while a pull was in flight and left the
    page spinning.
    """
    orphans = db.execute(
        select(DiscoveryRun).where(DiscoveryRun.state == RunState.running)
    ).scalars().all()
    for run in orphans:
        run.state = RunState.failed
        run.finished_at = datetime.now(UTC)
        run.error = "Interrupted: the server restarted while this was running."
    if orphans:
        db.commit()
    return len(orphans)


def latest_run(db: Session, user_id: str) -> DiscoveryRun | None:
    return db.execute(
        select(DiscoveryRun)
        .where(DiscoveryRun.user_id == user_id)
        .order_by(DiscoveryRun.started_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def start_run(db: Session, user_id: str) -> DiscoveryRun:
    """Claim the right to run, or raise RunAlreadyGoing.

    The row is written BEFORE any work happens, which is what makes the claim
    mean anything: a second caller arriving a moment later sees a running row
    and is turned away.

    A stale `running` row — one left behind by a process that died mid-pull —
    would otherwise block every future run forever. Anything older than an hour
    is treated as abandoned and marked failed, because no honest pull takes that
    long and a permanently jammed pipeline is worse than a duplicated one.
    """
    current = latest_run(db, user_id)
    if current is not None and current.state is RunState.running:
        age = datetime.now(UTC) - current.started_at.replace(tzinfo=UTC)
        if age < timedelta(hours=1):
            raise RunAlreadyGoing(current.id)
        current.state = RunState.failed
        current.finished_at = datetime.now(UTC)
        current.error = "Abandoned: no result after an hour."

    run = DiscoveryRun(user_id=user_id)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def execute_run(run_id: str, user_id: str, settings: Settings, **filters: object) -> None:
    """Do the pull and record the outcome. Runs detached from any request.

    Opens its OWN session rather than borrowing the request's. By the time this
    executes, FastAPI has already returned the response and closed that session,
    so using it would fail on the first query — the kind of bug that only shows
    up in production under real timing.

    Never raises. It has no caller left to raise to: the response went out long
    ago. Every failure ends up on the run row instead, which is the only place
    anyone will look.
    """
    db = SessionLocal()
    try:
        run = db.get(DiscoveryRun, run_id)
        if run is None:
            return
        try:
            result = run_pull(db, user_id, settings, **filters)
            run.fetched = result.fetched
            run.staged = result.staged
            run.duplicates = result.duplicates
            run.enriched = result.enriched
            run.ruled_out = result.ruled_out
            run.sources = {FEED_SOURCE: result.model_dump()}
            run.state = RunState.succeeded
        except Exception as exc:  # noqa: BLE001 - see docstring
            run.state = RunState.failed
            # The class name plus the message: enough to recognise a repeat
            # failure without a stack trace nobody will read.
            run.error = f"{type(exc).__name__}: {exc}"[:2000]
        run.finished_at = datetime.now(UTC)
        db.commit()
    finally:
        db.close()
