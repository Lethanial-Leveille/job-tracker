"""The discovery feed: fetch a public listing of internships, keep the few that
could plausibly be yours, discard the rest.

This module does two things and neither of them touches the database. It
downloads the feed, and it decides which entries are worth your attention.
Staging what survives is services/discovery.py's job; this one is pure enough to
test against a fixture with no network and no session.

The source is a structured JSON file published by the SimplifyJobs internship
list, NOT the README tables that repository renders for humans. Those tables are
the obvious thing to scrape and the wrong one: they are HTML inside markdown
cells, they carry no stable identifier, and re-parsing them is how you end up
with the same job staged twice under two spellings. The JSON has an id per
posting, which is what makes the whole pull idempotent.

Filtering here is deliberately COARSE and deliberately free. It answers only
the questions a string comparison can answer honestly: is this posting open, for
the right year, open to an undergraduate, and recent. Sixteen thousand entries
come down and a few hundred survive.

What it does NOT do is decide whether a posting is the kind of job you want.
That needs reading the title properly — "Flight Software Intern" is a firmware
role and "Hardware Design Verification Engineer" is not, and no keyword list
gets that right for long. services/discovery.py does it with the role-family
classifier, after deduplication, so the paid call only ever sees postings that
are new to you.
"""

from datetime import UTC, datetime

import httpx
from pydantic import ValidationError

from schemas.discovery import FeedListing, PullResult

# The published file. A module constant rather than a setting because it is not
# a secret and not per-user; it moves to config.py the day a second feed exists.
FEED_URL = (
    "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships"
    "/dev/.github/scripts/listings.json"
)

# The name we record on every row this feed produces, so a second source later
# is distinguishable without a migration.
FEED_SOURCE = "simplify"

# Twelve megabytes of JSON over a home connection, and the download is the whole
# request. Generous, because a slow pull that finishes beats a fast one that has
# to run again.
_TIMEOUT = httpx.Timeout(120.0, connect=10.0)

# The feed labels the same category more than one way — "Software" and "Software
# Engineering" both appear, as do "AI/ML/Data" and "Data Science, AI & Machine
# Learning". Comparing the raw string against one spelling silently drops the
# other, which is the kind of filter bug that looks like a quiet week.
#
# So categories are normalized through this table first. Anything not listed
# normalizes to its own lowercased text, which will not match the wanted set and
# so gets dropped — but the drop is COUNTED by category in PullResult, which is
# how a new label the feed invents shows up as a number instead of as silence.
_CATEGORY_ALIASES = {
    "software": "software",
    "software engineering": "software",
    "ai/ml/data": "ai-ml-data",
    "data science, ai & machine learning": "ai-ml-data",
    "hardware": "hardware",
    "hardware engineering": "hardware",
    "quant": "quant",
    "product": "product",
    "product management": "product",
}

# A COARSE pre-filter, not the real decision. Its only job is to keep obviously
# irrelevant work out of the paid classifier downstream — quant and product are
# whole disciplines away, and paying to be told so would be waste.
#
# AI/ML/Data is deliberately INCLUDED here even though machine learning titles
# are not a target. The feed's taxonomy is loose enough that ordinary software
# roles get filed under it, and excluding the category outright would lose them
# with no way to notice. The classifier sorts that out properly: a real ML role
# comes back as "AI and ML Engineer Intern" and is dropped there, on the
# strength of its title rather than on the feed's shelving.
#
DEFAULT_CATEGORIES = frozenset({"software", "hardware", "ai-ml-data"})

# The cycle being applied to. Postings for other years are the single largest
# thing this filter removes.
#
# The feed also labels 203 active postings "N/A", meaning no term was stated.
# Those are excluded by the default. It is a real tradeoff and the honest answer
# is not obvious: including them adds a couple of hundred entries of which most
# are irrelevant, excluding them means a genuinely relevant posting with a sloppy
# label never reaches you. Narrow wins by default per the module docstring; add
# "N/A" to this set to see them.
DEFAULT_TERMS = frozenset({"Summer 2027"})

# An undergraduate. A posting that only wants a Master's or a PhD is not a near
# miss, it is a different job.
DEFAULT_DEGREE = "Bachelor's"

# How stale a posting can be and still be worth showing. Applications close, and
# a listing that has been up for a month has usually been filled or buried.
#
# Note what this number does on the FIRST run against an empty table: it is not
# a daily rate, it is the size of the backlog you get handed at once. Two weeks
# at the defaults is a few hundred rows on day one and roughly thirty a day
# after that, because the unique constraint means later pulls only ever stage
# what is genuinely new. Run the first pull with a smaller window if that
# backlog is not something you want to face.
DEFAULT_MAX_AGE_DAYS = 14


def fetch_listings(url: str = FEED_URL) -> list[FeedListing]:
    """Download the feed and validate it into FeedListings.

    Entries that fail validation are SKIPPED rather than raising. Every field on
    FeedListing has a default precisely so this is rare, but the file is written
    by someone else and a single malformed entry must not cost you the night's
    pull. A skipped entry is invisible here by design — it never became a
    listing, so the filter never sees it and it cannot be counted as a drop.
    """
    response = httpx.get(url, timeout=_TIMEOUT, follow_redirects=True)
    response.raise_for_status()

    listings: list[FeedListing] = []
    for entry in response.json():
        if not isinstance(entry, dict):
            continue
        try:
            listings.append(FeedListing.model_validate(entry))
        except ValidationError:
            continue
    return listings


def _category_key(raw: str) -> str:
    return _CATEGORY_ALIASES.get(raw.strip().lower(), raw.strip().lower())


def filter_listings(
    listings: list[FeedListing],
    *,
    categories: frozenset[str] = DEFAULT_CATEGORIES,
    terms: frozenset[str] = DEFAULT_TERMS,
    degree: str = DEFAULT_DEGREE,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> tuple[list[FeedListing], dict[str, int]]:
    """Keep the listings worth staging; count why the others went.

    Returns the survivors and a tally of drops by reason. The tally is not
    decoration — see PullResult. A filter that has stopped recognizing the
    feed's labels and a genuinely quiet week produce the same empty inbox, and
    this is the only thing that tells them apart.

    Checks run cheapest-first and stop at the first failure, so each listing is
    counted under exactly one reason: the first thing wrong with it.
    """
    dropped: dict[str, int] = {}
    kept: list[FeedListing] = []
    cutoff = datetime.now(UTC).date()

    def drop(reason: str) -> None:
        dropped[reason] = dropped.get(reason, 0) + 1

    for listing in listings:
        if not listing.active or not listing.is_visible:
            drop("closed")
        elif not listing.url or not listing.title or not listing.company_name:
            # A listing missing the fields a row is built from. Rare, and it
            # cannot be rescued: there is nothing to link to or call it.
            drop("incomplete")
        elif _category_key(listing.category) not in categories:
            # Counted by the feed's OWN label, not the normalized key, so an
            # unrecognized new category reads as itself here rather than
            # disappearing into a generic bucket.
            drop(f"category:{listing.category or 'none'}")
        elif not terms.intersection(listing.terms):
            drop("term")
        elif degree not in listing.degrees:
            drop("degree")
        else:
            posted = listing.posted_on()
            # A missing date is kept, not dropped. It means the feed did not say
            # when this was posted, which is not evidence that it is old, and
            # discarding a current posting over a missing field is the more
            # expensive mistake.
            if posted is not None and (cutoff - posted).days > max_age_days:
                drop("stale")
            else:
                kept.append(listing)

    return kept, dropped


def pull(url: str = FEED_URL, **filters: object) -> tuple[list[FeedListing], PullResult]:
    """Fetch and filter in one call: what the staging service starts from.

    The PullResult comes back already carrying the counts this stage knows
    about. Staging fills in the rest, because only it can know how many of these
    were jobs you are already tracking.
    """
    listings = fetch_listings(url)
    kept, dropped = filter_listings(listings, **filters)  # type: ignore[arg-type]
    return kept, PullResult(
        fetched=len(listings), kept=len(kept), dropped=dropped
    )
